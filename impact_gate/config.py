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
_COG = _D.get("cognitive", {"cognitive_max": 20})
_M = _D.get("measures", {})

# The three measures ImpactGate runs. Each is on by default and gates per MEASURES[name]
# enforcement (its own override, else the top-level `enforcement`). "change_impact" is the
# composite blast-radius score, "cognitive" the per-method readability gate, "coupling" the
# coupling-divergence placement check.
MEASURES = ("change_impact", "cognitive", "coupling")

# The knobs an .impact-gate.yml / CLI flag may override, and their loaders. Absolute and
# curve knobs share one path so a repo can set either mode's numbers in the same file.
_SCALAR_KEYS = ("warn_at", "block_at", "enforcement", "tolerance", "measure_config",
                "curve_enabled", "warn_percentile", "block_percentile",
                "curve_prior_weight", "baseline_file", "cognitive_max",
                "change_impact_enforcement", "cognitive_enforcement",
                "coupling_enforcement")


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
    # Cognitive-complexity gate (Campbell 2018): an ABSOLUTE per-method readability threshold,
    # independent of the change-impact composite/curve. ON by default (20). ANY method in a
    # changed file whose cognitive complexity exceeds it is reported — the gate for deeply-
    # nested, hard-to-read methods the change-impact score cannot see. Set cognitive_max to
    # null, or the cognitive measure's enforcement to "off", to disable it.
    cognitive_max: int | None = _COG["cognitive_max"]
    # Per-measure enforcement overrides. None = inherit the top-level `enforcement` (warn by
    # default, so every measure warns and nothing blocks until asked). Set one to "block" to
    # fail the build on just that measure, or "off" to switch that measure off entirely.
    change_impact_enforcement: str | None = _M.get("change_impact_enforcement")
    cognitive_enforcement: str | None = _M.get("cognitive_enforcement")
    coupling_enforcement: str | None = _M.get("coupling_enforcement")

    def measure_mode(self, measure: str) -> str:
        """Effective enforcement (off | warn | block) for one measure: its own override if
        set, else the top-level `enforcement`. This is the single place the per-measure vs
        global precedence is decided."""
        override = getattr(self, f"{measure}_enforcement", None)
        return override if override is not None else self.enforcement

    def enabled(self, measure: str) -> bool:
        """Whether a measure runs at all. A measure in 'off' is not run or reported."""
        return self.measure_mode(measure) != "off"

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
        """True only when the change-impact measure is in 'block' AND the impact clears
        block_at: the one case that fails the gate on impact. In 'warn' a too-high change
        still passes."""
        return (self.measure_mode("change_impact") == "block"
                and self.level(impact) == "block")

    def level_for_grade(self, percentile: float) -> str:
        """Curve mode: 'block' / 'warn' / 'ok' from a change's grade percentile. A change
        at or above `block_percentile` blocks; at or above `warn_percentile` warns."""
        if percentile >= self.block_percentile:
            return "block"
        if percentile >= self.warn_percentile:
            return "warn"
        return "ok"

    def blocks_grade(self, percentile: float) -> bool:
        """Curve analogue of `blocks`: fails the gate only when change_impact is 'block'."""
        return (self.measure_mode("change_impact") == "block"
                and self.level_for_grade(percentile) == "block")

    def cognitive_enabled(self) -> bool:
        """The cognitive gate runs when its measure is not 'off' and a limit is set."""
        return self.enabled("cognitive") and self.cognitive_max is not None

    def cognitive_level(self, max_cognitive: int) -> str:
        """'block' when a method's cognitive complexity exceeds `cognitive_max`, else 'ok'.
        Independent of the change-impact level; the two are OR'd by the caller."""
        if self.cognitive_enabled() and max_cognitive > self.cognitive_max:
            return "block"
        return "ok"

    def blocks_cognitive(self, max_cognitive: int) -> bool:
        """Fails the gate on readability only when the cognitive measure is in 'block'."""
        return (self.measure_mode("cognitive") == "block"
                and self.cognitive_level(max_cognitive) == "block")

    def coupling_enabled(self) -> bool:
        """The coupling-divergence placement check runs when its measure is not 'off'."""
        return self.enabled("coupling")

    def coupling_level(self, has_vortex: bool) -> str:
        """'block' when the change touches a coupling vortex, else 'ok'. OR'd with the
        other measures by the caller; advisory in 'warn'."""
        return "block" if (self.coupling_enabled() and has_vortex) else "ok"

    def blocks_coupling(self, has_vortex: bool) -> bool:
        """Fails the gate on coupling only when the coupling measure is in 'block'."""
        return (self.measure_mode("coupling") == "block"
                and self.coupling_level(has_vortex) == "block")

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
        for m in MEASURES:
            v = getattr(self, f"{m}_enforcement")
            if v is not None and v not in ENFORCEMENTS:
                raise ValueError(f"{m}_enforcement must be one of {ENFORCEMENTS} or null, "
                                 f"got {v!r}")
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
        if self.cognitive_max is not None and self.cognitive_max <= 0:
            raise ValueError("cognitive_max must be > 0 (or null to disable)")


def _discover(repo_path: str) -> str | None:
    for name in CONFIG_NAMES:
        p = os.path.join(repo_path, name)
        if os.path.isfile(p):
            return p
    return None
