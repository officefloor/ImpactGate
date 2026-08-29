"""The project baseline: the repo's own per-commit impact distribution, and the
empirical-Bayes blend of it with the shipped seed prior.

Scope. The walk starts from the merged base branch (default `main`) and follows its
first-parent mainline, so only landed work is measured; an unmerged in-flight branch is
never reached, because the walk only ever follows real merge commits.

One observation = one atomic landed change:
  * a main non-merge commit -> its own diff vs its parent;
  * a leaf MR (a merged branch with no MRs inside it) -> the net change from the branch
    start (merge-base of the merge's parents) to the branch tip;
  * a parent MR (a merged branch that contains MRs) -> its direct commits netted per run
    between the merges on its spine, each run based at the preceding synced base; every
    child MR recurses, and a merge that only syncs the parent/main branch in is skipped.
A merge is never scored as its own diff, so a long-running roll-up cannot inflate things.

Each observation carries two metrics: composite = (Σ mutation + Σ godclass) * files, and
mutation = Σ mutation. The distribution of these over all observations is the baseline.

Grading. A change's grade blends its percentile rank in this project distribution (n
observations) with its rank against the per-language seed table, weighting the project by
  w = n / (n + K)
so a shallow history leans on the seed and a deep one trusts itself. K is curve_prior_weight.
"""
from __future__ import annotations

import bisect
import json
import re
from dataclasses import dataclass, field

from . import gitio
from .core.config import MeasureConfig
from .core.gitplumb import GitRepo
from .data import load_defaults, rank_in_table, seed_table
from .engine import score_change

# curve metric -> the ChangeScore attribute that carries it.
METRIC_ATTR = {"composite": "impact", "mutation": "mutation"}

_BD = load_defaults().get("baseline", {})


# --------------------------------------------------------------------------- model

@dataclass
class Baseline:
    """The project's per-metric per-observation distributions (each ascending)."""
    n: int
    values: dict[str, list[int]] = field(default_factory=dict)
    head: str | None = None
    base_ref: str | None = None

    def rank(self, metric: str, value: float) -> float:
        return _percentile_rank(self.values.get(metric, []), value)

    def to_dict(self) -> dict:
        return {"_meta": {"tool": "impact-gate", "n": self.n, "head": self.head,
                          "base_ref": self.base_ref},
                "metrics": self.values}

    @classmethod
    def from_dict(cls, d: dict) -> "Baseline":
        meta = d.get("_meta", {})
        values = {k: [int(v) for v in vs] for k, vs in (d.get("metrics") or {}).items()}
        n = int(meta.get("n", len(next(iter(values.values()), []))))
        return cls(n=n, values=values, head=meta.get("head"),
                   base_ref=meta.get("base_ref"))


def _percentile_rank(sorted_vals: list[int], value: float) -> float:
    """Percentile rank of `value` in an ascending list: fraction below plus half the
    ties, in [0, 100]. Above every observation -> 100; at or below the smallest -> ~0."""
    n = len(sorted_vals)
    if n == 0:
        return 0.0
    lo = bisect.bisect_left(sorted_vals, value)
    hi = bisect.bisect_right(sorted_vals, value)
    return round((lo + 0.5 * (hi - lo)) / n * 100, 2)


# ----------------------------------------------------------------------- the walk

def build_baseline(repo_path: str, mcfg: MeasureConfig | None = None, *,
                   base_ref: str | None = None, max_commits: int | None = None,
                   exclude_subject_pattern: str | None = None) -> Baseline:
    """Walk the merged history of `base_ref` into the project's impact distribution."""
    mcfg = mcfg or MeasureConfig()
    base_ref = base_ref or _BD.get("base_ref") or "HEAD"
    if max_commits is None:
        max_commits = _BD.get("max_commits")
    if exclude_subject_pattern is None:
        exclude_subject_pattern = _BD.get("exclude_subject_pattern")
    pat = re.compile(exclude_subject_pattern) if exclude_subject_pattern else None

    parents = gitio.rev_parents(repo_path, base_ref)
    mainline = gitio.mainline_commits(repo_path, base_ref, max_commits)
    repo = GitRepo(repo_path)
    comp: list[int] = []
    mut: list[int] = []
    seen: set[str] = set()

    def emit(old_rev: str, new_rev: str) -> None:
        score = score_change(gitio.diff_between(repo, old_rev, new_rev), mcfg)
        if score.empty:
            return
        comp.append(score.impact)
        mut.append(score.mutation)

    def walk_mr(merge_sha: str, p1: str, tip: str) -> None:
        if merge_sha in seen:
            return
        seen.add(merge_sha)
        if pat and pat.search(gitio.commit_subject(repo_path, merge_sha)):
            return  # naming-convention exclusion: skip this MR entirely
        start = gitio.merge_base(repo_path, p1, tip) or p1
        spine = gitio.first_parent_spine(repo_path, start, tip)
        base = start
        for c in reversed(spine):                       # oldest first, along the branch
            cps = parents.get(c) or gitio.rev_parents(repo_path, c).get(c, [])
            if len(cps) < 2:
                continue                                # direct commit: extends the run
            prev = cps[0]                               # branch state just before this merge
            if prev != base:
                emit(base, prev)                        # net of the run of direct commits
            for sec in cps[1:]:
                if gitio.is_ancestor(repo_path, sec, p1):
                    continue                            # a sync of parent/main: already counted
                walk_mr(c, cps[0], sec)                 # a child MR: recurse
            base = c                                    # advance past the merge
        if base != tip:
            emit(base, tip)                             # final run up to the branch tip

    try:
        for c in mainline:
            ps = parents.get(c, [])
            if len(ps) >= 2:                            # an MR landed on the mainline
                for sec in ps[1:]:
                    walk_mr(c, ps[0], sec)
            else:                                       # a direct commit on the mainline
                emit(ps[0] if ps else gitio.EMPTY_TREE, c)
    finally:
        repo.close()

    comp.sort()
    mut.sort()
    return Baseline(n=len(comp), values={"composite": comp, "mutation": mut},
                    head=gitio.head_sha(repo_path, base_ref), base_ref=base_ref)


# ------------------------------------------------------------------- persistence

def save_baseline(baseline: Baseline, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(baseline.to_dict(), fh, indent=1)


def load_baseline(path: str) -> Baseline | None:
    """The cached baseline at `path`, or None if it is missing or unreadable."""
    try:
        with open(path, encoding="utf-8") as fh:
            return Baseline.from_dict(json.load(fh))
    except (OSError, ValueError):
        return None


# ------------------------------------------------------------------------ grading

@dataclass
class Grade:
    percentile: float            # the blended grade, 0..100
    metric: str
    value: int
    seed_percentile: float       # rank against the shipped per-language seed
    project_percentile: float | None   # rank against project history (None at cold start)
    weight: float                # w = n / (n + K): the project's share of the blend
    n: int                       # project observations behind the grade
    language: str | None


def dominant_language(score) -> str | None:
    """The language driving the change (highest-cost file), else None -> pooled seed."""
    best, best_cost = None, -1
    for f in score.files:
        if f.lang and f.cost > best_cost:
            best, best_cost = f.lang, f.cost
    return best


def grade_value(value: int, *, metric: str, language: str | None,
                baseline: Baseline | None, prior_weight_K: float) -> Grade:
    seed_pct, seed_vals = seed_table(language)
    seed_rank = rank_in_table(value, seed_pct, seed_vals)
    n = baseline.n if baseline else 0
    if n <= 0:
        return Grade(seed_rank, metric, value, seed_rank, None, 0.0, 0, language)
    project_rank = baseline.rank(metric, value)
    denom = n + prior_weight_K
    w = n / denom if denom > 0 else 1.0
    blended = round(w * project_rank + (1 - w) * seed_rank, 2)
    return Grade(blended, metric, value, round(seed_rank, 2), round(project_rank, 2),
                 round(w, 4), n, language)


def grade_change(score, *, metric: str = "composite", baseline: Baseline | None = None,
                 prior_weight_K: float = 200) -> Grade:
    """Grade a scored change by blending its project and seed percentile ranks."""
    value = getattr(score, METRIC_ATTR[metric])
    return grade_value(value, metric=metric, language=dominant_language(score),
                       baseline=baseline, prior_weight_K=prior_weight_K)
