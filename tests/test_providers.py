"""The provider seam: the local file/policy adapters, the remote stubs' contract, and
the selection + seed fallback that keep the gate storage-agnostic."""
import pytest

from impact_gate.baseline import Baseline
from impact_gate.config import GateConfig
from impact_gate.engine import ChangeScore, FileScore
from impact_gate import providers
from impact_gate.providers import (ChangeSummary, LocalGradeProvider,
                                   LocalPolicyProvider, RemoteGradeProvider,
                                   RemotePolicyProvider)


def _score(impact, files):
    return ChangeScore(files_changed=len(files), mutation=0, godclass=0,
                       impact=impact, files=files, units=[])


def test_change_summary_takes_value_and_dominant_language():
    score = _score(1234, [FileScore("a.py", "python", 10, 0, 1, 0),
                          FileScore("b.js", "javascript", 100, 0, 1, 0)])
    cs = ChangeSummary.of(score)
    assert cs.value == 1234
    assert cs.language == "javascript"          # the higher-cost file wins


def test_local_grade_provider_without_a_file_is_pure_seed():
    g = LocalGradeProvider(None, prior_weight_K=200).grade(ChangeSummary(500, "python"))
    assert g.project_percentile is None         # no project baseline
    assert g.weight == 0.0
    assert g.percentile == g.seed_percentile


def test_local_grade_provider_blends_a_published_baseline(tmp_path):
    path = str(tmp_path / "bl.json")
    prov = LocalGradeProvider(path, prior_weight_K=100)
    prov.publish("repo", Baseline(n=100, dist=[1] * 99 + [10_000]))
    g = prov.grade(ChangeSummary(5000, "python"))
    assert g.project_percentile == 99.0         # above the 99 low obs, below the high one
    assert g.n == 100
    assert 0.0 < g.weight < 1.0                  # blended, not pure seed


def test_publish_writes_the_file_and_updates_the_cache(tmp_path):
    from impact_gate.baseline import load_baseline
    path = str(tmp_path / "bl.json")
    prov = LocalGradeProvider(path, prior_weight_K=200)
    bl = Baseline(n=3, dist=[10, 20, 30])
    prov.publish("repo", bl)
    assert load_baseline(path).dist == [10, 20, 30]     # persisted
    assert prov.baseline.dist == [10, 20, 30]           # cached without a re-read


def test_publish_without_a_path_refuses():
    with pytest.raises(ValueError):
        LocalGradeProvider(None, 200).publish("repo", Baseline(n=1, dist=[1]))


def test_local_policy_provider_returns_a_gateconfig(tmp_path):
    (tmp_path / ".impact-gate.yml").write_text("enforcement: block\nwarn_at: 5\n")
    cfg = LocalPolicyProvider(None, str(tmp_path)).policy("repo")
    assert isinstance(cfg, GateConfig)
    assert cfg.enforcement == "block" and cfg.warn_at == 5


def test_remote_grade_stub_reports_unavailable_and_refuses_publish():
    rp = RemoteGradeProvider("https://example.test", token="t")
    assert rp.grade(ChangeSummary(1, "python"), "repo") is None   # -> seed fallback
    with pytest.raises(NotImplementedError):
        rp.publish("repo", Baseline(n=1, dist=[1]))


def test_remote_policy_stub_not_implemented():
    with pytest.raises(NotImplementedError):
        RemotePolicyProvider("https://example.test").policy("repo")


def test_selection_returns_local_adapters(tmp_path):
    gp = providers.select_grade_provider(str(tmp_path), ".impact-gate-baseline.json", 200)
    pp = providers.select_policy_provider(None, str(tmp_path))
    assert isinstance(gp, LocalGradeProvider)
    assert isinstance(pp, LocalPolicyProvider)
    assert gp.path.endswith(".impact-gate-baseline.json")         # repo path joined in


def test_seed_grade_helper_is_the_pure_seed_fallback():
    score = _score(500, [FileScore("a.py", "python", 500, 0, 1, 0)])
    g = providers.seed_grade(score, prior_weight_K=200)
    assert g.project_percentile is None
    assert g.percentile == g.seed_percentile
