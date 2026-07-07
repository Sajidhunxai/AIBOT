"""Volatility indicators."""

from __future__ import annotations

import pandas as pd

from indicators.base import IndicatorResult


def atr(df: pd.DataFrame, period: int = 14) -> IndicatorResult:
    """Average True Range."""
    high = df["high"]
    low = df["low"]
    close = df["close"]
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    values = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    return IndicatorResult(name=f"atr_{period}", values=values)


def bollinger_bands(
    series: pd.Series,
    period: int = 20,
    std_dev: float = 2.0,
) -> IndicatorResult:
    """Bollinger Bands."""
    middle = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper = middle + std_dev * std
    lower = middle - std_dev * std
    values = pd.DataFrame({"upper": upper, "middle": middle, "lower": lower})
    return IndicatorResult(
        name="bollinger_bands",
        values=values,
        metadata={"period": period, "std_dev": std_dev},
    )
