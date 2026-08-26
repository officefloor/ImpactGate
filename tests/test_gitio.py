"""Layer 2: git resolution for each mode, over a real temp repo."""
import pytest

from impact_gate.gitio import DiffError, changed_files
from gitutil import commit, score, stage, write

BASE = "def f():\n    return 1\n"
CHANGED = "def f():\n    return 1\n\ndef g():\n    return 2\n"


def test_range_mode_scores_committed_branch(repo):
    write(repo, "m.py", BASE)
    commit(repo, "base")
    write(repo, "m.py", CHANGED)
    commit(repo, "add g")
    s = score(repo, mode="range", base="HEAD~1")
    assert s.files_changed == 1
    assert s.impact > 0


def test_staged_mode_scores_the_index(repo):
    write(repo, "m.py", BASE)
    commit(repo, "base")
    stage(repo, "m.py", CHANGED)              # staged, not committed
    s = score(repo, mode="staged")
    assert s.files_changed == 1
    assert s.impact > 0


def test_worktree_mode_scores_uncommitted_edits(repo):
    write(repo, "m.py", BASE)
    commit(repo, "base")
    write(repo, "m.py", CHANGED)              # edited, not staged
    assert score(repo, mode="staged").empty   # nothing staged
    assert score(repo, mode="worktree").impact > 0


def test_no_merge_base_raises_diff_error(repo):
    write(repo, "m.py", BASE)
    commit(repo, "base")
    with pytest.raises(DiffError):
        changed_files(str(repo), "range", "nonexistent-branch")


def test_non_source_change_scores_empty(repo):
    write(repo, "README.md", "# hi\n")
    commit(repo, "base")
    write(repo, "README.md", "# hi\n\nmore words\n")
    assert score(repo, mode="worktree").empty
