"""Backtest unit tests."""

import pandas as pd
import pytest

from backtest.engine import BacktestEngine
from backtest.metrics import calculate_metrics


class TestBacktestMetrics:
    def test_empty_trades(self) -> None:
        metrics = calculate_metrics([], [10000], 10000)
        assert metrics.total_trades == 0
        assert metrics.win_rate == 0.0

    def test_with_trades(self) -> None:
        trades = [
            {"pnl": 100, "closed_at": "2024-01-15"},
            {"pnl": -50, "closed_at": "2024-01-20"},
            {"pnl": 200, "closed_at": "2024-02-01"},
        ]
        equity = [10000, 10100, 10050, 10250]
        metrics = calculate_metrics(
            trades,
            equity,
            10000,
            pd.Timestamp("2024-01-01"),
            pd.Timestamp("2024-03-01"),
        )
        assert metrics.total_trades == 3
        assert metrics.winning_trades == 2
        assert metrics.win_rate == pytest.approx(66.67, abs=0.1)
        assert metrics.profit_factor == pytest.approx(6.0, abs=0.1)


class TestBacktestEngine:
    def test_run_backtest(self, sample_ohlcv: pd.DataFrame, strategies_config: dict, risk_config: dict) -> None:
        engine = BacktestEngine(
            strategies_config=strategies_config,
            risk_config=risk_config,
            backtest_config={"initial_balance": 10000, "commission_pct": 0.04, "slippage_pct": 0.02},
        )
        result = engine.run({"BTCUSDT": sample_ohlcv}, "BTCUSDT", "15m")
        assert result.metrics is not None
        assert isinstance(result.trades, list)
