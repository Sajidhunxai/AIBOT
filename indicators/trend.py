"""Trend indicators."""

from __future__ import annotations

import numpy as np
import pandas as pd

from indicators.base import IndicatorResult


def ema(series: pd.Series, period: int) -> IndicatorResult:
    """Exponential Moving Average."""
    values = series.ewm(span=period, adjust=False).mean()
    return IndicatorResult(name=f"ema_{period}", values=values)


def sma(series: pd.Series, period: int) -> IndicatorResult:
    """Simple Moving Average."""
    values = series.rolling(window=period).mean()
    return IndicatorResult(name=f"sma_{period}", values=values)


def supertrend(
    df: pd.DataFrame,
    period: int = 10,
    multiplier: float = 3.0,
) -> IndicatorResult:
    """Supertrend indicator."""
    high = df["high"]
    low = df["low"]
    close = df["close"]

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr_vals = tr.rolling(window=period).mean()

    hl2 = (high + low) / 2
    upper_band = hl2 + multiplier * atr_vals
    lower_band = hl2 - multiplier * atr_vals

    supertrend_vals = pd.Series(index=df.index, dtype=float)
    direction = pd.Series(index=df.index, dtype=int)

    for i in range(period, len(df)):
        if i == period:
            supertrend_vals.iloc[i] = upper_band.iloc[i]
            direction.iloc[i] = -1
            continue

        prev_st = supertrend_vals.iloc[i - 1]
        prev_dir = direction.iloc[i - 1]

        curr_upper = upper_band.iloc[i]
        curr_lower = lower_band.iloc[i]
        curr_close = close.iloc[i]

        if prev_dir == -1:
            st = curr_lower if curr_lower > prev_st or close.iloc[i - 1] > prev_st else prev_st
            if curr_close < st:
                direction.iloc[i] = 1
                st = curr_upper
            else:
                direction.iloc[i] = -1
        else:
            st = curr_upper if curr_upper < prev_st or close.iloc[i - 1] < prev_st else prev_st
            if curr_close > st:
                direction.iloc[i] = -1
                st = curr_lower
            else:
                direction.iloc[i] = 1

        supertrend_vals.iloc[i] = st

    result_df = pd.DataFrame({"supertrend": supertrend_vals, "direction": direction})
    return IndicatorResult(
        name="supertrend",
        values=result_df,
        metadata={"period": period, "multiplier": multiplier},
    )
