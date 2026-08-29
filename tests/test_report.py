"""The driver tables name the containing class (text and markdown)."""
from impact_gate.config import GateConfig
from impact_gate.engine import ChangeScore, UnitScore
from impact_gate import report


def _score(units):
    return ChangeScore(files_changed=1, mutation=0, godclass=999, impact=999,
                       files=[], units=units)


CLASSED = UnitScore("Owner.java", "Owner::c", "Owner", 4, 5, 500, "godclass")
FREE = UnitScore("util.py", "helper", "", 2, 0, 6, "godclass")


def _render(fn, units):
    cfg = GateConfig(warn_at=1)
    s = _score(units)
    return fn(s, cfg, cfg.level(s.impact), "worktree", "main", False)


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
