"""impact-gate command line.

  impact-gate score [--mode staged|worktree|range] [--base main] ...

Exit codes: 0 = ok or warn (change allowed), 2 = blocked (impact too high, enforcement
'block'), 1 = usage/environment error. CI wrappers (GitHub/GitLab/Jenkins) call this
same command and translate the exit code + JSON into a check result / comment.
"""
from __future__ import annotations

import argparse
import sys

from .core.config import MeasureConfig

from . import __version__, gitio, report
from .config import ENFORCEMENTS, GateConfig
from .engine import score_change


def _add_score_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--mode", choices=gitio.MODES, default="staged",
                   help="what to score: 'staged' (the commit you're about to make, "
                        "default), 'worktree' (uncommitted edits), or 'range' "
                        "(committed branch vs --base, for CI/PR).")
    p.add_argument("--base", default="main",
                   help="base ref for --mode range (default: main). Use e.g. "
                        "origin/main in CI.")
    p.add_argument("--repo", default=".", help="path to the git repo (default: .)")
    p.add_argument("--format", choices=("text", "json", "markdown"), default="text")
    p.add_argument("--config", help="path to an .impact-gate.yml (else auto-discovered in --repo)")
    # threshold / enforcement overrides (win over the config file when given)
    p.add_argument("--warn-at", type=int)
    p.add_argument("--block-at", type=int)
    p.add_argument("--enforcement", choices=ENFORCEMENTS)
    p.add_argument("--tolerance", type=float)
    p.add_argument("--wmc-context", choices=("before", "after"))
    p.add_argument("--measure-config", help="Surveyor-style YAML for ignore globs etc.")


def _resolve_config(args) -> GateConfig:
    cfg = GateConfig.load(args.config, args.repo)
    for attr in ("warn_at", "block_at", "enforcement", "tolerance",
                 "wmc_context", "measure_config"):
        val = getattr(args, attr, None)
        if val is not None:
            setattr(cfg, attr, val)
    cfg.validate()
    return cfg


def _cmd_score(args) -> int:
    cfg = _resolve_config(args)
    mcfg = MeasureConfig.load(cfg.measure_config)
    try:
        changed = gitio.changed_files(args.repo, args.mode, args.base)
    except gitio.DiffError as e:
        print(f"impact-gate: {e}", file=sys.stderr)
        return 1

    score = score_change(changed, mcfg, cfg.wmc_context)
    level = cfg.level(score.impact)
    blocked = cfg.blocks(score.impact)

    if args.format == "json":
        print(report.render_json(score, cfg, level, args.mode, args.base, blocked))
    elif args.format == "markdown":
        print(report.render_markdown(score, cfg, level, args.mode, args.base, blocked))
    else:
        print(report.render_text(score, cfg, level, args.mode, args.base, blocked))
        if blocked:
            print("\nimpact-gate: change BLOCKED — impact exceeds the block threshold. "
                  "Simplify the change or refactor the code it touches, then retry.",
                  file=sys.stderr)
    return 2 if blocked else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="impact-gate",
                                 description="Report and gate on the change-impact of a change.")
    ap.add_argument("--version", action="version", version=f"impact-gate {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("score", help="score the current change and gate on it")
    _add_score_args(s)
    s.set_defaults(func=_cmd_score)

    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except ValueError as e:            # config validation, bad args
        print(f"impact-gate: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
