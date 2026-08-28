"""Shipped data and the loader for it.

Every tunable number the gate leans on lives in a JSON file in this package, not in
code, so refining them as research lands is a data edit and a version bump — never a
code change:

  defaults.json          — default gate / grading-curve constants (GateConfig reads
                           these as its built-in defaults).
  seed_percentiles.json  — per-language percentile tables of per-commit composite
                           impact, with a pooled fallback. The cold-start prior for the
                           grading curve, derived from the corpus scan.

Files are read through importlib.resources so they resolve the same whether the package
is run from a checkout or an installed wheel. Results are cached; call `reload()` in a
test that rewrites a file.
"""
from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources

METRICS = ("composite", "mutation")


def _read(name: str) -> dict:
    with resources.files(__package__).joinpath(name).open(encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=None)
def load_defaults() -> dict:
    """The default gate / curve constants from defaults.json (cached)."""
    return _read("defaults.json")


@lru_cache(maxsize=None)
def load_seed_percentiles() -> dict:
    """The seed percentile tables from seed_percentiles.json (cached, validated)."""
    data = _read("seed_percentiles.json")
    _validate_seed(data)
    return data


def reload() -> None:
    """Drop the caches so the next load re-reads from disk (tests that rewrite files)."""
    load_defaults.cache_clear()
    load_seed_percentiles.cache_clear()


def seed_table(lang: str | None) -> tuple[list[float], list[float]]:
    """(percentiles, values) for a language, falling back to the pooled table.

    `percentiles` is the shared axis (ascending, e.g. [50, 75, 90, 95, 98, 99]);
    `values` is the per-commit impact at each of those percentiles for `lang`.
    """
    data = load_seed_percentiles()
    pct = [float(p) for p in data["percentiles"]]
    table = data["languages"].get(lang) if lang else None
    if table is None:
        table = data["pooled"]
    return pct, [float(v) for v in table["values"]]


def rank_in_table(value: float, percentiles: list[float],
                  values: list[float]) -> float:
    """Percentile rank of `value` against a percentile->value table.

    Linear interpolation between the tabulated points, clamped to [0, 100]. Below the
    first point the rank scales from 0 up to the first percentile; above the last point
    it saturates just under 100 (the tail is unbounded, so never report a flat 100).
    This is the seed half of the grade; `baseline.py` blends it with project history.
    """
    if value <= 0:
        return 0.0
    # Below the lowest tabulated value: scale 0 -> percentiles[0] by the value ratio.
    if value <= values[0]:
        first = percentiles[0]
        return round(first * (value / values[0]), 2) if values[0] > 0 else 0.0
    for i in range(1, len(values)):
        if value <= values[i]:
            lo_v, hi_v = values[i - 1], values[i]
            lo_p, hi_p = percentiles[i - 1], percentiles[i]
            frac = (value - lo_v) / (hi_v - lo_v) if hi_v > lo_v else 0.0
            return round(lo_p + frac * (hi_p - lo_p), 2)
    # Above the top tabulated point: approach 100 without reaching it.
    last_p = percentiles[-1]
    return round(last_p + (100.0 - last_p) * 0.5, 2)


def _validate_seed(data: dict) -> None:
    """Fail loud on a malformed table, so a bad scan swap is caught at load, not use."""
    pct = data.get("percentiles")
    if not isinstance(pct, list) or len(pct) < 2:
        raise ValueError("seed_percentiles.json: 'percentiles' must list >= 2 points")
    if any(pct[i] >= pct[i + 1] for i in range(len(pct) - 1)):
        raise ValueError("seed_percentiles.json: 'percentiles' must be ascending")
    if not (0 < pct[0] and pct[-1] < 100):
        raise ValueError("seed_percentiles.json: percentiles must be within (0, 100)")
    tables = {"pooled": data.get("pooled"), **(data.get("languages") or {})}
    if data.get("pooled") is None:
        raise ValueError("seed_percentiles.json: a 'pooled' fallback table is required")
    for label, table in tables.items():
        vals = (table or {}).get("values")
        if not isinstance(vals, list) or len(vals) != len(pct):
            raise ValueError(f"seed_percentiles.json: table {label!r} needs "
                             f"{len(pct)} values to match 'percentiles'")
        if any(vals[i] > vals[i + 1] for i in range(len(vals) - 1)):
            raise ValueError(f"seed_percentiles.json: table {label!r} values must be "
                             "non-decreasing")
