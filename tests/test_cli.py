"""Layer 3: CLI and gate behavior. Calls cli.main and checks exit code + output."""
import json

from impact_gate.cli import main
from gitutil import commit, write

BASE = "def f():\n    return 1\n"
CHANGED = "def f():\n    return 1\n\ndef g():\n    return 2\n"


def _prepare(repo):
    write(repo, "m.py", BASE)
    commit(repo, "base")
    write(repo, "m.py", CHANGED)              # worktree change, impact == 2


def test_block_mode_returns_exit_2(repo, capsys):
    _prepare(repo)
    code = main(["score", "--repo", str(repo), "--mode", "worktree",
                 "--block-at", "1", "--enforcement", "block"])
    assert code == 2
    assert "[BLOCK]" in capsys.readouterr().out


def test_warn_mode_allows_but_reports(repo, capsys):
    _prepare(repo)
    code = main(["score", "--repo", str(repo), "--mode", "worktree",
                 "--warn-at", "1", "--enforcement", "warn"])
    assert code == 0
    assert "[WARN]" in capsys.readouterr().out


def test_tolerance_lifts_threshold(repo, capsys):
    _prepare(repo)
    code = main(["score", "--repo", str(repo), "--mode", "worktree",
                 "--block-at", "1", "--enforcement", "block", "--tolerance", "1000000"])
    assert code == 0                          # effective block far above the impact
    assert "[OK]" in capsys.readouterr().out


def test_empty_change_exits_zero(repo, capsys):
    write(repo, "m.py", BASE)
    commit(repo, "base")
    code = main(["score", "--repo", str(repo), "--mode", "staged"])   # nothing staged
    assert code == 0
    assert "no source changes" in capsys.readouterr().out


def test_json_output_shape(repo, capsys):
    _prepare(repo)
    code = main(["score", "--repo", str(repo), "--mode", "worktree", "--format", "json"])
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["impact"] == 2
    assert data["files_changed"] == 1
    assert set(("impact", "level", "blocked", "mode", "thresholds")) <= data.keys()


def test_markdown_output(repo, capsys):
    _prepare(repo)
    code = main(["score", "--repo", str(repo), "--mode", "worktree",
                 "--format", "markdown", "--warn-at", "1"])
    out = capsys.readouterr().out
    assert code == 0
    assert "## Change impact: 2" in out
    assert "| metric | value |" in out
    assert "Top cost drivers" in out          # warn level shows drivers


def test_bad_base_returns_exit_1(repo, capsys):
    write(repo, "m.py", BASE)
    commit(repo, "base")
    code = main(["score", "--repo", str(repo), "--mode", "range", "--base", "nope"])
    assert code == 1
    assert "merge-base" in capsys.readouterr().err
