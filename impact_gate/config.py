"""Gate configuration: thresholds, enforcement mode, CI-adjustable tolerance.

Resolved in layers (later wins): built-in defaults -> `.impact-gate.yml` in the repo
-> CLI flags / CI inputs. The built-in defaults are not literals here; they are read
from `impact_gate/data/defaults.json`, so tuning them is a data edit, not a code change.

Two gating modes coexist. Absolute: `warn_at` / `block_at` are raw composite-impact
numbers. Curve (`curve_enabled`): a change is graded by its percentile against the
blended seed + project distribution, and `warn_percentile` / `block_percentile` gate on
that. The curve fields are wired here; `baseline.py` and the percentile gate consume
them (a later phase). Absolute stays the fallback when the curve is off or no baseline
exists yet.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from .data import load_defaults

CONFIG_NAMES = (".impact-gate.yml", ".impact-gate.yaml")
ENFORCEMENTS = ("off", "warn", "block")

# Built-in defaults come from the shipped JSON, never from literals in this file.
_D = load_defaults()
_ABS = _D["absolute"]
_CURVE = _D["curve"]

# The knobs an .impact-gate.yml / CLI flag may override, and their loaders. Absolute and
# curve knobs share one path so a repo can set either mode's numbers in the same file.
_SCALAR_KEYS = ("warn_at", "block_at", "enforcement", "tolerance", "measure_config",
                "curve_enabled", "warn_percentile", "block_percentile",
                "curve_prior_weight", "baseline_file")


@dataclass
class GateConfig:
    warn_at: int | None = _ABS["warn_at"]     # impact above which to warn (None = never)
    block_at: int | None = _ABS["block_at"]   # impact above which to block (None = never)
    enforcement: str = _D["enforcement"]      # off | warn | block (block = too-high fails)
    tolerance: float = _D["tolerance"]        # CI multiplier on both thresholds (>1 = looser)
    measure_config: str | None = None         # optional Surveyor-style YAML (ignore globs)
    # Grading curve (percentile-based). Consumed once baseline.py + the percentile gate land.
    # The gate always scores the composite (change-level) impact; the mutation cost is a
    # per-file signal used to rank which files to consider, not a rival gating metric.
    curve_enabled: bool = _CURVE["enabled"]           # gate on percentile vs absolute
    warn_percentile: float = _CURVE["warn_percentile"]
    block_percentile: float = _CURVE["block_percentile"]
    curve_prior_weight: float = _CURVE["prior_weight_K"]  # K in w = n / (n + K)
    baseline_file: str = _CURVE["baseline_file"]      # project distribution cache

    def effective_warn(self) -> float | None:
        return None if self.warn_at is None else self.warn_at * self.tolerance

    def effective_block(self) -> float | None:
        return None if self.block_at is None else self.block_at * self.tolerance

    def level(self, impact: float) -> str:
        """'block' / 'warn' / 'ok' by threshold alone (independent of enforcement)."""
        b, w = self.effective_block(), self.effective_warn()
        if b is not None and impact > b:
            return "block"
        if w is not None and impact > w:
            return "warn"
        return "ok"

    def blocks(self, impact: float) -> bool:
        """True only when enforcement is 'block' AND the impact clears block_at — the
        one case that fails the gate. In 'warn' mode a too-high change still passes."""
        return self.enforcement == "block" and self.level(impact) == "block"

    @classmethod
    def load(cls, path: str | None = None, repo_path: str = ".") -> "GateConfig":
        """Load from an explicit path, else the first `.impact-gate.y*ml` in repo_path."""
        cfg = cls()
        found = path or _discover(repo_path)
        if not found:
            return cfg
        import yaml  # optional; only needed when a config file exists
        with open(found) as fh:
            data = yaml.safe_load(fh) or {}
        for key in _SCALAR_KEYS:
            if key in data and data[key] is not None:
                setattr(cfg, key, data[key])
        cfg.validate()
        return cfg

    def validate(self) -> None:
        if self.enforcement not in ENFORCEMENTS:
            raise ValueError(f"enforcement must be one of {ENFORCEMENTS}, got "
                             f"{self.enforcement!r}")
        if self.tolerance <= 0:
            raise ValueError("tolerance must be > 0")
        for name in ("warn_percentile", "block_percentile"):
            p = getattr(self, name)
            if not 0 < p < 100:
                raise ValueError(f"{name} must be within (0, 100), got {p}")
        if self.warn_percentile > self.block_percentile:
            raise ValueError("warn_percentile must be <= block_percentile")
        if self.curve_prior_weight < 0:
            raise ValueError("curve_prior_weight (K) must be >= 0")


def _discover(repo_path: str) -> str | None:
    for name in CONFIG_NAMES:
        p = os.path.join(repo_path, name)
        if os.path.isfile(p):
            return p
    return None
