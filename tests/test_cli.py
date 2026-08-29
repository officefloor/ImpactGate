"""Layer 3: CLI and gate behavior. Calls cli.main and checks exit code + output."""
import json
import os

from impact_gate.cli import main
from gitutil import cc_func, commit, write

BASE = "def f():\n    return 1\n"
CHANGED = "def f():\n    return 1\n\ndef g():\n    return 2\n"


def _prepare(repo):
    write(repo, "m.py", BASE)
    commit(repo, "base")
    write(repo, "m.py", CHANGED)              # worktree change, impact == 2


def _history(repo):
    """Three landed commits on main -> three baseline observations."""
    write(repo, "a.py", cc_func("a", 3)); commit(repo, "m1")
    write(repo, "a.py", cc_func("a", 3) + cc_func("b", 4)); commit(repo, "m2")
    write(repo, "b.py", cc_func("c", 5)); commit(repo, "m3")


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
    assert "| field | value |" in out
    assert "Top cost drivers" in out          # warn level shows drivers


def test_bad_base_returns_exit_1(repo, capsys):
    write(repo, "m.py", BASE)
    commit(repo, "base")
    code = main(["score", "--repo", str(repo), "--mode", "range", "--base", "nope"])
    assert code == 1
    assert "merge-base" in capsys.readouterr().err


# --------------------------------------------------------------- baseline command

def test_baseline_command_writes_cache(repo, capsys):
    _history(repo)
    code = main(["baseline", "--repo", str(repo)])
    assert code == 0
    assert "baseline written" in capsys.readouterr().out
    data = json.load(open(os.path.join(str(repo), ".impact-gate-baseline.json")))
    assert data["_meta"]["n"] == 3                       # three landed commits
    assert len(data["distribution"]) == 3
    assert data["distribution"] == sorted(data["distribution"])   # ascending on disk


def test_baseline_command_honours_baseline_file_flag(repo, capsys):
    _history(repo)
    code = main(["baseline", "--repo", str(repo), "--baseline-file", "custom.json"])
    assert code == 0
    assert os.path.exists(os.path.join(str(repo), "custom.json"))


def test_baseline_command_on_empty_history_errs_cleanly(repo, capsys):
    # Fresh repo, no commits on main: a friendly error and exit 1, never a traceback.
    code = main(["baseline", "--repo", str(repo)])
    assert code == 1
    assert "impact-gate:" in capsys.readouterr().err


# ------------------------------------------------------------------ percentile gate

def test_curve_gate_blocks_a_high_grade_change(repo, capsys):
    _history(repo)
    main(["baseline", "--repo", str(repo)])
    capsys.readouterr()
    # A large change grades high on the curve; block enforcement fails it.
    write(repo, "big.py", "".join(cc_func(n, 30) for n in "abcdefgh"))
    code = main(["score", "--repo", str(repo), "--mode", "worktree", "--curve",
                 "--enforcement", "block",
                 "--warn-percentile", "40", "--block-percentile", "60"])
    out = capsys.readouterr().out
    assert code == 2
    assert "[BLOCK]" in out
    assert "grade:" in out


def test_curve_low_change_passes_and_reports_the_grade(repo, capsys):
    _history(repo)
    main(["baseline", "--repo", str(repo)])
    capsys.readouterr()
    write(repo, "b.py", cc_func("c", 5) + cc_func("z", 2))    # small addition
    code = main(["score", "--repo", str(repo), "--mode", "worktree", "--curve",
                 "--format", "json"])
    data = json.loads(capsys.readouterr().out)
    assert code == 0
    assert data["curve"] is True
    assert data["blocked"] is False
    assert data["grade"]["n"] == 3                       # blended against the baseline
    assert data["grade"]["language"] == "python"
    assert 0 <= data["grade"]["percentile"] <= 100


def test_curve_without_baseline_grades_on_seed_only(repo, capsys):
    _prepare(repo)                                        # no baseline file built
    code = main(["score", "--repo", str(repo), "--mode", "worktree", "--curve",
                 "--format", "json"])
    data = json.loads(capsys.readouterr().out)
    assert code == 0
    assert data["grade"]["n"] == 0
    assert data["grade"]["project_percentile"] is None   # pure seed at cold start
    assert data["grade"]["percentile"] == data["grade"]["seed_percentile"]
