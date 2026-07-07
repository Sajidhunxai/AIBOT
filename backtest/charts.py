"""Backtest chart generation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd


class BacktestCharts:
    """Generate backtest visualization charts."""

    def __init__(self, output_dir: str = "backtest_output") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def plot_equity_curve(
        self,
        equity_curve: list[float],
        title: str = "Equity Curve",
        filename: str = "equity_curve.png",
    ) -> str:
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.plot(equity_curve, color="#2563eb", linewidth=1.5)
        ax.set_title(title, fontsize=14, fontweight="bold")
        ax.set_xlabel("Trade #")
        ax.set_ylabel("Equity ($)")
        ax.grid(True, alpha=0.3)
        ax.fill_between(range(len(equity_curve)), equity_curve, alpha=0.1, color="#2563eb")
        path = self.output_dir / filename
        fig.tight_layout()
        fig.savefig(path, dpi=150)
        plt.close(fig)
        return str(path)

    def plot_monthly_returns(
        self,
        monthly_returns: dict[str, float],
        filename: str = "monthly_returns.png",
    ) -> str:
        if not monthly_returns:
            return ""
        fig, ax = plt.subplots(figsize=(12, 6))
        months = list(monthly_returns.keys())
        values = list(monthly_returns.values())
        colors = ["#22c55e" if v >= 0 else "#ef4444" for v in values]
        ax.bar(months, values, color=colors, alpha=0.8)
        ax.set_title("Monthly Returns", fontsize=14, fontweight="bold")
        ax.set_ylabel("PnL ($)")
        ax.tick_params(axis="x", rotation=45)
        ax.grid(True, alpha=0.3, axis="y")
        ax.axhline(y=0, color="black", linewidth=0.5)
        path = self.output_dir / filename
        fig.tight_layout()
        fig.savefig(path, dpi=150)
        plt.close(fig)
        return str(path)

    def plot_drawdown(
        self,
        equity_curve: list[float],
        filename: str = "drawdown.png",
    ) -> str:
        import numpy as np

        equity = np.array(equity_curve)
        peak = np.maximum.accumulate(equity)
        drawdown_pct = (peak - equity) / peak * 100

        fig, ax = plt.subplots(figsize=(12, 4))
        ax.fill_between(range(len(drawdown_pct)), drawdown_pct, color="#ef4444", alpha=0.5)
        ax.set_title("Drawdown %", fontsize=14, fontweight="bold")
        ax.set_ylabel("Drawdown (%)")
        ax.set_xlabel("Trade #")
        ax.grid(True, alpha=0.3)
        path = self.output_dir / filename
        fig.tight_layout()
        fig.savefig(path, dpi=150)
        plt.close(fig)
        return str(path)

    def generate_all(
        self,
        equity_curve: list[float],
        monthly_returns: dict[str, float],
        prefix: str = "",
    ) -> dict[str, str]:
        """Generate all charts and return paths."""
        p = f"{prefix}_" if prefix else ""
        return {
            "equity_curve": self.plot_equity_curve(
                equity_curve, filename=f"{p}equity_curve.png"
            ),
            "monthly_returns": self.plot_monthly_returns(
                monthly_returns, filename=f"{p}monthly_returns.png"
            ),
            "drawdown": self.plot_drawdown(equity_curve, filename=f"{p}drawdown.png"),
        }
