"""Backtesting engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from backtest.charts import BacktestCharts
from backtest.metrics import PerformanceMetrics, calculate_metrics
from risk.manager import OpenPositionSnapshot, RiskContext, RiskManager
from strategies.base import Signal, SignalType, StrategyBase, StrategyContext
from strategies.registry import StrategyRegistry
from utils.helpers import calculate_pnl
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class BacktestResult:
    metrics: PerformanceMetrics
    trades: list[dict[str, Any]] = field(default_factory=list)
    chart_paths: dict[str, str] = field(default_factory=dict)


class BacktestEngine:
    """Event-driven backtesting engine."""

    def __init__(
        self,
        strategies_config: dict[str, Any],
        risk_config: dict[str, Any],
        backtest_config: dict[str, Any],
    ) -> None:
        self.strategies = StrategyRegistry.create_all(strategies_config)
        self.risk_manager = RiskManager(risk_config)
        self.initial_balance = float(backtest_config.get("initial_balance", 10000))
        self.commission_pct = float(backtest_config.get("commission_pct", 0.04))
        self.slippage_pct = float(backtest_config.get("slippage_pct", 0.02))
        self.charts = BacktestCharts()

    def run(
        self,
        data: dict[str, pd.DataFrame],
        symbol: str,
        timeframe: str = "15m",
    ) -> BacktestResult:
        """Run backtest on historical candle data."""
        df = data.get(symbol, pd.DataFrame())
        if df.empty:
            logger.warning("backtest_no_data", symbol=symbol)
            return BacktestResult(metrics=PerformanceMetrics())

        balance = self.initial_balance
        equity_curve = [balance]
        trades: list[dict[str, Any]] = []
        open_position: dict[str, Any] | None = None

        min_bars = 60
        for i in range(min_bars, len(df)):
            window = df.iloc[: i + 1].copy()
            price = float(window["close"].iloc[-1])
            context = StrategyContext(
                symbol=symbol,
                timeframe=timeframe,
                candles=window,
                latest_price=price,
            )

            if open_position:
                exit_reason = self._check_exit(open_position, price, window)
                if exit_reason:
                    pnl = self._close_position(open_position, price, balance)
                    commission = abs(pnl) * (self.commission_pct / 100)
                    pnl -= commission
                    balance += pnl
                    open_position["exit_price"] = price
                    open_position["pnl"] = pnl
                    open_position["exit_reason"] = exit_reason
                    open_position["closed_at"] = window["close_time"].iloc[-1]
                    trades.append(open_position)
                    if pnl < 0:
                        self.risk_manager.record_loss()
                    open_position = None
                    equity_curve.append(balance)
                continue

            for strategy in self.strategies:
                signal = strategy.analyze(context)
                if signal is None or signal.action == SignalType.HOLD:
                    continue

                from indicators.volatility import atr

                atr_val = float(atr(window, 14).values.iloc[-1])
                open_snapshots: list[OpenPositionSnapshot] = []
                if open_position:
                    opened = open_position.get("opened_at")
                    opened_dt = (
                        opened.to_pydatetime() if hasattr(opened, "to_pydatetime") else opened
                    )
                    open_snapshots = [
                        OpenPositionSnapshot(
                            symbol=open_position["symbol"],
                            side=open_position["side"],
                            quantity=open_position["quantity"],
                            entry_price=open_position["entry_price"],
                            opened_at=opened_dt,
                        )
                    ]
                risk_context = RiskContext(
                    balance=balance,
                    equity=balance,
                    open_positions=open_snapshots,
                )
                risk_result = self.risk_manager.check_signal(signal, risk_context, atr_val)
                if not risk_result.approved:
                    continue

                entry_price = self._apply_slippage(signal.price, signal.action)
                side = "LONG" if signal.action == SignalType.BUY else "SHORT"
                open_position = {
                    "symbol": symbol,
                    "side": side,
                    "strategy": signal.strategy,
                    "entry_price": entry_price,
                    "quantity": risk_result.quantity,
                    "stop_loss": risk_result.stop_loss,
                    "take_profit": risk_result.take_profit,
                    "opened_at": window["close_time"].iloc[-1],
                    "pnl": 0.0,
                }
                break

        if open_position:
            price = float(df["close"].iloc[-1])
            pnl = self._close_position(open_position, price, balance)
            open_position["exit_price"] = price
            open_position["pnl"] = pnl
            open_position["exit_reason"] = "end_of_data"
            open_position["closed_at"] = df["close_time"].iloc[-1]
            trades.append(open_position)
            balance += pnl
            equity_curve.append(balance)

        start = pd.Timestamp(df["open_time"].iloc[min_bars])
        end = pd.Timestamp(df["close_time"].iloc[-1])
        metrics = calculate_metrics(trades, equity_curve, self.initial_balance, start, end)
        chart_paths = self.charts.generate_all(
            equity_curve, metrics.monthly_returns, prefix=symbol
        )

        logger.info(
            "backtest_complete",
            symbol=symbol,
            trades=metrics.total_trades,
            win_rate=metrics.win_rate,
            total_pnl=metrics.total_pnl,
        )
        return BacktestResult(metrics=metrics, trades=trades, chart_paths=chart_paths)

    def _apply_slippage(self, price: float, action: SignalType) -> float:
        slip = price * (self.slippage_pct / 100)
        if action == SignalType.BUY:
            return price + slip
        return price - slip

    def _check_exit(
        self,
        position: dict[str, Any],
        price: float,
        window: pd.DataFrame,
    ) -> str | None:
        side = position["side"]
        sl = position.get("stop_loss")
        tp = position.get("take_profit")
        if side == "LONG":
            if sl and price <= sl:
                return "stop_loss"
            if tp and price >= tp:
                return "take_profit"
        else:
            if sl and price >= sl:
                return "stop_loss"
            if tp and price <= tp:
                return "take_profit"
        return None

    def _close_position(
        self,
        position: dict[str, Any],
        exit_price: float,
        balance: float,
    ) -> float:
        return calculate_pnl(
            position["side"],
            position["entry_price"],
            exit_price,
            position["quantity"],
        )
