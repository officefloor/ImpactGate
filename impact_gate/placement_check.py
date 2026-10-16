"""Per-change placement check (prototype): does this change touch or create a coupling
vortex?

A complementary signal to the impact score. ImpactGate's score asks "is this change
piling complexity onto already-complex code". This asks a different, placement question:
"are the methods this change adds or mutates coupling-generation OUTLIERS in the resulting
tree" -- the orchestrator god the size-based score can miss. It is a snapshot test on the
AFTER state (the working tree), so it needs no history and no prediction.

It reuses `gitio.changed_files` to find the changed functions and
`core.generation.analyze_tree` to place them against every function in the tree. A changed
function is flagged when its generation `gain` is a modified-z outlier; a changed file is
flagged when its class-cumulated generation is an outlier. Report it beside the impact
score, not folded into it: the two measure different axes (we verified generation catches
orchestrators the WMC cost under-weights and ignores the self-contained complex algorithms
the WMC cost over-weights), and blending them would blur both.

    python -m impact_gate.placement_check --repo . --mode range --base main
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass

import lizard

from . import gitio
from .core import generation as gen
from .engine import IMPACT_STATUSES, _touches


@dataclass
class Flag:
    path: str
    name: str
    gain: int
    kind: str            # "method" (gain outlier) and/or "class" (file-cumulated outlier)


def _changed_functions(repo: str, changed) -> set:
    """(relpath, short_name) touched by the change: a new file's functions, or (for a
    modified file) the functions overlapping the added line ranges, read from the AFTER
    (working-tree) version via lizard."""
    out: set = set()
    for c in changed:
        if c.status not in IMPACT_STATUSES or c.after is None:
            continue
        path = os.path.join(repo, c.path)
        try:
            units = lizard.analyze_file(path).function_list
        except Exception:
            continue
        new_file = c.before is None
        for u in units:
            if new_file or _touches(u, c.added):
                out.add((c.path, gen._short(u.name)))
    return out


def check(repo: str, mode: str, base: str) -> dict:
    """Return the placement signal for the current change: the changed functions that are
    generation outliers in the after-state tree, and the changed files that are
    class-generation outliers."""
    changed = gitio.changed_files(repo, mode, base)
    changed_fns = _changed_functions(repo, changed)
    changed_files = {c.path for c in changed if c.status in IMPACT_STATUSES}

    res = gen.analyze_tree(repo)
    funcs, wmc = res["funcs"], res["wmc"]
    mouts = gen.outliers(funcs)
    couts = gen.class_outliers(gen.class_gain(funcs))

    flags: list[Flag] = []
    for fid in sorted(changed_fns):
        if fid in mouts:
            flags.append(Flag(fid[0], fid[1], funcs[fid]["gain"], "method"))
    file_flags = sorted(f for f in (changed_files & couts))
    return {
        "changed_functions": len(changed_fns),
        "changed_files": len(changed_files),
        "method_vortex_flags": flags,
        "class_vortex_files": file_flags,
        "tree_functions": len(funcs),
    }


def has_vortex(result: dict) -> bool:
    """True when the change touches at least one coupling vortex (a method generation
    outlier or a class-cumulated outlier). The gate's one-bit summary of the result."""
    return bool(result.get("method_vortex_flags") or result.get("class_vortex_files"))


def render(result: dict) -> str:
    lines = []
    mf, cf = result["method_vortex_flags"], result["class_vortex_files"]
    if not mf and not cf:
        lines.append("placement: no coupling vortex among the changed methods "
                     f"({result['changed_functions']} changed functions checked).")
        return "\n".join(lines)
    lines.append("placement: this change touches coupling vortices (generation outliers "
                 "in the resulting tree) -- review for an orchestrator god:")
    for f in sorted(mf, key=lambda x: -x.gain):
        lines.append(f"  method  gain={f.gain:>4}  {f.name}  ({f.path})")
    for p in cf:
        lines.append(f"  class   (cumulated generation outlier)  {p}")
    lines.append("Note: a signal to look, not a block. High generation is the orchestrator "
                 "axis, complementary to the impact score, not the same as it.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="impact-gate placement-check", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".")
    ap.add_argument("--mode", default="range", choices=["range", "staged", "worktree"])
    ap.add_argument("--base", default="main")
    args = ap.parse_args(argv)
    print(render(check(args.repo, args.mode, args.base)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
