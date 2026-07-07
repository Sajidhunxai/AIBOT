"""General helper utilities."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from typing import Any


@dataclass(frozen=True)
class SymbolFilters:
    tick_size: float
    step_size: float
    min_qty: float = 0.0
    min_notional: float = 20.0


def parse_symbol_filters(symbol_info: dict[str, Any]) -> SymbolFilters:
    """Extract lot and price filters from Binance exchangeInfo symbol entry."""
    tick_size = 0.01
    step_size = 0.001
    min_qty = 0.0
    min_notional = 20.0
    for f in symbol_info.get("filters", []):
        filter_type = f.get("filterType")
        if filter_type == "PRICE_FILTER":
            tick_size = safe_float(f.get("tickSize"), tick_size)
        elif filter_type == "LOT_SIZE":
            step_size = safe_float(f.get("stepSize"), step_size)
            min_qty = safe_float(f.get("minQty"), min_qty)
        elif filter_type == "MIN_NOTIONAL":
            min_notional = safe_float(f.get("notional"), min_notional)
        elif filter_type == "NOTIONAL":
            min_notional = safe_float(f.get("minNotional"), min_notional)
    return SymbolFilters(
        tick_size=tick_size,
        step_size=step_size,
        min_qty=min_qty,
        min_notional=min_notional,
    )


def format_exchange_value(value: float, step: float) -> str:
    """Format a price or quantity for Binance API (round down to step)."""
    rounded = round_step(value, step)
    if step >= 1:
        return str(int(rounded))
    step_str = f"{step:.16f}".rstrip("0")
    precision = len(step_str.split(".")[-1]) if "." in step_str else 0
    return f"{rounded:.{precision}f}"


def format_exchange_value_up(value: float, step: float) -> str:
    """Format quantity for orders — round up to step so min notional is not lost."""
    rounded = round_step_up(value, step)
    if step >= 1:
        return str(int(rounded))
    step_str = f"{step:.16f}".rstrip("0")
    precision = len(step_str.split(".")[-1]) if "." in step_str else 0
    return f"{rounded:.{precision}f}"


def safe_float(value: Any, default: float = 0.0) -> float:
    """Safely convert value to float."""
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def round_step(value: float, step: float) -> float:
    """Round value down to nearest step size (exchange lot size)."""
    if step <= 0:
        return value
    d_value = Decimal(str(value))
    d_step = Decimal(str(step))
    rounded = (d_value / d_step).quantize(Decimal("1"), rounding=ROUND_DOWN) * d_step
    return float(rounded)


def round_step_up(value: float, step: float) -> float:
    """Round value up to nearest step size."""
    if step <= 0:
        return value
    d_value = Decimal(str(value))
    d_step = Decimal(str(step))
    rounded = (d_value / d_step).quantize(Decimal("1"), rounding=ROUND_UP) * d_step
    return float(rounded)


def ensure_min_notional_quantity(
    quantity: float,
    entry_price: float,
    min_notional: float,
    lot_step: float,
    min_qty: float = 0.0,
) -> float:
    """Bump quantity so notional meets exchange minimum (e.g. Binance $20)."""
    if entry_price <= 0 or quantity <= 0:
        return 0.0
    qty = round_step(quantity, lot_step)
    if qty < min_qty:
        qty = round_step_up(min_qty, lot_step)
    if min_notional <= 0:
        return qty
    if qty * entry_price >= min_notional:
        return qty
    needed = max(min_notional / entry_price, min_qty)
    return round_step_up(max(qty, needed), lot_step)


def pct_change(old: float, new: float) -> float:
    """Calculate percentage change."""
    if old == 0:
        return 0.0
    return ((new - old) / old) * 100.0


def timestamp_ms(dt: datetime | None = None) -> int:
    """Return UTC timestamp in milliseconds."""
    if dt is None:
        dt = datetime.now(UTC)
    return int(dt.timestamp() * 1000)


def timestamp_to_datetime(ts: int | float) -> datetime:
    """Convert millisecond timestamp to UTC datetime."""
    if ts > 1e12:
        ts = ts / 1000.0
    return datetime.fromtimestamp(ts, tz=UTC)


def clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp value between min and max."""
    return max(min_val, min(value, max_val))


def timeframe_to_minutes(timeframe: str) -> int:
    """Convert timeframe string to minutes."""
    mapping = {"m": 1, "h": 60, "d": 1440, "w": 10080}
    unit = timeframe[-1]
    if unit not in mapping:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    return int(timeframe[:-1]) * mapping[unit]


def calculate_pnl(
    side: str,
    entry_price: float,
    exit_price: float,
    quantity: float,
    leverage: int = 1,
) -> float:
    """Calculate PnL for a futures position."""
    if side.upper() in ("LONG", "BUY"):
        return (exit_price - entry_price) * quantity
    return (entry_price - exit_price) * quantity


def sharpe_ratio(returns: list[float], risk_free_rate: float = 0.0) -> float:
    """Calculate annualized Sharpe ratio from daily returns."""
    if len(returns) < 2:
        return 0.0
    import numpy as np

    arr = np.array(returns)
    excess = arr - risk_free_rate / 252
    std = np.std(excess, ddof=1)
    if std == 0 or math.isnan(std):
        return 0.0
    return float(np.mean(excess) / std * math.sqrt(252))
