"""Bulk-commit guard: source files whose diff exceeds max_diff_lines are skipped from
the score (not counted, not parsed) and surfaced separately."""
import json

from impact_gate.config import GateConfig
from impact_gate.core.config import MeasureConfig
from impact_gate.engine import ChangedFile, score_change
from impact_gate import report


def _added_file(path, body, added_lines):
    return ChangedFile(path=path, status="A", before=None, after=body.encode(),
                       added=[(1, added_lines)], removed=[])


def test_oversized_file_is_skipped_not_scored():
    body = "".join(f"def f{i}(x):\n    return {i}\n" for i in range(50))  # real fns
    c = _added_file("gen.py", body, added_lines=300)
    s = score_change([c], MeasureConfig(max_diff_lines=100))
    assert s.files_changed == 0
    assert s.impact == 0
    assert [sk.path for sk in s.skipped] == ["gen.py"]
    assert s.skipped[0].diff_lines == 300
    assert not s.empty                     # a skipped-only change is not "no changes"


def test_file_at_or_under_limit_is_scored():
    body = "def f(x):\n    if x:\n        return 1\n    return 0\n"
    c = _added_file("a.py", body, added_lines=100)   # == limit, kept
    s = score_change([c], MeasureConfig(max_diff_lines=100))
    assert s.files_changed == 1
    assert not s.skipped
    assert s.impact > 0


def test_guard_off_when_limit_zero():
    body = "def f(x):\n    return 1\n"
    c = _added_file("a.py", body, added_lines=10_000_000)
    s = score_change([c], MeasureConfig(max_diff_lines=0))   # 0 disables the guard
    assert not s.skipped
    assert s.files_changed == 1


def test_mixed_change_scores_small_skips_large():
    small = _added_file("small.py", "def f(x):\n    return 1\n", added_lines=5)
    big = _added_file("dump.py", "def g(x):\n    return 2\n", added_lines=500)
    s = score_change([small, big], MeasureConfig(max_diff_lines=100))
    assert s.files_changed == 1
    assert {f.path for f in s.files} == {"small.py"}
    assert [sk.path for sk in s.skipped] == ["dump.py"]


def test_skip_is_reported_in_all_formats():
    body = "def f(x):\n    return 1\n"
    s = score_change([_added_file("dump.py", body, 500)],
                     MeasureConfig(max_diff_lines=100))
    cfg = GateConfig()
    text = report.render_text(s, cfg, "ok", "staged", "main", False)
    assert "skipped 1 oversized file" in text and "dump.py" in text
    md = report.render_markdown(s, cfg, "ok", "staged", "main", False)
    assert "Skipped: oversized files" in md and "`dump.py`" in md
    data = json.loads(report.render_json(s, cfg, "ok", "staged", "main", False))
    assert data["skipped"] == [{"path": "dump.py", "diff_lines": 500}]
