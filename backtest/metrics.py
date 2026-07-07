"""Backtest performance metrics."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from utils.helpers import sharpe_ratio


@dataclass
class PerformanceMetrics:
    win_rate: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    cagr: float = 0.0
    expectancy: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    monthly_returns: dict[str, float] = field(default_factory=dict)
    equity_curve: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "win_rate": round(self.win_rate, 2),
            "profit_factor": round(self.profit_factor, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 2),
            "max_drawdown": round(self.max_drawdown, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "cagr": round(self.cagr, 2),
            "expectancy": round(self.expectancy, 4),
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "total_pnl": round(self.total_pnl, 2),
            "monthly_returns": self.monthly_returns,
        }


def calculate_metrics(
    trades: list[dict[str, Any]],
    equity_curve: list[float],
    initial_balance: float,
    start_date: pd.Timestamp | None = None,
    end_date: pd.Timestamp | None = None,
) -> PerformanceMetrics:
    """Calculate comprehensive backtest metrics."""
    metrics = PerformanceMetrics(equity_curve=equity_curve)

    if not trades:
        return metrics

    pnls = [t["pnl"] for t in trades]
    metrics.total_trades = len(trades)
    metrics.winning_trades = sum(1 for p in pnls if p > 0)
    metrics.losing_trades = sum(1 for p in pnls if p <= 0)
    metrics.total_pnl = sum(pnls)
    metrics.win_rate = (metrics.winning_trades / metrics.total_trades) * 100

    gross_profit = sum(p for p in pnls if p > 0)
    gross_loss = abs(sum(p for p in pnls if p < 0))
    metrics.profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    metrics.expectancy = metrics.total_pnl / metrics.total_trades

    if len(equity_curve) > 1:
        equity = np.array(equity_curve)
        peak = np.maximum.accumulate(equity)
        drawdown = peak - equity
        metrics.max_drawdown = float(drawdown.max())
        metrics.max_drawdown_pct = (
            float((drawdown / peak).max() * 100) if peak.max() > 0 else 0.0
        )

        daily_returns = np.diff(equity) / equity[:-1]
        metrics.sharpe_ratio = sharpe_ratio(daily_returns.tolist())

    if start_date and end_date and initial_balance > 0:
        years = (end_date - start_date).days / 365.25
        if years > 0 and equity_curve:
            final = equity_curve[-1]
            metrics.cagr = ((final / initial_balance) ** (1 / years) - 1) * 100

    closed_dates = [t.get("closed_at") for t in trades if t.get("closed_at")]
    if closed_dates:
        df = pd.DataFrame({"pnl": pnls, "date": pd.to_datetime(closed_dates)})
        df["month"] = df["date"].dt.to_period("M").astype(str)
        monthly = df.groupby("month")["pnl"].sum()
        metrics.monthly_returns = {str(k): round(float(v), 2) for k, v in monthly.items()}

    return metrics
