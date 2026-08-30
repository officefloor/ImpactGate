"""Ports and adapters for where the grade and the policy come from.

The gate logic depends only on two ports, never on files or HTTP directly:

  GradeProvider   grade a change against a distribution, and publish a rebuilt baseline.
  PolicyProvider  supply the gate policy (thresholds, enforcement, curve knobs).

Today the only adapters are local: a JSON baseline file on disk and an .impact-gate.yml.
A remote adapter (a hosted store + config service) implements the same two ports, so the
CLI and the CI plugins do not change when a team moves from the file to the service. The
choice of adapter lives in `select_*_provider`; everything above the ports is
storage-agnostic.

Contract rules every adapter must honour, so the merge path stays safe:
  * grade() returns None when the backend is unreachable. The caller then falls back to
    the shipped seed (a grade with no project baseline), never a hard failure of the gate.
  * the verdict (warn / block, exit code) is always computed by the caller from the
    policy, never by the provider. A provider informs the gate; it never *is* the gate.
  * a remote grade should be reproducible after the fact: record which baseline head /
    version produced it (a field to add to Grade when the remote adapter lands).

REMOTE API CONTRACT (for the future hosted adapter; not implemented yet):
  POST {base}/v1/grade         {repo, value, language}           -> Grade JSON
  PUT  {base}/v1/baseline      {repo, distribution:[...], head}  -> replace the baseline
  POST {base}/v1/observations  {repo, from_head, observations}   -> incremental append
  Auth: `Authorization: Bearer <token>`. Identity: the `repo` id, configured per project.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

from .baseline import (Baseline, Grade, dominant_language, grade_value,
                       load_baseline, save_baseline)
from .config import GateConfig
from .engine import ChangeScore


@dataclass
class ChangeSummary:
    """The storage-agnostic description of a change that a grade needs. Deliberately tiny:
    this is all a remote grade endpoint ever receives — a number and a language, never the
    diff or the source."""
    value: int               # composite impact to grade
    language: str | None     # dominant language; selects the seed table (None -> pooled)

    @classmethod
    def of(cls, score: ChangeScore) -> "ChangeSummary":
        return cls(value=score.impact, language=dominant_language(score))


class GradeProvider(Protocol):
    """Where a change's grade comes from, and where a rebuilt baseline is stored."""

    def grade(self, change: ChangeSummary, repo_id: str) -> Grade | None:
        """Grade `change` against the distribution for `repo_id`. None means the backend
        is unavailable, and the caller falls back to the shipped seed."""
        ...

    def publish(self, repo_id: str, baseline: Baseline) -> None:
        """Replace the stored baseline for `repo_id` with a freshly built one."""
        ...


class PolicyProvider(Protocol):
    """Where the gate policy (thresholds, enforcement, curve knobs) comes from."""

    def policy(self, repo_id: str) -> GateConfig:
        ...


# ------------------------------------------------------------------- local adapters

_UNSET = object()


class LocalGradeProvider:
    """Grades against the shipped seed blended with a JSON baseline file on disk."""

    def __init__(self, path: str | None, prior_weight_K: float):
        self.path = path
        self.prior_weight_K = prior_weight_K
        self._baseline = _UNSET      # loaded lazily; publish() sets it without a read

    @property
    def baseline(self) -> Baseline | None:
        if self._baseline is _UNSET:
            self._baseline = load_baseline(self.path) if self.path else None
        return self._baseline

    def grade(self, change: ChangeSummary, repo_id: str | None = None) -> Grade:
        # Never None: with no baseline file this is a pure-seed grade, which is exactly the
        # fallback a remote adapter degrades to.
        return grade_value(change.value, language=change.language,
                           baseline=self.baseline, prior_weight_K=self.prior_weight_K)

    def publish(self, repo_id: str | None, baseline: Baseline) -> None:
        if not self.path:
            raise ValueError("no baseline_file configured to publish to")
        save_baseline(baseline, self.path)
        self._baseline = baseline


class LocalPolicyProvider:
    """Reads the gate policy from an .impact-gate.yml (or the built-in defaults)."""

    def __init__(self, config_path: str | None, repo_path: str):
        self.config_path = config_path
        self.repo_path = repo_path

    def policy(self, repo_id: str | None = None) -> GateConfig:
        return GateConfig.load(self.config_path, self.repo_path)


# -------------------------------------------------------------- remote adapters (stubs)

class RemoteGradeProvider:
    """Contract stub for the hosted grade store. Not implemented yet: grade() reports the
    backend as unavailable (so the gate falls back to the shipped seed) and publish()
    refuses rather than silently dropping data. See the REMOTE API CONTRACT above."""

    def __init__(self, base_url: str, token: str | None = None):
        self.base_url = base_url
        self.token = token

    def grade(self, change: ChangeSummary, repo_id: str) -> Grade | None:
        return None      # unavailable -> the caller uses the shipped-seed fallback

    def publish(self, repo_id: str, baseline: Baseline) -> None:
        raise NotImplementedError("remote grade store not implemented yet")


class RemotePolicyProvider:
    """Contract stub for hosted, centrally governed policy. Not implemented yet."""

    def __init__(self, base_url: str, token: str | None = None):
        self.base_url = base_url
        self.token = token

    def policy(self, repo_id: str) -> GateConfig:
        raise NotImplementedError("remote policy service not implemented yet")


# --------------------------------------------------------------- selection + fallback

def select_grade_provider(repo_path: str, baseline_file: str,
                          prior_weight_K: float) -> GradeProvider:
    """The grade adapter for this run. Local file today; the extension point for a hosted
    store is here (e.g. return a RemoteGradeProvider when a baseline API is configured)."""
    return LocalGradeProvider(os.path.join(repo_path, baseline_file), prior_weight_K)


def select_policy_provider(config_path: str | None, repo_path: str) -> PolicyProvider:
    """The policy adapter for this run. Local .impact-gate.yml today; the extension point
    for hosted, centrally governed policy is here."""
    return LocalPolicyProvider(config_path, repo_path)


def seed_grade(score: ChangeScore, prior_weight_K: float) -> Grade:
    """The shipped-seed-only grade — the safe fallback when a remote provider is
    unreachable. No project baseline, so `w = 0` and the grade is the pure seed rank."""
    return LocalGradeProvider(None, prior_weight_K).grade(ChangeSummary.of(score))
