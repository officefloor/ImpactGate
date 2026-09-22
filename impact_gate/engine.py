"""The structural change-impact measure: the engine seam.

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
# unit to weight, so (like the scan) they are not scored.
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
class CognitiveUnit:
    """A function in a changed file with its ABSOLUTE cognitive complexity (Campbell 2018).

    Independent of the change-impact composite: a per-method readability signal over the AFTER
    version of every file the change touched, consumed by the optional cognitive gate."""
    path: str
    name: str
    container: str
    cognitive: int


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
class SkippedFile:
    """A source file left out of the score because its diff is pathologically large.

    A generated dump or a vendored blob can be enormous; scoring it would distort the
    impact number (and slow parsing) without measuring any real structural decay. The
    gate skips it past `max_diff_lines` and surfaces it so the number is never silently
    wrong."""
    path: str
    diff_lines: int


@dataclass
class ChangeScore:
    files_changed: int
    mutation: int
    godclass: int
    impact: int                    # composite = (mutation + godclass) * files_changed
    files: list[FileScore] = field(default_factory=list)
    units: list[UnitScore] = field(default_factory=list)   # sorted by cost, desc
    skipped: list[SkippedFile] = field(default_factory=list)   # over max_diff_lines
    cognitive_max: int = 0                                     # worst method (changed files, after)
    cognitive_units: list[CognitiveUnit] = field(default_factory=list)  # sorted by cognitive, desc

    @property
    def empty(self) -> bool:
        # Nothing scored AND nothing skipped: a genuinely empty change. A change whose
        # only source edits were skipped is not empty. The skip must still be reported.
        return self.files_changed == 0 and not self.skipped


def _touches(u, added: list[tuple[int, int]]) -> bool:
    """True if function `u`'s line span overlaps any of the change's NEW-side added ranges
    (start, count) — i.e. this change added or edited lines inside the function."""
    for start, count in added:
        if count <= 0:
            continue
        if not (u.end_line < start or u.start_line > start + count - 1):
            return True
    return False


def _parse(mcfg: MeasureConfig, path: str, data: bytes | None):
    """(source_lines, units) for one file version, or ([], []) when absent/unparsable."""
    if data is None:
        return [], []
    plugin = get_plugin(mcfg.ext(path))
    units = plugin.parse(data, path) if plugin else []
    src = data.decode("utf-8", errors="replace").split("\n")
    return src, units


def score_change(changed: list[ChangedFile],
                 mcfg: MeasureConfig | None = None) -> ChangeScore:
    """Compute the change-impact of a set of changed files.

    Only source files with an impact-bearing status count, `files_changed` is the
    spread term, and the composite is `(Σ mutation + Σ godclass) * files_changed`.
    """
    mcfg = mcfg or MeasureConfig()
    src = [c for c in changed
           if c.status in IMPACT_STATUSES and mcfg.is_source(c.path)]

    # Bulk-commit guard: a source file whose diff exceeds max_diff_lines is almost
    # always a generated dump or a vendored blob. Skip it so it neither distorts the
    # composite nor slows parsing; it is reported separately, not counted or scored.
    skipped: list[SkippedFile] = []
    scored: list[ChangedFile] = []
    for c in src:
        dl = sum(n for _, n in c.added) + sum(n for _, n in c.removed)
        if mcfg.max_diff_lines and dl > mcfg.max_diff_lines:
            skipped.append(SkippedFile(c.path, dl))
        else:
            scored.append(c)
    files_changed = len(scored)

    total_mut = total_god = 0
    files: list[FileScore] = []
    units: list[UnitScore] = []
    cog_units: list[CognitiveUnit] = []
    for c in scored:
        before_src, before_units = _parse(mcfg, c.path, c.before)
        after_src, after_units = _parse(mcfg, c.path, c.after)
        if not after_units and not before_units:
            continue
        fi = compute_file_impact(
            before_units, after_units, before_src, after_src,
            c.added, c.removed, mcfg.rename_jaccard,
        )
        total_mut += fi.mutation_cost
        total_god += fi.godclass_cost
        files.append(FileScore(c.path, mcfg.language(c.path) or "",
                               fi.mutation_cost, fi.godclass_cost,
                               fi.mut_fns, fi.new_fns))
        for u in fi.units:
            units.append(UnitScore(c.path, u.name, u.container, u.cc,
                                   u.wmc_other, u.cost, u.kind))
        # Cognitive readability gate: scoped to the methods THIS change actually touched — a new
        # file's methods, or (for a modified file) only functions overlapping the added line
        # ranges. A pre-existing, untouched, already-accepted complex method in the same file is
        # never re-flagged, so the gate nags about code you just wrote, not code you inherited.
        new_file = c.before is None
        for u in after_units:
            if new_file or _touches(u, c.added):
                cog_units.append(CognitiveUnit(c.path, u.name, u.container, u.cognitive))

    files.sort(key=lambda f: f.cost, reverse=True)
    units.sort(key=lambda u: u.cost, reverse=True)
    cog_units.sort(key=lambda u: u.cognitive, reverse=True)
    cognitive_max = cog_units[0].cognitive if cog_units else 0
    composite = (total_mut + total_god) * files_changed
    return ChangeScore(files_changed, total_mut, total_god, composite, files, units,
                       skipped, cognitive_max, cog_units)
