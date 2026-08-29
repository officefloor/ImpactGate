"""Ignore rules, including the top-level vendored-dir fix."""
from impact_gate.core.config import MeasureConfig


def test_ignores_vendored_and_generated_at_any_depth():
    cfg = MeasureConfig()
    # Top-level (the bug): a repo-root vendor/ or node_modules/ must be ignored.
    assert cfg.is_ignored("vendor/foo.go")
    assert cfg.is_ignored("node_modules/x.js")
    assert cfg.is_ignored("third_party/y.cc")
    assert cfg.is_ignored("dist/app.min.js")
    # Nested (already worked): still ignored.
    assert cfg.is_ignored("pkg/vendor/foo.go")
    assert cfg.is_ignored("web/node_modules/x.js")
    # Top-level file patterns too.
    assert cfg.is_ignored("bundle.min.js")
    # Real source is not ignored.
    assert not cfg.is_ignored("src/main/App.java")
    assert not cfg.is_ignored("app.py")


def test_vendored_change_scores_empty():
    # A change confined to vendored code should contribute no impact.
    from impact_gate.engine import ChangedFile, score_change
    cf = ChangedFile("vendor/lib.go", "M", b"func f(){}\n", b"func f(){return}\n",
                     added=[(1, 1)], removed=[(1, 1)])
    assert score_change([cf]).empty
