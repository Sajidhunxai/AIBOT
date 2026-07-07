"""Momentum indicators."""

from __future__ import annotations

import pandas as pd

from indicators.base import IndicatorResult


def rsi(series: pd.Series, period: int = 14) -> IndicatorResult:
    """Relative Strength Index."""
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-10)
    values = 100 - (100 / (1 + rs))
    return IndicatorResult(name=f"rsi_{period}", values=values)


def macd(
    series: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> IndicatorResult:
    """Moving Average Convergence Divergence."""
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    values = pd.DataFrame(
        {"macd": macd_line, "signal": signal_line, "histogram": histogram}
    )
    return IndicatorResult(
        name="macd",
        values=values,
        metadata={"fast": fast, "slow": slow, "signal": signal},
    )


def adx(df: pd.DataFrame, period: int = 14) -> IndicatorResult:
    """Average Directional Index."""
    high = df["high"]
    low = df["low"]
    close = df["close"]

    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr_vals = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    plus_di = 100 * (plus_dm.ewm(alpha=1 / period, min_periods=period, adjust=False).mean() / atr_vals)
    minus_di = 100 * (minus_dm.ewm(alpha=1 / period, min_periods=period, adjust=False).mean() / atr_vals)

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-10)
    adx_vals = dx.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    values = pd.DataFrame({"adx": adx_vals, "plus_di": plus_di, "minus_di": minus_di})
    return IndicatorResult(name=f"adx_{period}", values=values)
