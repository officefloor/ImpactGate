"""The driver tables name the containing class (text and markdown), and the report
ranks the files to consider for refactoring by their change-impact cost."""
import json

from impact_gate.config import GateConfig
from impact_gate.engine import ChangeScore, FileScore, UnitScore
from impact_gate import report


def _score(units, files=None):
    return ChangeScore(files_changed=len(files) if files else 1, mutation=0,
                       godclass=999, impact=999, files=files or [], units=units)


CLASSED = UnitScore("Owner.java", "Owner::c", "Owner", 4, 5, 500, "godclass")
FREE = UnitScore("util.py", "helper", "", 2, 0, 6, "godclass")


def _render(fn, units, files=None):
    cfg = GateConfig(warn_at=1)
    s = _score(units, files)
    return fn(s, cfg, cfg.level(s.impact), "worktree", "main", False)


# A god-class file (heavy new code) and a lighter modification, in ranked order.
GODCLASS = FileScore("big.py", "python", mutation=100, godclass=900, mut_fns=1, new_fns=8)
SMALL = FileScore("small.py", "python", mutation=40, godclass=0, mut_fns=2, new_fns=0)
CLEAN = FileScore("clean.py", "python", mutation=0, godclass=0, mut_fns=0, new_fns=0)


def test_text_names_the_class_and_collapses_the_qualifier():
    out = _render(report.render_text, [CLASSED])
    assert "Owner.java:c" in out          # method shown short, not "Owner::c"
    assert "in Owner" in out              # the containing class is named
    assert "Owner::c" not in out          # qualifier not duplicated


def test_text_labels_file_scope_for_free_functions():
    out = _render(report.render_text, [FREE])
    assert "util.py:helper" in out
    assert "file scope" in out


def test_markdown_has_a_class_column():
    out = _render(report.render_markdown, [CLASSED, FREE])
    assert "| cost | location | class | CC | WMC_other | kind |" in out
    assert "`Owner.java:c` | `Owner` |" in out       # class in its own column
    assert "`util.py:helper` | _file scope_ |" in out


def test_text_ranks_files_to_consider_by_cost():
    out = _render(report.render_text, [], [GODCLASS, SMALL])
    assert "Files to consider for refactoring" in out
    # The god-class file (cost 1000) ranks above the small modification (cost 40), and its
    # new functions are reported so an added-code god class is visible as such.
    assert out.index("big.py") < out.index("small.py")
    assert "8 new" in out


def test_zero_cost_files_are_not_listed():
    out = _render(report.render_text, [], [CLEAN])
    assert "Files to consider for refactoring" not in out


def test_markdown_lists_the_files_table():
    out = _render(report.render_markdown, [], [GODCLASS, SMALL])
    assert "### Files to consider for refactoring" in out
    assert "| cost | file | existing | new | fns changed | fns new |" in out
    assert "`big.py`" in out


def test_json_drops_change_level_mutation_but_keeps_per_file_breakdown():
    out = _render(report.render_json, [], [GODCLASS])
    data = json.loads(out)
    assert "mutation" not in data and "godclass" not in data   # no rival change metric
    assert data["files"][0]["cost"] == 1000                    # ranking is per file
    assert data["files"][0]["new_fns"] == 8
