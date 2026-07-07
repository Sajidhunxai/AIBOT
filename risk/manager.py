"""Risk management orchestrator."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from risk.position_sizer import PositionSizer
from risk.stops import StopManager
from strategies.base import Signal
from utils.helpers import ensure_min_notional_quantity
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class RiskCheckResult:
    approved: bool
    reason: str
    quantity: float = 0.0
    stop_loss: float | None = None
    take_profit: float | None = None


@dataclass
class OpenPositionSnapshot:
    symbol: str
    side: str
    quantity: float
    entry_price: float
    opened_at: datetime | None = None


@dataclass
class RiskContext:
    balance: float
    equity: float
    open_positions: list[OpenPositionSnapshot] = field(default_factory=list)
    unrealized_pnl: float = 0.0


class RiskManager:
    """Enforce risk rules before trade execution."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.risk_per_trade_pct = float(config.get("risk_per_trade_pct", 1.0))
        self.max_daily_loss_pct = float(config.get("max_daily_loss_pct", 3.0))
        self.max_drawdown_pct = float(config.get("max_drawdown_pct", 10.0))
        self.max_concurrent_positions = int(config.get("max_concurrent_positions", 4))
        self.max_positions_per_symbol = int(config.get("max_positions_per_symbol", 1))
        self.cooldown_minutes = int(config.get("cooldown_after_loss_minutes", 30))
        self.signal_cooldown_minutes = int(config.get("signal_cooldown_minutes", 15))
        self.max_unrealized_loss_pct = float(config.get("max_unrealized_loss_pct", 5.0))
        self.emergency_close_unrealized_loss_pct = float(
            config.get("emergency_close_unrealized_loss_pct", 8.0)
        )
        self.max_total_exposure_pct = float(config.get("max_total_exposure_pct", 40.0))
        self.block_duplicate_side = bool(config.get("block_duplicate_side", True))
        self.use_equity_for_limits = bool(config.get("use_equity_for_limits", True))

        self.position_sizer = PositionSizer(
            risk_per_trade_pct=self.risk_per_trade_pct,
            method=config.get("position_size_method", "fixed_risk"),
        )
        self.stop_manager = StopManager(
            atr_multiplier=float(config.get("atr_stop_multiplier", 2.0)),
            take_profit_rr=float(config.get("take_profit_rr", 2.0)),
            trailing_atr_multiplier=float(config.get("trailing_stop_atr_multiplier", 1.5)),
            break_even_rr=float(config.get("break_even_trigger_rr", 1.0)),
        )

        self._peak_equity: float = 0.0
        self._last_loss_time: datetime | None = None
        self._daily_pnl: float = 0.0
        self._initial_balance: float = 0.0
        self._trading_halted: bool = False
        self._halt_reason: str = ""

    @property
    def trading_halted(self) -> bool:
        return self._trading_halted

    @property
    def halt_reason(self) -> str:
        return self._halt_reason

    def halt_trading(self, reason: str) -> None:
        self._trading_halted = True
        self._halt_reason = reason
        logger.warning("trading_halted", reason=reason)

    def resume_trading(self) -> None:
        self._trading_halted = False
        self._halt_reason = ""

    def set_balance(self, balance: float) -> None:
        if self._initial_balance == 0:
            self._initial_balance = balance
        self._peak_equity = max(self._peak_equity, balance)

    def set_equity(self, equity: float) -> None:
        self._peak_equity = max(self._peak_equity, equity)

    def update_daily_pnl(self, pnl: float) -> None:
        self._daily_pnl = pnl

    def record_loss(self) -> None:
        self._last_loss_time = datetime.now(UTC)

    def should_emergency_close(self, context: RiskContext) -> bool:
        """Return True when open loss is large enough to force-close everything."""
        reference = self._reference_capital(context)
        if reference <= 0:
            return False
        loss_pct = (-context.unrealized_pnl / reference) * 100.0
        if context.unrealized_pnl < 0 and loss_pct >= self.emergency_close_unrealized_loss_pct:
            self.halt_trading("emergency_unrealized_loss")
            return True
        return False

    def get_limits_summary(self) -> dict[str, Any]:
        return {
            "max_concurrent_positions": self.max_concurrent_positions,
            "max_positions_per_symbol": self.max_positions_per_symbol,
            "max_daily_loss_pct": self.max_daily_loss_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "max_unrealized_loss_pct": self.max_unrealized_loss_pct,
            "emergency_close_unrealized_loss_pct": self.emergency_close_unrealized_loss_pct,
            "max_total_exposure_pct": self.max_total_exposure_pct,
            "signal_cooldown_minutes": self.signal_cooldown_minutes,
            "cooldown_after_loss_minutes": self.cooldown_minutes,
            "trading_halted": self._trading_halted,
            "halt_reason": self._halt_reason,
        }

    def get_settings(self) -> dict[str, Any]:
        """Return all editable risk settings for API / dashboard."""
        return {
            **self.get_limits_summary(),
            "risk_per_trade_pct": self.risk_per_trade_pct,
            "block_duplicate_side": self.block_duplicate_side,
            "use_equity_for_limits": self.use_equity_for_limits,
            "atr_stop_multiplier": self.stop_manager.atr_multiplier,
            "take_profit_rr": self.stop_manager.take_profit_rr,
            "trailing_stop_atr_multiplier": self.stop_manager.trailing_atr_multiplier,
            "break_even_trigger_rr": self.stop_manager.break_even_rr,
            "position_size_method": self.position_sizer.method,
        }

    def apply_settings(self, updates: dict[str, Any]) -> dict[str, Any]:
        """Apply runtime risk setting updates (partial patch supported)."""
        int_fields = {
            "max_concurrent_positions",
            "max_positions_per_symbol",
            "signal_cooldown_minutes",
        }
        float_fields = {
            "risk_per_trade_pct",
            "max_daily_loss_pct",
            "max_drawdown_pct",
            "max_unrealized_loss_pct",
            "emergency_close_unrealized_loss_pct",
            "max_total_exposure_pct",
            "atr_stop_multiplier",
            "take_profit_rr",
            "trailing_stop_atr_multiplier",
            "break_even_trigger_rr",
        }
        bool_fields = {"block_duplicate_side", "use_equity_for_limits"}

        for key, value in updates.items():
            if value is None:
                continue
            if key == "cooldown_after_loss_minutes":
                self.cooldown_minutes = int(value)
            elif key in int_fields:
                setattr(self, key, int(value))
            elif key in float_fields:
                if key == "atr_stop_multiplier":
                    self.stop_manager.atr_multiplier = float(value)
                elif key == "take_profit_rr":
                    self.stop_manager.take_profit_rr = float(value)
                elif key == "trailing_stop_atr_multiplier":
                    self.stop_manager.trailing_atr_multiplier = float(value)
                elif key == "break_even_trigger_rr":
                    self.stop_manager.break_even_rr = float(value)
                else:
                    setattr(self, key, float(value))
            elif key in bool_fields:
                setattr(self, key, bool(value))
            elif key == "position_size_method" and isinstance(value, str):
                self.position_sizer.method = value

        self.position_sizer.risk_per_trade_pct = self.risk_per_trade_pct
        logger.info("risk_settings_applied", updates=list(updates.keys()))
        return self.get_settings()

    def check_signal(
        self,
        signal: Signal,
        context: RiskContext,
        atr: float,
        lot_step: float = 0.001,
        min_notional: float = 0.0,
        min_qty: float = 0.0,
    ) -> RiskCheckResult:
        """Validate signal against all risk rules."""
        self.set_balance(context.balance)
        self.set_equity(context.equity)

        blocked = self._common_blocks(
            symbol=signal.symbol,
            side="LONG" if signal.action.value == "BUY" else "SHORT",
            entry_price=signal.price,
            quantity=0.0,
            context=context,
            check_cooldown=True,
        )
        if blocked:
            return blocked

        stop_loss = signal.stop_loss
        take_profit = signal.take_profit
        if stop_loss is None or take_profit is None:
            side = "LONG" if signal.action.value == "BUY" else "SHORT"
            stop_loss, take_profit = self.stop_manager.initial_stops(side, signal.price, atr)

        quantity = self.position_sizer.calculate(
            balance=context.equity if self.use_equity_for_limits else context.balance,
            entry_price=signal.price,
            stop_loss=stop_loss,
            lot_step=lot_step,
            min_notional=min_notional,
            min_qty=min_qty,
        )
        if quantity <= 0:
            return RiskCheckResult(False, "position_size_zero")

        if min_notional > 0 and quantity * signal.price < min_notional:
            return RiskCheckResult(False, "below_min_notional")

        max_qty = self._max_quantity_for_exposure(signal.price, context, lot_step)
        if max_qty is not None and quantity > max_qty:
            quantity = max_qty

        if min_notional > 0:
            quantity = ensure_min_notional_quantity(
                quantity, signal.price, min_notional, lot_step, min_qty
            )
            if quantity * signal.price < min_notional:
                return RiskCheckResult(False, "below_min_notional")

        if quantity <= 0:
            return RiskCheckResult(False, "max_total_exposure")

        exposure_block = self._check_exposure(signal.price, quantity, context)
        if exposure_block:
            return exposure_block

        return RiskCheckResult(
            approved=True,
            reason="approved",
            quantity=quantity,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

    def check_manual_trade(
        self,
        symbol: str,
        side: str,
        quantity: float,
        entry_price: float,
        context: RiskContext,
        lot_step: float = 0.001,
        min_notional: float = 0.0,
        min_qty: float = 0.0,
    ) -> RiskCheckResult:
        """Validate a manual trade against position and loss limits."""
        self.set_balance(context.balance)
        self.set_equity(context.equity)

        pos_side = "LONG" if side.upper() in ("BUY", "LONG") else "SHORT"
        blocked = self._common_blocks(
            symbol=symbol,
            side=pos_side,
            entry_price=entry_price,
            quantity=quantity,
            context=context,
            check_cooldown=False,
        )
        if blocked:
            return blocked

        quantity = ensure_min_notional_quantity(
            quantity, entry_price, min_notional, lot_step, min_qty
        )
        if min_notional > 0 and quantity * entry_price < min_notional:
            return RiskCheckResult(False, "below_min_notional")

        exposure_block = self._check_exposure(entry_price, quantity, context)
        if exposure_block:
            return exposure_block

        return RiskCheckResult(True, "approved", quantity=quantity)

    def _common_blocks(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        quantity: float,
        context: RiskContext,
        check_cooldown: bool,
    ) -> RiskCheckResult | None:
        if self._trading_halted:
            return RiskCheckResult(False, self._halt_reason or "trading_halted")

        if self._is_in_cooldown():
            return RiskCheckResult(False, "cooldown_after_loss")

        open_count = len(context.open_positions)
        if open_count >= self.max_concurrent_positions:
            return RiskCheckResult(False, "max_concurrent_positions")

        symbol_positions = [p for p in context.open_positions if p.symbol == symbol]
        if len(symbol_positions) >= self.max_positions_per_symbol:
            return RiskCheckResult(False, "max_positions_per_symbol")

        if self.block_duplicate_side and any(p.side == side for p in symbol_positions):
            return RiskCheckResult(False, "duplicate_side_blocked")

        if check_cooldown:
            cooldown_block = self._check_signal_cooldown(symbol, symbol_positions)
            if cooldown_block:
                return cooldown_block

        reference = self._reference_capital(context)
        daily_loss_limit = reference * (self.max_daily_loss_pct / 100.0)
        total_pnl = self._daily_pnl + context.unrealized_pnl
        if total_pnl < -daily_loss_limit:
            self.halt_trading("max_daily_loss")
            return RiskCheckResult(False, "max_daily_loss")

        if context.unrealized_pnl < 0 and reference > 0:
            unrealized_loss_pct = (-context.unrealized_pnl / reference) * 100.0
            if unrealized_loss_pct >= self.max_unrealized_loss_pct:
                return RiskCheckResult(False, "max_unrealized_loss")

        drawdown = self._calculate_drawdown(context.equity)
        if drawdown >= self.max_drawdown_pct:
            self.halt_trading("max_drawdown")
            return RiskCheckResult(False, "max_drawdown")

        return None

    def _check_signal_cooldown(
        self,
        symbol: str,
        symbol_positions: list[OpenPositionSnapshot],
    ) -> RiskCheckResult | None:
        if not symbol_positions or self.signal_cooldown_minutes <= 0:
            return None
        latest = max(
            (p.opened_at for p in symbol_positions if p.opened_at),
            default=None,
        )
        if latest is None:
            return None
        elapsed = datetime.now(UTC) - latest
        if elapsed < timedelta(minutes=self.signal_cooldown_minutes):
            return RiskCheckResult(False, "signal_cooldown")
        return None

    def _max_quantity_for_exposure(
        self,
        entry_price: float,
        context: RiskContext,
        lot_step: float,
    ) -> float | None:
        """Max additional quantity that fits within the exposure cap."""
        if self.max_total_exposure_pct <= 0 or entry_price <= 0:
            return None
        reference = self._reference_capital(context)
        if reference <= 0:
            return None
        max_notional = reference * (self.max_total_exposure_pct / 100.0)
        current_notional = sum(p.quantity * p.entry_price for p in context.open_positions)
        remaining = max(0.0, max_notional - current_notional)
        from utils.helpers import round_step

        return round_step(remaining / entry_price, lot_step)

    def _check_exposure(
        self,
        entry_price: float,
        quantity: float,
        context: RiskContext,
    ) -> RiskCheckResult | None:
        if self.max_total_exposure_pct <= 0 or entry_price <= 0:
            return None
        reference = self._reference_capital(context)
        if reference <= 0:
            return None

        current_notional = sum(p.quantity * p.entry_price for p in context.open_positions)
        new_notional = quantity * entry_price
        exposure_pct = ((current_notional + new_notional) / reference) * 100.0
        if exposure_pct > self.max_total_exposure_pct:
            max_notional = reference * (self.max_total_exposure_pct / 100.0)
            remaining = max(0.0, max_notional - current_notional)
            max_qty = remaining / entry_price if entry_price > 0 else 0.0
            return RiskCheckResult(
                False,
                (
                    f"max_total_exposure ({exposure_pct:.1f}% > {self.max_total_exposure_pct:.0f}% cap; "
                    f"open ${current_notional:.2f}, max additional qty ~{max_qty:.6f})"
                ),
            )
        return None

    def _reference_capital(self, context: RiskContext) -> float:
        if self.use_equity_for_limits:
            return context.equity if context.equity > 0 else context.balance
        return context.balance

    def _is_in_cooldown(self) -> bool:
        if self._last_loss_time is None:
            return False
        elapsed = datetime.now(UTC) - self._last_loss_time
        return elapsed < timedelta(minutes=self.cooldown_minutes)

    def _calculate_drawdown(self, current_equity: float) -> float:
        if self._peak_equity <= 0:
            return 0.0
        return ((self._peak_equity - current_equity) / self._peak_equity) * 100.0
