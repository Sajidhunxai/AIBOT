"""Support and resistance detection."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from indicators.base import IndicatorResult


def find_support_resistance(
    df: pd.DataFrame,
    lookback: int = 50,
    num_levels: int = 3,
    tolerance_pct: float = 0.5,
) -> IndicatorResult:
    """Detect support and resistance levels using local extrema clustering."""
    subset = df.tail(lookback)
    if len(subset) < 5:
        return IndicatorResult(
            name="support_resistance",
            values=pd.Series(dtype=float),
            metadata={"support": [], "resistance": []},
        )

    highs = subset["high"].values
    lows = subset["low"].values
    close = float(subset["close"].iloc[-1])

    resistance_levels = _find_levels(highs, num_levels, tolerance_pct, above=close)
    support_levels = _find_levels(lows, num_levels, tolerance_pct, above=False, reference=close)

    metadata: dict[str, Any] = {
        "support": support_levels,
        "resistance": resistance_levels,
        "nearest_support": _nearest(support_levels, close, below=True),
        "nearest_resistance": _nearest(resistance_levels, close, below=False),
    }
    all_levels = pd.Series(support_levels + resistance_levels)
    return IndicatorResult(name="support_resistance", values=all_levels, metadata=metadata)


def _find_levels(
    prices: np.ndarray,
    num_levels: int,
    tolerance_pct: float,
    above: bool | None = None,
    reference: float = 0.0,
) -> list[float]:
    extrema: list[float] = []
    for i in range(2, len(prices) - 2):
        if prices[i] > prices[i - 1] and prices[i] > prices[i + 1]:
            if above is None or (above and prices[i] > reference) or (not above and prices[i] < reference):
                extrema.append(float(prices[i]))
        elif prices[i] < prices[i - 1] and prices[i] < prices[i + 1]:
            if above is None or (not above and prices[i] < reference):
                extrema.append(float(prices[i]))

    if not extrema:
        return []

    clustered: list[float] = []
    for price in sorted(extrema):
        merged = False
        for i, level in enumerate(clustered):
            if abs(price - level) / level * 100 < tolerance_pct:
                clustered[i] = (level + price) / 2
                merged = True
                break
        if not merged:
            clustered.append(price)

    clustered.sort(reverse=above if above else False)
    return clustered[:num_levels]


def _nearest(levels: list[float], price: float, below: bool) -> float | None:
    if not levels:
        return None
    if below:
        candidates = [l for l in levels if l <= price]
        return max(candidates) if candidates else None
    candidates = [l for l in levels if l >= price]
    return min(candidates) if candidates else None
