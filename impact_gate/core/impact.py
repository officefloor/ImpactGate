"""The structural change-impact measure for one file within one change.

cost(unit)    = max(WMC_other, 1) * CC * max(1, dlines)
  WMC_other   = sum CC of the OTHER units sharing the unit's container, measured on
                the PRE-change (before) container by default (`wmc_context`), so a unit
                added to a brand-new container costs ~CC*dlines while a method accreted
                onto an existing class is still charged for the siblings already there.
mutation_cost = sum cost over modified/renamed existing units
godclass_cost = sum cost over new units (new files + new methods)

The change-level composite multiplies (mutation+godclass) by files_changed; that
spread term is applied by the caller, which knows the whole change.

Rename handling is intentionally LIGHT: match after-vs-before units by exact name
first, then a single greedy token-set Jaccard pass over the leftovers. Cross-file
moves are not chased.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .units import Unit

_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


@dataclass
class UnitImpact:
    name: str
    container: str
    cc: int
    dlines: int
    wmc_other: int
    cost: int
    kind: str          # "mutation" | "godclass" (new) | "rename"


@dataclass
class FileImpact:
    mutation_cost: int = 0
    godclass_cost: int = 0
    mut_fns: int = 0
    new_fns: int = 0
    renames: int = 0
    units: list[UnitImpact] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.units is None:
            self.units = []


def _line_set(ranges: list[tuple[int, int]]) -> set[int]:
    out: set[int] = set()
    for start, count in ranges:
        out.update(range(start, start + count))
    return out


def _overlap(u: Unit, lines: set[int]) -> int:
    if not lines:
        return 0
    return sum(1 for ln in range(u.start_line, u.end_line + 1) if ln in lines)


def _tokens(src_lines: list[str], u: Unit) -> set[str]:
    body = "\n".join(src_lines[max(0, u.start_line - 1): u.end_line])
    return set(_TOKEN.findall(body))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def compute_file_impact(
    before: list[Unit], after: list[Unit],
    before_src: list[str], after_src: list[str],
    added: list[tuple[int, int]], removed: list[tuple[int, int]],
    rename_jaccard: float, wmc_context: str = "before",
) -> FileImpact:
    added_lines = _line_set(added)
    removed_lines = _line_set(removed)

    # WMC_other = the surrounding complexity you must comprehend to change a unit.
    # Two definitions, selected by `wmc_context`:
    #   "after"  — the container as it stands in the RESULTING file (original behaviour).
    #   "before" — the complexity that PRE-EXISTED the change (the context you faced).
    # Under "before", a unit added to a brand-new container has no prior siblings, so its
    # WMC_other falls to 0 (floored to 1): importing/greenfield code costs only ~CC*dlines,
    # while a method accreted onto an existing (god) class is still charged for the siblings
    # that were already there — so growth-by-accretion stays expensive.
    after_by_container: dict[str, int] = {}
    for u in after:
        after_by_container[u.container] = after_by_container.get(u.container, 0) + u.cc
    before_by_container: dict[str, int] = {}
    for u in before:
        before_by_container[u.container] = before_by_container.get(u.container, 0) + u.cc

    def _wmc(u: Unit, src: Unit | None) -> int:
        if wmc_context == "before":
            # other pre-existing complexity in the container; subtract the unit's own prior
            # contribution (`src`) only if it already existed — a new unit subtracts nothing.
            base = before_by_container.get(u.container, 0)
            return max(base - (src.cc if src is not None else 0), 0)
        return max(after_by_container.get(u.container, 0) - u.cc, 0)

    before_by_name = {u.name: u for u in before}
    after_names = {u.name for u in after}

    # Which after-units the change actually touched, and by how much.
    touched_after = [(u, _overlap(u, added_lines)) for u in after]
    touched_after = [(u, n) for u, n in touched_after if n > 0]

    matched_before: set[str] = set()
    fi = FileImpact()

    for u, add_n in touched_after:
        prior = before_by_name.get(u.name)
        kind = "mutation"
        del_n = 0
        src = prior            # before-side unit this change corresponds to (None if new)
        if prior is not None:
            matched_before.add(prior.name)
            del_n = _overlap(prior, removed_lines)
        else:
            # light rename match: best Jaccard among removed before-units (those
            # gone from `after`), touched by this diff and not already claimed.
            cand = _best_rename(u, before, after_names, matched_before,
                                removed_lines, before_src, after_src, rename_jaccard)
            if cand is not None:
                matched_before.add(cand.name)
                del_n = _overlap(cand, removed_lines)
                kind = "rename"
                src = cand
            else:
                kind = "godclass"  # genuinely new unit

        dlines = max(1, add_n + del_n)
        wmc = _wmc(u, src)
        cost = max(wmc, 1) * u.cc * dlines
        fi.units.append(UnitImpact(u.name, u.container, u.cc, dlines, wmc, cost, kind))
        if kind == "godclass":
            fi.godclass_cost += cost
            fi.new_fns += 1
        else:
            fi.mutation_cost += cost
            fi.mut_fns += 1
            if kind == "rename":
                fi.renames += 1

    return fi


def _best_rename(u: Unit, before: list[Unit], after_names: set[str],
                 matched: set[str], removed_lines: set[int],
                 before_src, after_src, threshold: float) -> Unit | None:
    u_tokens = _tokens(after_src, u)
    best, best_j = None, threshold
    for b in before:
        if b.name in matched or b.name in after_names:
            continue  # already claimed, or still exists (not a rename source)
        if _overlap(b, removed_lines) == 0:
            continue
        j = _jaccard(u_tokens, _tokens(before_src, b))
        if j >= best_j:
            best, best_j = b, j
    return best
