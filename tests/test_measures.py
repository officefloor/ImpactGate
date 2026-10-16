"""The three measures run by default in warn, with per-measure enforcement overrides.

Covers the configuration contract (all on, all warn, nothing blocks until asked; block
turnable on globally or per measure; any measure switch-off-able) and that the coupling
section is rendered in every format when the coupling measure is on.
"""
import json

import pytest

from impact_gate import report
from impact_gate.config import ENFORCEMENTS, MEASURES, GateConfig
from impact_gate.engine import ChangeScore
from impact_gate.placement_check import Flag, has_vortex


def _score():
    # A non-empty score (files_changed > 0) so the renderers do not short-circuit.
    return ChangeScore(1, 0, 0, 5, [], [], [], 0, [])


def _coupling(vortex=True):
    return {
        "changed_functions": 3,
        "changed_files": 2,
        "method_vortex_flags": [Flag("svc/orchestrator.py", "dispatch", 42, "method")]
        if vortex else [],
        "class_vortex_files": ["svc/orchestrator.py"] if vortex else [],
        "tree_functions": 100,
    }


# --- configuration contract ---------------------------------------------------

def test_all_three_on_and_warn_by_default():
    cfg = GateConfig()
    for m in MEASURES:
        assert cfg.enabled(m) is True, m
        assert cfg.measure_mode(m) == "warn", m
    # warn means nothing fails the build, however high the signal
    assert cfg.blocks(10**9) is False
    assert cfg.blocks_cognitive(999) is False
    assert cfg.blocks_coupling(True) is False


def test_global_block_blocks_every_measure():
    cfg = GateConfig(enforcement="block", warn_at=1, block_at=1)
    assert cfg.blocks(100) is True
    assert cfg.blocks_cognitive(999) is True
    assert cfg.blocks_coupling(True) is True


def test_block_one_measure_selectively():
    # coupling blocks; the other two stay advisory
    cfg = GateConfig(coupling_enforcement="block", warn_at=1, block_at=1)
    assert cfg.blocks_coupling(True) is True
    assert cfg.blocks(100) is False
    assert cfg.blocks_cognitive(999) is False


def test_exempt_one_measure_from_a_global_block():
    # everything blocks except cognitive, which is pinned back to warn
    cfg = GateConfig(enforcement="block", cognitive_enforcement="warn",
                     warn_at=1, block_at=1)
    assert cfg.blocks(100) is True
    assert cfg.blocks_coupling(True) is True
    assert cfg.blocks_cognitive(999) is False


def test_switch_a_measure_off():
    cfg = GateConfig(coupling_enforcement="off")
    assert cfg.enabled("coupling") is False
    assert cfg.coupling_enabled() is False
    assert cfg.blocks_coupling(True) is False


def test_validate_rejects_bad_measure_enforcement():
    with pytest.raises(ValueError):
        GateConfig(coupling_enforcement="nope").validate()
    # null and any real enforcement are accepted
    for v in (None, *ENFORCEMENTS):
        GateConfig(cognitive_enforcement=v).validate()


# --- coupling rendering -------------------------------------------------------

def test_has_vortex_summary():
    assert has_vortex(_coupling(vortex=True)) is True
    assert has_vortex(_coupling(vortex=False)) is False


def test_text_shows_coupling_when_on():
    txt = report.render_text(_score(), GateConfig(), "ok", "worktree", "main", False,
                             coupling=_coupling())
    assert "Coupling divergence" in txt
    assert "dispatch" in txt


def test_text_hides_coupling_when_off():
    cfg = GateConfig(coupling_enforcement="off")
    txt = report.render_text(_score(), cfg, "ok", "worktree", "main", False,
                             coupling=_coupling())
    assert "Coupling divergence" not in txt


def test_json_coupling_section():
    out = json.loads(report.render_json(_score(), GateConfig(), "ok", "worktree", "main",
                                        False, coupling=_coupling()))
    assert out["coupling"]["has_vortex"] is True
    assert out["coupling"]["enforcement"] == "warn"
    assert out["coupling"]["method_vortices"][0]["name"] == "dispatch"
    # off -> omitted
    cfg_off = GateConfig(coupling_enforcement="off")
    out_off = json.loads(report.render_json(_score(), cfg_off, "ok", "worktree", "main",
                                            False, coupling=_coupling()))
    assert "coupling" not in out_off


def test_markdown_coupling_block_wording():
    cfg = GateConfig(coupling_enforcement="block")
    md = report.render_markdown(_score(), cfg, "block", "worktree", "main", True,
                                coupling=_coupling())
    assert "Coupling divergence" in md
    assert "fails the gate" in md
