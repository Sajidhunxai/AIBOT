"""Stop loss and take profit management."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class StopState:
    stop_loss: float
    take_profit: float
    trailing_stop: float | None = None
    break_even_triggered: bool = False
    highest_price: float = 0.0
    lowest_price: float = float("inf")


class StopManager:
    """Manage dynamic stops: ATR, trailing, break-even."""

    def __init__(
        self,
        atr_multiplier: float = 2.0,
        take_profit_rr: float = 2.0,
        trailing_atr_multiplier: float = 1.5,
        break_even_rr: float = 1.0,
    ) -> None:
        self.atr_multiplier = atr_multiplier
        self.take_profit_rr = take_profit_rr
        self.trailing_atr_multiplier = trailing_atr_multiplier
        self.break_even_rr = break_even_rr

    def initial_stops(
        self,
        side: str,
        entry_price: float,
        atr: float,
    ) -> tuple[float, float]:
        """Calculate initial stop loss and take profit."""
        stop_distance = atr * self.atr_multiplier
        if side.upper() in ("LONG", "BUY"):
            stop_loss = entry_price - stop_distance
            take_profit = entry_price + stop_distance * self.take_profit_rr
        else:
            stop_loss = entry_price + stop_distance
            take_profit = entry_price - stop_distance * self.take_profit_rr
        return stop_loss, take_profit

    def update_trailing(
        self,
        state: StopState,
        side: str,
        current_price: float,
        atr: float,
    ) -> StopState:
        """Update trailing stop and break-even."""
        trail_distance = atr * self.trailing_atr_multiplier

        if side.upper() in ("LONG", "BUY"):
            state.highest_price = max(state.highest_price, current_price)
            risk = state.highest_price - (state.stop_loss if not state.break_even_triggered else state.highest_price)
            reward = current_price - (state.highest_price - risk)

            if not state.break_even_triggered and reward >= risk * self.break_even_rr:
                state.stop_loss = state.highest_price - risk * 0.1
                state.break_even_triggered = True

            new_trail = state.highest_price - trail_distance
            if state.trailing_stop is None or new_trail > state.trailing_stop:
                state.trailing_stop = new_trail
                if new_trail > state.stop_loss:
                    state.stop_loss = new_trail
        else:
            state.lowest_price = min(state.lowest_price, current_price)
            risk = (state.stop_loss if not state.break_even_triggered else state.lowest_price) - state.lowest_price
            reward = (state.lowest_price + risk) - current_price

            if not state.break_even_triggered and reward >= risk * self.break_even_rr:
                state.stop_loss = state.lowest_price + risk * 0.1
                state.break_even_triggered = True

            new_trail = state.lowest_price + trail_distance
            if state.trailing_stop is None or new_trail < state.trailing_stop:
                state.trailing_stop = new_trail
                if new_trail < state.stop_loss:
                    state.stop_loss = new_trail

        return state

    def should_exit(
        self,
        side: str,
        current_price: float,
        stop_loss: float,
        take_profit: float,
    ) -> str | None:
        """Check if position should be exited. Returns reason or None."""
        if side.upper() in ("LONG", "BUY"):
            if current_price <= stop_loss:
                return "stop_loss"
            if current_price >= take_profit:
                return "take_profit"
        else:
            if current_price >= stop_loss:
                return "stop_loss"
            if current_price <= take_profit:
                return "take_profit"
        return None


def build_initial_stop_state(
    entry_price: float,
    stop_loss: float,
    take_profit: float,
) -> StopState:
    """Create trailing/break-even state for a new position."""
    return StopState(
        stop_loss=stop_loss,
        take_profit=take_profit,
        highest_price=entry_price,
        lowest_price=entry_price,
    )


def stop_state_to_dict(state: StopState) -> dict[str, Any]:
    return {
        "stop_loss": state.stop_loss,
        "take_profit": state.take_profit,
        "trailing_stop": state.trailing_stop,
        "break_even_triggered": state.break_even_triggered,
        "highest_price": state.highest_price,
        "lowest_price": state.lowest_price,
    }


def stop_state_from_dict(
    data: dict[str, Any] | None,
    *,
    entry_price: float,
    stop_loss: float | None,
    take_profit: float | None,
) -> StopState | None:
    if stop_loss is None or take_profit is None:
        return None
    if not data:
        return build_initial_stop_state(entry_price, stop_loss, take_profit)
    return StopState(
        stop_loss=float(data.get("stop_loss", stop_loss)),
        take_profit=float(data.get("take_profit", take_profit)),
        trailing_stop=data.get("trailing_stop"),
        break_even_triggered=bool(data.get("break_even_triggered", False)),
        highest_price=float(data.get("highest_price", entry_price)),
        lowest_price=float(data.get("lowest_price", entry_price)),
    )
