"""The structural change-impact measure — the engine seam.

Everything that knows the formula lives behind this module: it drives the vendored,
self-contained `core` measure over a set of changed files, so the rest of the tool
speaks only in `ChangedFile` / `ChangeScore` and never sees the formula.

Input contract: a list of `ChangedFile` (path + before/after bytes + diff ranges),
produced by `gitio` from git. Output: a `ChangeScore` (the composite impact number
plus the per-file / per-unit breakdown that drives "simplify or refactor" guidance).
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Importing .core registers the default (lizard) plugin as a side effect.
from . import core as _core  # noqa: F401
from .core.config import MeasureConfig
from .core.impact import compute_file_impact
from .core.units import get_plugin

# Statuses that carry impact (added / modified / renamed). Deletions have no "after"
# unit to weight, so — like the scan — they are not scored.
IMPACT_STATUSES = ("A", "M", "R")


@dataclass
class ChangedFile:
    """One file's change, git-agnostic: bytes on each side + the -U0 line ranges."""
    path: str
    status: str                                   # A / M / D / R
    before: bytes | None                          # None for an added file
    after: bytes | None                           # None for a deleted file
    added: list[tuple[int, int]] = field(default_factory=list)    # (start, count) in NEW
    removed: list[tuple[int, int]] = field(default_factory=list)  # (start, count) in OLD


@dataclass
class UnitScore:
    path: str
    name: str
    container: str
    cc: int
    wmc_other: int
    cost: int
    kind: str          # mutation / godclass / rename


@dataclass
class FileScore:
    path: str
    lang: str
    mutation: int
    godclass: int
    mut_fns: int
    new_fns: int

    @property
    def cost(self) -> int:
        return self.mutation + self.godclass


@dataclass
class ChangeScore:
    files_changed: int
    mutation: int
    godclass: int
    impact: int                    # composite = (mutation + godclass) * files_changed
    files: list[FileScore] = field(default_factory=list)
    units: list[UnitScore] = field(default_factory=list)   # sorted by cost, desc

    @property
    def empty(self) -> bool:
        return self.files_changed == 0


def _parse(mcfg: MeasureConfig, path: str, data: bytes | None):
    """(source_lines, units) for one file version, or ([], []) when absent/unparsable."""
    if data is None:
        return [], []
    plugin = get_plugin(mcfg.ext(path))
    units = plugin.parse(data, path) if plugin else []
    src = data.decode("utf-8", errors="replace").split("\n")
    return src, units


def score_change(changed: list[ChangedFile], mcfg: MeasureConfig | None = None,
                 wmc_context: str = "before") -> ChangeScore:
    """Compute the change-impact of a set of changed files.

    Only source files with an impact-bearing status count, `files_changed` is the
    spread term, and the composite is `(Σ mutation + Σ godclass) * files_changed`.
    """
    mcfg = mcfg or MeasureConfig()
    src = [c for c in changed
           if c.status in IMPACT_STATUSES and mcfg.is_source(c.path)]
    files_changed = len(src)

    total_mut = total_god = 0
    files: list[FileScore] = []
    units: list[UnitScore] = []
    for c in src:
        before_src, before_units = _parse(mcfg, c.path, c.before)
        after_src, after_units = _parse(mcfg, c.path, c.after)
        if not after_units and not before_units:
            continue
        fi = compute_file_impact(
            before_units, after_units, before_src, after_src,
            c.added, c.removed, mcfg.rename_jaccard, wmc_context,
        )
        total_mut += fi.mutation_cost
        total_god += fi.godclass_cost
        files.append(FileScore(c.path, mcfg.language(c.path) or "",
                               fi.mutation_cost, fi.godclass_cost,
                               fi.mut_fns, fi.new_fns))
        for u in fi.units:
            units.append(UnitScore(c.path, u.name, u.container, u.cc,
                                   u.wmc_other, u.cost, u.kind))

    files.sort(key=lambda f: f.cost, reverse=True)
    units.sort(key=lambda u: u.cost, reverse=True)
    composite = (total_mut + total_god) * files_changed
    return ChangeScore(files_changed, total_mut, total_god, composite, files, units)
