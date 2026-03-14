"""Math utility helpers."""
from __future__ import annotations

from typing import Sequence


def safe_div(numerator: float, denominator: float, fallback: float = 0.0) -> float:
    """Divide, returning *fallback* when denominator is zero."""
    if denominator == 0.0:
        return fallback
    return numerator / denominator


def clamp(value: float, low: float, high: float) -> float:
    """Clamp *value* to [low, high]."""
    return max(low, min(high, value))


def normalize_score(
    raw: float,
    min_raw: float = -1.0,
    max_raw: float = 1.0,
    out_min: float = 0.0,
    out_max: float = 100.0,
) -> float:
    """Linear normalisation from [min_raw, max_raw] → [out_min, out_max]."""
    span = max_raw - min_raw
    if span == 0.0:
        return (out_min + out_max) / 2.0
    ratio = clamp((raw - min_raw) / span, 0.0, 1.0)
    return out_min + ratio * (out_max - out_min)


def weighted_average(values: Sequence[float], weights: Sequence[float]) -> float:
    """Compute weighted average. Returns 0 if total weight is 0."""
    total_weight = sum(weights)
    if total_weight == 0.0:
        return 0.0
    return sum(v * w for v, w in zip(values, weights)) / total_weight


def pct_change(current: float, previous: float) -> float:
    """Percentage change from *previous* to *current* (as fraction, e.g. 0.02 = 2%)."""
    return safe_div(current - previous, abs(previous), fallback=0.0)
