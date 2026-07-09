"""Stop and take-profit from recent candle support/resistance."""

from __future__ import annotations

import pandas as pd

from indicators.support_resistance import find_support_resistance


def compute_sr_stops(
    side: str,
    entry_price: float,
    candles: pd.DataFrame,
    atr: float,
    *,
    lookback: int = 50,
    atr_stop_multiplier: float = 2.0,
    fallback_take_profit_rr: float = 1.25,
    min_rr: float = 0.75,
    max_rr: float = 2.5,
) -> tuple[float, float, dict[str, float | None]]:
    """
    Place stop at nearest S/R and target at the next level.

    Falls back to ATR stop and fixed R:R when levels are missing or too far.
    """
    sr = find_support_resistance(candles, lookback=lookback)
    meta = sr.metadata or {}
    support = meta.get("nearest_support")
    resistance = meta.get("nearest_resistance")
    max_sl_dist = atr * atr_stop_multiplier

    is_long = side.upper() in ("LONG", "BUY")
    if is_long:
        atr_sl = entry_price - max_sl_dist
        if support is not None and support < entry_price:
            stop_loss = support if entry_price - support <= max_sl_dist * 1.25 else atr_sl
        else:
            stop_loss = atr_sl

        sl_dist = entry_price - stop_loss
        if sl_dist <= 0:
            stop_loss = atr_sl
            sl_dist = entry_price - stop_loss

        if resistance is not None and resistance > entry_price:
            take_profit = resistance
        else:
            take_profit = entry_price + sl_dist * fallback_take_profit_rr
    else:
        atr_sl = entry_price + max_sl_dist
        if resistance is not None and resistance > entry_price:
            stop_loss = resistance if resistance - entry_price <= max_sl_dist * 1.25 else atr_sl
        else:
            stop_loss = atr_sl

        sl_dist = stop_loss - entry_price
        if sl_dist <= 0:
            stop_loss = atr_sl
            sl_dist = stop_loss - entry_price

        if support is not None and support < entry_price:
            take_profit = support
        else:
            take_profit = entry_price - sl_dist * fallback_take_profit_rr

    take_profit = _clamp_take_profit(
        side, entry_price, stop_loss, take_profit, min_rr, max_rr, fallback_take_profit_rr
    )
    details: dict[str, float | None] = {
        "nearest_support": float(support) if support is not None else None,
        "nearest_resistance": float(resistance) if resistance is not None else None,
    }
    return stop_loss, take_profit, details


def _clamp_take_profit(
    side: str,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    min_rr: float,
    max_rr: float,
    fallback_rr: float,
) -> float:
    sl_dist = abs(entry_price - stop_loss)
    if sl_dist <= 0:
        return take_profit

    is_long = side.upper() in ("LONG", "BUY")
    tp_dist = (take_profit - entry_price) if is_long else (entry_price - take_profit)
    rr = tp_dist / sl_dist

    if rr < min_rr:
        return entry_price + sl_dist * min_rr if is_long else entry_price - sl_dist * min_rr
    if rr > max_rr:
        return entry_price + sl_dist * max_rr if is_long else entry_price - sl_dist * max_rr
    if rr <= 0:
        return entry_price + sl_dist * fallback_rr if is_long else entry_price - sl_dist * fallback_rr
    return take_profit
