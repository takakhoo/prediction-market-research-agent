"""Strict validation at untrusted model-output boundaries."""
from __future__ import annotations
import math
from typing import Any


def probability(value: Any) -> float | None:
    """JSON numeric probability, not bool/string/NaN/infinity or a clamped score."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        result = float(value)
    except (ValueError, OverflowError):
        return None
    return result if math.isfinite(result) and 0 <= result <= 1 else None
