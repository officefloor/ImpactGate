"""Render a ChangeScore as human text or machine JSON."""
from __future__ import annotations

import json

from .config import GateConfig
from .engine import ChangeScore

_MODE_DESC = {"range": "vs {base} (merge-base..HEAD)",
              "staged": "staged vs HEAD", "worktree": "working tree vs HEAD"}


def _unit_parts(u) -> tuple[str, str]:
    """(container, short_name) for a unit. "Owner::addOwner" -> ("Owner", "addOwner");
    a free function keeps its name and reports container "" (file scope). The class is
    what you look at when a driver is heavy, so the reports show it beside the method."""
    short = u.name.rpartition("::")[2] if "::" in u.name else u.name
    return u.container, short


def _thresholds_note(cfg: GateConfig) -> str:
    w, b = cfg.effective_warn(), cfg.effective_block()
    parts = []
    if w is not None:
        parts.append(f"warn ≥ {int(w):,}")
    if b is not None:
        parts.append(f"block ≥ {int(b):,}")
    return "  (" + " · ".join(parts) + ")" if parts else ""


def _grade_source(grade) -> str:
    """How the grade was arrived at: pure seed at cold start, else the blend weight."""
    if grade.project_percentile is None:
        return "seed only"
    return f"blended n={grade.n}, w={grade.weight:.2f}"


def _grade_line(grade, cfg: GateConfig) -> str:
    """The percentile-grade line for text output, carrying the curve thresholds."""
    lang = grade.language or "pooled"
    return (f"  grade: {grade.percentile:g}th percentile   "
            f"(warn ≥ p{cfg.warn_percentile:g} · block ≥ p{cfg.block_percentile:g}; "
            f"{lang}, {_grade_source(grade)})")


def _cognitive_offenders(score: ChangeScore, cfg: GateConfig, limit: int = 10):
    """Methods in changed files whose cognitive complexity exceeds the gate (or [] if off)."""
    if not cfg.cognitive_enabled():
        return []
    return [u for u in score.cognitive_units if u.cognitive > cfg.cognitive_max][:limit]


def cognitive_report(score: ChangeScore, cfg: GateConfig) -> dict | None:
    """The cognitive-gate section for JSON output, or None when the gate is off."""
    if not cfg.cognitive_enabled():
        return None
    offs = _cognitive_offenders(score, cfg)
    return {
        "threshold": cfg.cognitive_max,
        "max": score.cognitive_max,
        "blocked": bool(offs),
        "offenders": [{"path": u.path, "name": u.name, "container": u.container,
                       "cognitive": u.cognitive} for u in offs],
    }


def _cognitive_lines(score: ChangeScore, cfg: GateConfig) -> list[str]:
    """Text/markdown lines naming the over-limit methods to break up (or [] when none)."""
    offs = _cognitive_offenders(score, cfg, limit=5)
    if not offs:
        return []
    lines = ["", f"Methods over the cognitive-complexity limit ({cfg.cognitive_max}) — "
             "break these into smaller methods (reduce nesting/decision depth; "
             "sequential code is fine):"]
    for u in offs:
        container, short = _unit_parts(u)
        loc = f"{u.path}:{short}" if short else u.path
        where = f"in {container}" if container else "file scope"
        lines.append(f"  cognitive {u.cognitive:>4}  {loc}  ({where})")
    return lines


def render_text(score: ChangeScore, cfg: GateConfig, level: str,
                mode: str, base: str, blocked: bool, grade=None) -> str:
    if score.empty:
        return "impact-gate: no source changes to score."
    # Tag reflects the OUTCOME under the current enforcement, not just the severity.
    # In warn/off mode a change over the block threshold is allowed (tag WARN), with a
    # nudge that it will fail once enforcement is 'block'. This is the warn->block on-ramp.
    tag = "BLOCK" if blocked else ("OK" if level == "ok" else "WARN")
    desc = _MODE_DESC[mode].format(base=base)
    # In curve mode the grade line carries the (percentile) thresholds; in absolute mode
    # they hang off the headline instead.
    note = "" if grade is not None else _thresholds_note(cfg)
    lines = [f"Change impact: {score.impact:,}   [{tag}]{note}"]
    if grade is not None:
        lines.append(_grade_line(grade, cfg))
    lines.append(f"  files changed: {score.files_changed}   ({desc})")
    if score.skipped:
        lines.append(f"  skipped {len(score.skipped)} oversized file(s), not scored "
                     "(diff over max_diff_lines; likely generated or vendored):")
        for s in score.skipped:
            lines.append(f"    {s.path}  ({s.diff_lines:,} diff lines)")
    if level == "block" and not blocked:
        lines.append("  note: over the block threshold. This will fail once "
                     "enforcement is set to 'block'.")
    ranked = [f for f in score.files if f.cost > 0]
    if ranked:
        lines.append("")
        lines.append("Files to consider for refactoring (by change-impact cost):")
        for f in ranked[:5]:
            lines.append(f"  {f.cost:>12,}  {f.path}  "
                         f"(existing {f.mutation:,}, new {f.godclass:,}; "
                         f"{f.mut_fns} fns changed, {f.new_fns} new)")
    if level != "ok" and score.units:
        lines.append("")
        lines.append("Top cost drivers. Simplify or refactor these:")
        for u in score.units[:5]:
            container, short = _unit_parts(u)
            loc = f"{u.path}:{short}" if short else u.path
            where = f"in {container}" if container else "file scope"
            lines.append(f"  {u.cost:>12,}  {loc}  "
                         f"({where}, CC {u.cc}, WMC_other {u.wmc_other}, {u.kind})")
    lines.extend(_cognitive_lines(score, cfg))
    return "\n".join(lines)


def render_json(score: ChangeScore, cfg: GateConfig, level: str,
                mode: str, base: str, blocked: bool, grade=None) -> str:
    thresholds = {
        "warn": cfg.effective_warn(),
        "block": cfg.effective_block(),
        "enforcement": cfg.enforcement,
        "tolerance": cfg.tolerance,
    }
    if grade is not None:
        thresholds["warn_percentile"] = cfg.warn_percentile
        thresholds["block_percentile"] = cfg.block_percentile
    out = {
        "impact": score.impact,
        "level": level,
        "blocked": blocked,
        "curve": cfg.curve_enabled,
        "files_changed": score.files_changed,
        "mode": mode,
        "base": base,
        "thresholds": thresholds,
        "files": [{"path": f.path, "lang": f.lang, "cost": f.cost,
                   "mutation": f.mutation, "godclass": f.godclass,
                   "mut_fns": f.mut_fns, "new_fns": f.new_fns} for f in score.files],
        "skipped": [{"path": s.path, "diff_lines": s.diff_lines}
                    for s in score.skipped],
        "top_units": [{"path": u.path, "name": u.name, "container": u.container,
                       "cc": u.cc, "wmc_other": u.wmc_other, "cost": u.cost,
                       "kind": u.kind} for u in score.units[:10]],
    }
    if grade is not None:
        out["grade"] = {
            "percentile": grade.percentile,
            "value": grade.value,
            "seed_percentile": grade.seed_percentile,
            "project_percentile": grade.project_percentile,
            "weight": grade.weight,
            "n": grade.n,
            "language": grade.language,
        }
    cog = cognitive_report(score, cfg)
    if cog is not None:
        out["cognitive"] = cog
    return json.dumps(out, indent=2)


def render_markdown(score: ChangeScore, cfg: GateConfig, level: str,
                    mode: str, base: str, blocked: bool, grade=None) -> str:
    """GitHub/GitLab-friendly summary. Written to the CI job summary."""
    if score.empty:
        return "**impact-gate:** no source changes to score."
    verdict = {"ok": "✅ OK", "warn": "⚠️ WARN", "block": "⛔ BLOCK"}[
        "block" if blocked else ("ok" if level == "ok" else "warn")]
    desc = _MODE_DESC[mode].format(base=base)
    lines = [
        f"## Change impact: {score.impact:,}  {verdict}",
        "",
        "| field | value |",
        "|---|---|",
        f"| files changed | {score.files_changed} |",
    ]
    if grade is not None:
        lines.append(f"| grade | {grade.percentile:g}th percentile "
                     f"({grade.language or 'pooled'}, {_grade_source(grade)}) |")
        lines.append(f"| warn / block percentile | p{cfg.warn_percentile:g} / "
                     f"p{cfg.block_percentile:g} |")
    else:
        w, b = cfg.effective_warn(), cfg.effective_block()
        if w is not None:
            lines.append(f"| warn threshold | {int(w):,} |")
        if b is not None:
            lines.append(f"| block threshold | {int(b):,} |")
    lines.append(f"| scope | {desc} |")
    if score.skipped:
        lines.append(f"| skipped (oversized, not scored) | {len(score.skipped)} |")
    if level == "block" and not blocked:
        lines += ["", "> Over the block threshold. This will fail once enforcement "
                  "is set to `block`."]
    if score.skipped:
        lines += ["", "### Skipped: oversized files, not scored", "",
                  "Diff over `max_diff_lines` (likely generated or vendored).", "",
                  "| file | diff lines |", "|---|---|"]
        for s in score.skipped:
            lines.append(f"| `{s.path}` | {s.diff_lines:,} |")
    ranked = [f for f in score.files if f.cost > 0]
    if ranked:
        lines += ["", "### Files to consider for refactoring", "",
                  "| cost | file | existing | new | fns changed | fns new |",
                  "|---|---|---|---|---|---|"]
        for f in ranked[:5]:
            lines.append(f"| {f.cost:,} | `{f.path}` | {f.mutation:,} | "
                         f"{f.godclass:,} | {f.mut_fns} | {f.new_fns} |")
    if level != "ok" and score.units:
        lines += ["", "### Top cost drivers. Simplify or refactor these.", "",
                  "| cost | location | class | CC | WMC_other | kind |",
                  "|---|---|---|---|---|---|"]
        for u in score.units[:5]:
            container, short = _unit_parts(u)
            loc = f"`{u.path}:{short}`" if short else f"`{u.path}`"
            cls = f"`{container}`" if container else "_file scope_"
            lines.append(f"| {u.cost:,} | {loc} | {cls} | {u.cc} | {u.wmc_other} | "
                         f"{u.kind} |")
    offs = _cognitive_offenders(score, cfg, limit=5)
    if offs:
        lines += ["", f"### Methods over the cognitive-complexity limit ({cfg.cognitive_max})",
                  "", "Break these into smaller methods — reduce nesting/decision depth "
                  "(sequential code is fine).", "",
                  "| cognitive | location | class |", "|---|---|---|"]
        for u in offs:
            container, short = _unit_parts(u)
            loc = f"`{u.path}:{short}`" if short else f"`{u.path}`"
            cls = f"`{container}`" if container else "_file scope_"
            lines.append(f"| {u.cognitive} | {loc} | {cls} |")
    return "\n".join(lines)
