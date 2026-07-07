"""Position sizing calculations."""

from __future__ import annotations

from utils.helpers import ensure_min_notional_quantity, round_step


class PositionSizer:
    """Calculate position sizes based on risk parameters."""

    def __init__(
        self,
        risk_per_trade_pct: float = 1.0,
        method: str = "fixed_risk",
    ) -> None:
        self.risk_per_trade_pct = risk_per_trade_pct
        self.method = method

    def calculate(
        self,
        balance: float,
        entry_price: float,
        stop_loss: float,
        leverage: int = 1,
        lot_step: float = 0.001,
        min_notional: float = 0.0,
        min_qty: float = 0.0,
    ) -> float:
        """Calculate position quantity based on risk."""
        del leverage  # margin only; size is from stop distance
        if entry_price <= 0 or balance <= 0:
            return 0.0

        risk_amount = balance * (self.risk_per_trade_pct / 100.0)
        stop_distance = abs(entry_price - stop_loss)

        if stop_distance == 0:
            return 0.0

        if self.method == "fixed_risk":
            quantity = risk_amount / stop_distance
        elif self.method == "fixed_amount":
            quantity = risk_amount / entry_price
        else:
            quantity = risk_amount / stop_distance

        quantity = round_step(quantity, lot_step)
        if min_notional > 0:
            quantity = ensure_min_notional_quantity(
                quantity, entry_price, min_notional, lot_step, min_qty
            )
        return quantity
