"""Volume-based indicators."""

from __future__ import annotations

import numpy as np
import pandas as pd

from indicators.base import IndicatorResult


def vwap(df: pd.DataFrame) -> IndicatorResult:
    """Volume Weighted Average Price."""
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    cumulative_tp_vol = (typical_price * df["volume"]).cumsum()
    cumulative_vol = df["volume"].cumsum()
    values = cumulative_tp_vol / cumulative_vol.replace(0, 1e-10)
    return IndicatorResult(name="vwap", values=values)


def volume_profile(
    df: pd.DataFrame,
    num_bins: int = 20,
    lookback: int = 100,
) -> IndicatorResult:
    """Volume profile with point of control."""
    subset = df.tail(lookback)
    if subset.empty:
        empty = pd.Series(dtype=float)
        return IndicatorResult(name="volume_profile", values=empty, metadata={"poc": 0.0})

    price_min = subset["low"].min()
    price_max = subset["high"].max()
    if price_min == price_max:
        return IndicatorResult(
            name="volume_profile",
            values=pd.Series([subset["volume"].sum()]),
            metadata={"poc": float(subset["close"].iloc[-1])},
        )

    bins = np.linspace(price_min, price_max, num_bins + 1)
    bin_volumes = np.zeros(num_bins)

    for _, row in subset.iterrows():
        mid_price = (row["high"] + row["low"]) / 2
        bin_idx = int((mid_price - price_min) / (price_max - price_min) * (num_bins - 1))
        bin_idx = max(0, min(bin_idx, num_bins - 1))
        bin_volumes[bin_idx] += row["volume"]

    bin_centers = (bins[:-1] + bins[1:]) / 2
    poc_idx = int(np.argmax(bin_volumes))
    poc = float(bin_centers[poc_idx])

    values = pd.Series(bin_volumes, index=bin_centers)
    return IndicatorResult(
        name="volume_profile",
        values=values,
        metadata={"poc": poc, "num_bins": num_bins},
    )
