"""Layer 4: the headline property. Accreting onto heavy code costs far more than
adding the same code as an isolated new file. If this holds, the gate measures
structural decay, not just size."""
from gitutil import cc_func, commit, git, score, write


def test_accretion_costs_far_more_than_isolated_addition(repo):
    heavy = "\n".join(cc_func(f"fn{i}", 4) for i in range(5)) + "\n"   # 5 funcs, CC 5 each
    write(repo, "app.py", heavy)
    commit(repo, "base")

    # (1) Accretion: add a new function into the heavy module.
    write(repo, "app.py", heavy + cc_func("newfn", 2))
    accretion = score(repo, mode="worktree")
    git(repo, "checkout", "--", "app.py")            # discard the edit

    # (2) Isolated: the same new function as its own new file.
    write(repo, "feature.py", cc_func("newfn", 2))
    isolated = score(repo, mode="worktree")

    assert accretion.files_changed == isolated.files_changed == 1
    assert accretion.impact > isolated.impact * 5    # decay is far more expensive
