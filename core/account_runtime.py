"""Per-account paper trading, risk, and strategy runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.engine import StrategyEngine
from core.paper_trader import PaperTrader
from risk.manager import RiskManager


@dataclass
class AccountRuntime:
    """Isolated paper trader, risk manager, and strategy engine for one account."""

    account_id: int
    paper_trader: PaperTrader
    risk_manager: RiskManager
    strategy_engine: StrategyEngine
    strategies_config: dict[str, Any]
