"""Paper trading simulator."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from exchange.base import OrderResult, PositionInfo
from risk.stops import StopManager, StopState
from utils.helpers import calculate_pnl, safe_float
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class PaperPosition:
    id: str
    symbol: str
    side: str
    quantity: float
    entry_price: float
    leverage: int
    stop_loss: float | None = None
    take_profit: float | None = None
    strategy: str = ""
    opened_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    stop_state: StopState | None = None


class PaperTrader:
    """Simulated trading identical to live mode."""

    def __init__(
        self,
        initial_balance: float = 10000.0,
        slippage_pct: float = 0.02,
        commission_pct: float = 0.04,
    ) -> None:
        self.balance = initial_balance
        self.initial_balance = initial_balance
        self.slippage_pct = slippage_pct
        self.commission_pct = commission_pct
        self.positions: dict[str, PaperPosition] = {}
        self.closed_trades: list[dict[str, Any]] = []
        self._order_counter = 0

    async def get_balance(self) -> float:
        return self.balance

    async def get_positions(self, symbol: str | None = None) -> list[PositionInfo]:
        result = []
        for pos in self.positions.values():
            if symbol and pos.symbol != symbol:
                continue
            result.append(
                PositionInfo(
                    symbol=pos.symbol,
                    side=pos.side,
                    quantity=pos.quantity,
                    entry_price=pos.entry_price,
                    unrealized_pnl=0.0,
                    leverage=pos.leverage,
                )
            )
        return result

    async def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        position_side: str = "BOTH",
        strategy: str = "",
        stop_loss: float | None = None,
        take_profit: float | None = None,
        leverage: int = 1,
        current_price: float | None = None,
    ) -> OrderResult:
        self._order_counter += 1
        price = current_price or 0.0
        slip = price * (self.slippage_pct / 100)
        fill_price = price + slip if side.upper() == "BUY" else price - slip

        pos_side = "LONG" if side.upper() == "BUY" else "SHORT"
        pos_id = str(uuid4())
        self.positions[pos_id] = PaperPosition(
            id=pos_id,
            symbol=symbol,
            side=pos_side,
            quantity=quantity,
            entry_price=fill_price,
            leverage=leverage,
            stop_loss=stop_loss,
            take_profit=take_profit,
            strategy=strategy,
            stop_state=StopState(
                stop_loss=stop_loss or fill_price,
                take_profit=take_profit or fill_price,
                highest_price=fill_price,
                lowest_price=fill_price,
            )
            if stop_loss and take_profit
            else None,
        )

        logger.info(
            "paper_order_filled",
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=fill_price,
        )
        return OrderResult(
            order_id=str(self._order_counter),
            symbol=symbol,
            side=side,
            order_type="MARKET",
            price=fill_price,
            quantity=quantity,
            status="FILLED",
            filled_quantity=quantity,
        )

    async def close_position(
        self,
        position_id: str,
        current_price: float,
        reason: str = "manual",
    ) -> dict[str, Any] | None:
        pos = self.positions.pop(position_id, None)
        if pos is None:
            return None

        slip = current_price * (self.slippage_pct / 100)
        exit_price = (
            current_price - slip if pos.side == "LONG" else current_price + slip
        )
        pnl = calculate_pnl(pos.side, pos.entry_price, exit_price, pos.quantity)
        commission = abs(pnl) * (self.commission_pct / 100)
        pnl -= commission
        self.balance += pnl

        trade = {
            "symbol": pos.symbol,
            "side": pos.side,
            "entry_price": pos.entry_price,
            "exit_price": exit_price,
            "quantity": pos.quantity,
            "pnl": pnl,
            "pnl_pct": (pnl / (pos.entry_price * pos.quantity)) * 100,
            "strategy": pos.strategy,
            "reason": reason,
            "opened_at": pos.opened_at.isoformat(),
            "closed_at": datetime.now(UTC).isoformat(),
        }
        self.closed_trades.append(trade)
        logger.info("paper_position_closed", **trade)
        return trade

    def update_trailing_stops(
        self,
        symbol: str,
        current_price: float,
        stop_manager: StopManager,
        atr: float,
    ) -> None:
        """Tighten stops with trailing / break-even logic."""
        for pos in self.positions.values():
            if pos.symbol != symbol or pos.stop_state is None:
                continue
            updated = stop_manager.update_trailing(pos.stop_state, pos.side, current_price, atr)
            pos.stop_state = updated
            pos.stop_loss = updated.stop_loss

    def check_stops(self, symbol: str, current_price: float) -> list[tuple[str, str]]:
        """Check stop loss and take profit for open positions."""
        to_close: list[tuple[str, str]] = []
        for pos_id, pos in self.positions.items():
            if pos.symbol != symbol:
                continue
            if pos.side == "LONG":
                if pos.stop_loss and current_price <= pos.stop_loss:
                    to_close.append((pos_id, "stop_loss"))
                elif pos.take_profit and current_price >= pos.take_profit:
                    to_close.append((pos_id, "take_profit"))
            else:
                if pos.stop_loss and current_price >= pos.stop_loss:
                    to_close.append((pos_id, "stop_loss"))
                elif pos.take_profit and current_price <= pos.take_profit:
                    to_close.append((pos_id, "take_profit"))
        return to_close

    @property
    def equity(self) -> float:
        return self.balance

    @property
    def win_rate(self) -> float:
        if not self.closed_trades:
            return 0.0
        wins = sum(1 for t in self.closed_trades if t["pnl"] > 0)
        return (wins / len(self.closed_trades)) * 100

    def export_state(self) -> dict[str, Any]:
        positions: dict[str, Any] = {}
        for pid, pos in self.positions.items():
            positions[pid] = {
                "id": pos.id,
                "symbol": pos.symbol,
                "side": pos.side,
                "quantity": pos.quantity,
                "entry_price": pos.entry_price,
                "leverage": pos.leverage,
                "stop_loss": pos.stop_loss,
                "take_profit": pos.take_profit,
                "strategy": pos.strategy,
                "opened_at": pos.opened_at.isoformat(),
            }
        return {
            "balance": self.balance,
            "initial_balance": self.initial_balance,
            "positions": positions,
            "closed_trades": self.closed_trades,
            "order_counter": self._order_counter,
        }

    def import_state(self, data: dict[str, Any]) -> None:
        self.balance = float(data.get("balance", self.initial_balance))
        self.initial_balance = float(data.get("initial_balance", self.balance))
        self.closed_trades = list(data.get("closed_trades", []))
        self._order_counter = int(data.get("order_counter", 0))
        self.positions.clear()
        for pid, raw in data.get("positions", {}).items():
            opened = raw.get("opened_at")
            opened_at = (
                datetime.fromisoformat(str(opened).replace("Z", "+00:00"))
                if opened
                else datetime.now(UTC)
            )
            self.positions[pid] = PaperPosition(
                id=str(raw.get("id", pid)),
                symbol=raw["symbol"],
                side=raw["side"],
                quantity=float(raw["quantity"]),
                entry_price=float(raw["entry_price"]),
                leverage=int(raw.get("leverage", 1)),
                stop_loss=raw.get("stop_loss"),
                take_profit=raw.get("take_profit"),
                strategy=str(raw.get("strategy", "")),
                opened_at=opened_at,
            )

    def reset(self, balance: float) -> None:
        self.balance = balance
        self.initial_balance = balance
        self.positions.clear()
        self.closed_trades.clear()
        self._order_counter = 0
