"""Gate configuration: thresholds, enforcement mode, CI-adjustable tolerance.

Resolved in layers (later wins): built-in defaults -> `.impact-gate.yml` in the repo
-> CLI flags / CI inputs. For now thresholds are absolute impact numbers (seeded from
the Surveyor corpus); the per-project grading curve is a later phase and will populate
`warn_at` / `block_at` automatically from history.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

CONFIG_NAMES = (".impact-gate.yml", ".impact-gate.yaml")
ENFORCEMENTS = ("off", "warn", "block")


@dataclass
class GateConfig:
    warn_at: int | None = None       # impact above which to warn (None = never warn)
    block_at: int | None = None      # impact above which to block (None = never block)
    enforcement: str = "warn"        # off | warn | block  (block = a too-high change fails)
    tolerance: float = 1.0           # CI-adjustable multiplier on both thresholds (>1 = looser)
    wmc_context: str = "before"      # measure definition (canonical: before-context)
    measure_config: str | None = None  # optional Surveyor-style YAML (ignore globs, etc.)

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
        for key in ("warn_at", "block_at", "enforcement", "tolerance",
                    "wmc_context", "measure_config"):
            if key in data and data[key] is not None:
                setattr(cfg, key, data[key])
        cfg.validate()
        return cfg

    def validate(self) -> None:
        if self.enforcement not in ENFORCEMENTS:
            raise ValueError(f"enforcement must be one of {ENFORCEMENTS}, got "
                             f"{self.enforcement!r}")
        if self.wmc_context not in ("before", "after"):
            raise ValueError("wmc_context must be 'before' or 'after'")
        if self.tolerance <= 0:
            raise ValueError("tolerance must be > 0")


def _discover(repo_path: str) -> str | None:
    for name in CONFIG_NAMES:
        p = os.path.join(repo_path, name)
        if os.path.isfile(p):
            return p
    return None
