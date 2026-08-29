"""The baseline history walk, the empirical-Bayes blend, and persistence.

The walk's unit is one atomic landed change. The fixture below lands, in order:
  m1, m2                  two direct commits on main
  feat1 (f1, f2)          a leaf MR (a branch with no MRs inside it)
  feat2                   a parent MR: a direct commit (p1), a child MR (child2 -> c1),
                          then another direct commit (p2)
so the expected observations are exactly:
  m1, m2, feat1-net, feat2 run-before-child (p1), child2 (c1), feat2 run-after-child (p2)
= six. The three merge commits are never scored as their own diff.
"""
from gitutil import cc_func, commit, git, init_repo, write

from impact_gate import baseline
from impact_gate.baseline import Baseline, grade_value


def _co(repo, *args):
    git(repo, "checkout", "-q", *args)


def _merge(repo, branch, msg):
    git(repo, "merge", "-q", "--no-ff", "-m", msg, branch)


def _history(tmp_path):
    repo = init_repo(tmp_path / "proj")
    write(repo, "app.py", cc_func("a", 3))
    commit(repo, "m1")
    write(repo, "app.py", cc_func("a", 3) + cc_func("b", 4))
    commit(repo, "m2")

    _co(repo, "-b", "feat1")                       # leaf MR
    write(repo, "feature.py", cc_func("x", 2))
    commit(repo, "f1")
    write(repo, "feature.py", cc_func("x", 2) + cc_func("y", 3))
    commit(repo, "f2")
    _co(repo, "main")
    _merge(repo, "feat1", "Merge feat1")

    _co(repo, "-b", "feat2")                       # parent MR
    write(repo, "mod.py", cc_func("p", 3))
    commit(repo, "p1")                             # direct run before the child MR
    _co(repo, "-b", "child2")                      # child MR
    write(repo, "child.py", cc_func("c", 2))
    commit(repo, "c1")
    _co(repo, "feat2")
    _merge(repo, "child2", "Merge child2")
    write(repo, "mod.py", cc_func("p", 3) + cc_func("q", 2))
    commit(repo, "p2")                             # direct run after the child MR
    _co(repo, "main")
    _merge(repo, "feat2", "Merge feat2")
    return repo


def test_walk_counts_atomic_changes_not_merges(tmp_path):
    repo = _history(tmp_path)
    bl = baseline.build_baseline(str(repo), base_ref="main")
    # Six atomic changes; the three merge commits contribute no observation of their own.
    assert bl.n == 6
    assert len(bl.values["composite"]) == 6
    assert len(bl.values["mutation"]) == 6
    assert all(v > 0 for v in bl.values["composite"])
    assert bl.values["composite"] == sorted(bl.values["composite"])


def test_subject_pattern_excludes_an_mr(tmp_path):
    repo = _history(tmp_path)
    full = baseline.build_baseline(str(repo), base_ref="main")
    # Excluding the parent MR by its merge subject drops it and its child MR: the run
    # before the child (p1), the child (c1) and the run after (p2) all go -> 3 fewer.
    trimmed = baseline.build_baseline(str(repo), base_ref="main",
                                      exclude_subject_pattern=r"Merge feat2")
    assert trimmed.n == full.n - 3


def test_percentile_rank_endpoints_and_middle():
    bl = Baseline(n=5, values={"composite": [10, 20, 30, 40, 50]})
    assert bl.rank("composite", 5) == 0.0        # below all
    assert bl.rank("composite", 100) == 100.0    # above all
    assert bl.rank("composite", 30) == 50.0      # the median value


def test_cold_start_grade_is_pure_seed():
    g = grade_value(500, metric="composite", language="python",
                    baseline=None, prior_weight_K=200)
    assert g.project_percentile is None
    assert g.weight == 0.0
    assert g.percentile == g.seed_percentile


def test_blend_weights_project_by_n_over_n_plus_k():
    bl = Baseline(n=100, values={"composite": [1] * 99 + [10_000]})
    # value 5000 sits above the 99 low observations, below the single high one, with no
    # ties -> project rank 99.0.
    g = grade_value(5000, metric="composite", language="python",
                    baseline=bl, prior_weight_K=100)
    assert g.weight == 0.5                        # n/(n+K) = 100/200
    assert g.project_percentile == 99.0
    expected = round(0.5 * 99.0 + 0.5 * g.seed_percentile, 2)
    assert g.percentile == expected


def test_persistence_round_trip(tmp_path):
    repo = _history(tmp_path)
    bl = baseline.build_baseline(str(repo), base_ref="main")
    path = str(tmp_path / "baseline.json")
    baseline.save_baseline(bl, path)
    back = baseline.load_baseline(path)
    assert back is not None
    assert back.n == bl.n
    assert back.values == bl.values
    assert baseline.load_baseline(str(tmp_path / "missing.json")) is None
