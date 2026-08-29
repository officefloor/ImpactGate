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


def render_text(score: ChangeScore, cfg: GateConfig, level: str,
                mode: str, base: str, blocked: bool) -> str:
    if score.empty:
        return "impact-gate: no source changes to score."
    # Tag reflects the OUTCOME under the current enforcement, not just the severity.
    # In warn/off mode a change over the block threshold is allowed (tag WARN), with a
    # nudge that it will fail once enforcement is 'block'. This is the warn->block on-ramp.
    tag = "BLOCK" if blocked else ("OK" if level == "ok" else "WARN")
    desc = _MODE_DESC[mode].format(base=base)
    lines = [
        f"Change impact: {score.impact:,}   [{tag}]{_thresholds_note(cfg)}",
        f"  files changed: {score.files_changed}   "
        f"mutation: {score.mutation:,}   new code: {score.godclass:,}   "
        f"({desc})",
    ]
    if level == "block" and not blocked:
        lines.append("  note: over the block threshold. This will fail once "
                     "enforcement is set to 'block'.")
    if level != "ok" and score.units:
        lines.append("")
        lines.append("Top cost drivers. Simplify or refactor these:")
        for u in score.units[:5]:
            container, short = _unit_parts(u)
            loc = f"{u.path}:{short}" if short else u.path
            where = f"in {container}" if container else "file scope"
            lines.append(f"  {u.cost:>12,}  {loc}  "
                         f"({where}, CC {u.cc}, WMC_other {u.wmc_other}, {u.kind})")
    return "\n".join(lines)


def render_json(score: ChangeScore, cfg: GateConfig, level: str,
                mode: str, base: str, blocked: bool) -> str:
    return json.dumps({
        "impact": score.impact,
        "level": level,
        "blocked": blocked,
        "files_changed": score.files_changed,
        "mutation": score.mutation,
        "godclass": score.godclass,
        "mode": mode,
        "base": base,
        "thresholds": {
            "warn": cfg.effective_warn(),
            "block": cfg.effective_block(),
            "enforcement": cfg.enforcement,
            "tolerance": cfg.tolerance,
        },
        "files": [{"path": f.path, "lang": f.lang, "cost": f.cost,
                   "mutation": f.mutation, "godclass": f.godclass,
                   "mut_fns": f.mut_fns, "new_fns": f.new_fns} for f in score.files],
        "top_units": [{"path": u.path, "name": u.name, "container": u.container,
                       "cc": u.cc, "wmc_other": u.wmc_other, "cost": u.cost,
                       "kind": u.kind} for u in score.units[:10]],
    }, indent=2)


def render_markdown(score: ChangeScore, cfg: GateConfig, level: str,
                    mode: str, base: str, blocked: bool) -> str:
    """GitHub/GitLab-friendly summary. Written to the CI job summary."""
    if score.empty:
        return "**impact-gate:** no source changes to score."
    verdict = {"ok": "✅ OK", "warn": "⚠️ WARN", "block": "⛔ BLOCK"}[
        "block" if blocked else ("ok" if level == "ok" else "warn")]
    desc = _MODE_DESC[mode].format(base=base)
    lines = [
        f"## Change impact: {score.impact:,}  {verdict}",
        "",
        "| metric | value |",
        "|---|---|",
        f"| files changed | {score.files_changed} |",
        f"| mutation (disturbing existing code) | {score.mutation:,} |",
        f"| new code | {score.godclass:,} |",
    ]
    w, b = cfg.effective_warn(), cfg.effective_block()
    if w is not None:
        lines.append(f"| warn threshold | {int(w):,} |")
    if b is not None:
        lines.append(f"| block threshold | {int(b):,} |")
    lines.append(f"| scope | {desc} |")
    if level == "block" and not blocked:
        lines += ["", "> Over the block threshold. This will fail once enforcement "
                  "is set to `block`."]
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
    return "\n".join(lines)
