"""Layer 2: git resolution for each mode, over a real temp repo."""
import pytest

from impact_gate.gitio import DiffError, changed_files
from gitutil import commit, git, score, stage, write

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


def test_mnemonicprefix_config_does_not_break_scoring(repo):
    git(repo, "config", "diff.mnemonicprefix", "true")
    write(repo, "m.py", BASE)
    commit(repo, "base")
    stage(repo, "m.py", CHANGED)
    s = score(repo, mode="staged")
    assert s.files_changed == 1
    assert s.impact > 0


def test_non_ascii_and_spaced_filenames_are_scored(repo):
    write(repo, "café.py", BASE)
    write(repo, "my file.py", BASE)
    commit(repo, "base")
    stage(repo, "café.py", CHANGED)
    stage(repo, "my file.py", CHANGED)
    s = score(repo, mode="staged")
    assert s.files_changed == 2
    assert sorted(f.path for f in s.files) == ["café.py", "my file.py"]


def test_hunk_body_dash_line_does_not_corrupt_path(repo):
    base = "int widget(int counter) {\n    while (counter) {\n-- counter;\n    }\n    return counter;\n}\n"
    changed = "int widget(int counter) {\n    while (counter) {\n++ counter;\n    }\n    return counter;\n}\n"
    write(repo, "widget.c", base)
    commit(repo, "base")
    stage(repo, "widget.c", changed)
    s = score(repo, mode="staged")
    assert s.files_changed == 1
    assert [f.path for f in s.files] == ["widget.c"]


def test_worktree_mode_scores_untracked_non_ascii_file(repo):
    write(repo, "base.py", BASE)
    commit(repo, "base")
    write(repo, "café.py", CHANGED)
    s = score(repo, mode="worktree")
    assert s.files_changed == 1
    assert [f.path for f in s.files] == ["café.py"]
