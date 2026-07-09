"""Risk management unit tests."""

from datetime import UTC, datetime, timedelta

from risk.manager import OpenPositionSnapshot, RiskContext, RiskManager
from risk.position_sizer import PositionSizer
from risk.stops import StopManager, StopState
from strategies.base import Signal, SignalType


class TestPositionSizer:
    def test_fixed_risk_sizing(self) -> None:
        sizer = PositionSizer(risk_per_trade_pct=1.0, method="fixed_risk")
        qty = sizer.calculate(balance=10000, entry_price=50000, stop_loss=49000, leverage=10)
        assert qty > 0

    def test_zero_stop_distance(self) -> None:
        sizer = PositionSizer()
        qty = sizer.calculate(balance=10000, entry_price=50000, stop_loss=50000)
        assert qty == 0.0


class TestStopManager:
    def test_initial_stops_long(self) -> None:
        manager = StopManager(atr_multiplier=2.0, take_profit_rr=2.0)
        sl, tp = manager.initial_stops("LONG", 50000, atr=500)
        assert sl < 50000
        assert tp > 50000

    def test_initial_stops_short(self) -> None:
        manager = StopManager()
        sl, tp = manager.initial_stops("SHORT", 50000, atr=500)
        assert sl > 50000
        assert tp < 50000

    def test_should_exit_stop_loss(self) -> None:
        manager = StopManager()
        reason = manager.should_exit("LONG", 49000, stop_loss=49500, take_profit=52000)
        assert reason == "stop_loss"

    def test_trailing_stop_update(self) -> None:
        manager = StopManager()
        state = StopState(stop_loss=49000, take_profit=52000, highest_price=50000)
        updated = manager.update_trailing(state, "LONG", 51000, atr=500)
        assert updated.stop_loss >= 49000

    def test_trailing_disabled_when_multiplier_zero(self) -> None:
        manager = StopManager(trailing_atr_multiplier=0, break_even_rr=0)
        state = StopState(stop_loss=49000, take_profit=52000, highest_price=50000)
        updated = manager.update_trailing(state, "LONG", 51000, atr=500)
        assert updated.stop_loss == 49000
        assert updated.trailing_stop is None


def _context(
    balance: float = 10000,
    equity: float = 10000,
    open_positions: list[OpenPositionSnapshot] | None = None,
    unrealized_pnl: float = 0.0,
) -> RiskContext:
    return RiskContext(
        balance=balance,
        equity=equity,
        open_positions=open_positions or [],
        unrealized_pnl=unrealized_pnl,
    )


def _buy_signal() -> Signal:
    return Signal(
        symbol="BTCUSDT",
        action=SignalType.BUY,
        price=50000,
        confidence=0.8,
        strategy="ema_cross_rsi",
        timeframe="15m",
        stop_loss=49000,
        take_profit=52000,
    )


class TestRiskManager:
    def test_approve_valid_signal(self, risk_config: dict) -> None:
        manager = RiskManager(risk_config)
        result = manager.check_signal(_buy_signal(), _context(), atr=500)
        assert result.approved
        assert result.quantity > 0

    def test_reject_max_positions(self, risk_config: dict) -> None:
        manager = RiskManager(risk_config)
        open_positions = [
            OpenPositionSnapshot("BTCUSDT", "LONG", 0.01, 50000),
            OpenPositionSnapshot("ETHUSDT", "LONG", 0.1, 3000),
            OpenPositionSnapshot("ETHUSDT", "SHORT", 0.1, 3000),
        ]
        result = manager.check_signal(_buy_signal(), _context(open_positions=open_positions), atr=500)
        assert not result.approved
        assert result.reason == "max_concurrent_positions"

    def test_reject_max_per_symbol(self, risk_config: dict) -> None:
        manager = RiskManager(risk_config)
        open_positions = [OpenPositionSnapshot("BTCUSDT", "LONG", 0.01, 50000)]
        result = manager.check_signal(_buy_signal(), _context(open_positions=open_positions), atr=500)
        assert not result.approved
        assert result.reason == "max_positions_per_symbol"

    def test_reject_duplicate_side(self, risk_config: dict) -> None:
        manager = RiskManager({**risk_config, "max_positions_per_symbol": 2, "block_duplicate_side": True})
        open_positions = [OpenPositionSnapshot("BTCUSDT", "LONG", 0.01, 50000)]
        result = manager.check_signal(_buy_signal(), _context(open_positions=open_positions), atr=500)
        assert not result.approved
        assert result.reason == "duplicate_side_blocked"

    def test_reject_signal_cooldown(self, risk_config: dict) -> None:
        manager = RiskManager(
            {
                **risk_config,
                "max_positions_per_symbol": 2,
                "block_duplicate_side": False,
            }
        )
        recent = datetime.now(UTC) - timedelta(minutes=2)
        open_positions = [
            OpenPositionSnapshot("BTCUSDT", "LONG", 0.01, 49900, opened_at=recent),
        ]
        result = manager.check_signal(_buy_signal(), _context(open_positions=open_positions), atr=500)
        assert not result.approved
        assert result.reason == "signal_cooldown"

    def test_emergency_close_threshold(self, risk_config: dict) -> None:
        manager = RiskManager(risk_config)
        context = _context(equity=9200, unrealized_pnl=-800)
        assert manager.should_emergency_close(context)

    def test_apply_settings(self, risk_config: dict) -> None:
        manager = RiskManager(risk_config)
        updated = manager.apply_settings({"max_concurrent_positions": 8, "max_daily_loss_pct": 2.5})
        assert updated["max_concurrent_positions"] == 8
        assert manager.max_concurrent_positions == 8
        assert manager.max_daily_loss_pct == 2.5

    def test_cooldown_after_loss(self, risk_config: dict) -> None:
        manager = RiskManager(risk_config)
        manager.record_loss()
        result = manager.check_signal(_buy_signal(), _context(), atr=500)
        assert not result.approved
        assert result.reason == "cooldown_after_loss"

    def test_take_profit_uses_account_rr(self, risk_config: dict) -> None:
        manager = RiskManager({**risk_config, "take_profit_rr": 1.25})
        signal = Signal(
            symbol="BTCUSDT",
            action=SignalType.BUY,
            price=50000,
            confidence=0.8,
            strategy="ema_cross_rsi",
            timeframe="15m",
            stop_loss=49000,
            take_profit=52000,
        )
        result = manager.check_signal(signal, _context(), atr=500)
        assert result.approved
        assert result.take_profit == 51250.0
