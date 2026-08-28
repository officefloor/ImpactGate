"""The shipped-data loader, its schema validation, and the config knobs it feeds."""
import pytest

from impact_gate import data
from impact_gate.config import GateConfig


def test_defaults_shape():
    d = data.load_defaults()
    assert d["enforcement"] in ("off", "warn", "block")
    assert d["curve"]["warn_percentile"] < d["curve"]["block_percentile"]
    assert d["curve"]["prior_weight_K"] >= 0


def test_seed_percentiles_validate_and_load():
    seed = data.load_seed_percentiles()          # raises if the shipped table is malformed
    pct = seed["percentiles"]
    assert pct == sorted(pct) and 0 < pct[0] and pct[-1] < 100
    assert seed["pooled"] is not None


def test_seed_table_falls_back_to_pooled():
    pct, pooled = data.seed_table("no-such-language")
    _, py = data.seed_table("python")
    _, pooled_direct = data.seed_table(None)
    assert pooled == pooled_direct              # unknown lang -> pooled
    assert py != pooled                          # a known lang has its own table


def test_rank_in_table_is_monotonic_and_bounded():
    pct = [50.0, 90.0, 99.0]
    vals = [100.0, 1000.0, 10000.0]
    assert data.rank_in_table(0, pct, vals) == 0.0
    assert data.rank_in_table(100, pct, vals) == 50.0       # exactly the 50th point
    assert data.rank_in_table(1000, pct, vals) == 90.0      # exactly the 90th point
    mid = data.rank_in_table(550, pct, vals)                 # between 50th and 90th
    assert 50.0 < mid < 90.0
    tail = data.rank_in_table(1_000_000, pct, vals)          # far above the top point
    assert 99.0 < tail < 100.0                               # approaches but never hits 100


def test_gateconfig_defaults_come_from_json():
    cfg = GateConfig()
    d = data.load_defaults()
    assert cfg.warn_percentile == d["curve"]["warn_percentile"]
    assert cfg.block_percentile == d["curve"]["block_percentile"]
    assert cfg.curve_prior_weight == d["curve"]["prior_weight_K"]
    assert cfg.curve_enabled == d["curve"]["enabled"]


def test_validate_rejects_bad_curve_knobs():
    with pytest.raises(ValueError):
        GateConfig(metric="bogus").validate()
    with pytest.raises(ValueError):
        GateConfig(warn_percentile=0).validate()
    with pytest.raises(ValueError):
        GateConfig(warn_percentile=95, block_percentile=90).validate()
    with pytest.raises(ValueError):
        GateConfig(curve_prior_weight=-1).validate()


def test_config_file_overrides_curve_knobs(tmp_path):
    (tmp_path / ".impact-gate.yml").write_text(
        "curve_enabled: true\nwarn_percentile: 80\nblock_percentile: 95\n"
        "curve_prior_weight: 100\nmetric: mutation\n")
    cfg = GateConfig.load(repo_path=str(tmp_path))
    assert cfg.curve_enabled is True
    assert cfg.warn_percentile == 80 and cfg.block_percentile == 95
    assert cfg.curve_prior_weight == 100 and cfg.metric == "mutation"
