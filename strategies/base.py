"""Base strategy interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import pandas as pd


class SignalType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    CLOSE = "CLOSE"
    HOLD = "HOLD"


@dataclass
class Signal:
    symbol: str
    action: SignalType
    price: float
    confidence: float
    strategy: str
    timeframe: str
    stop_loss: float | None = None
    take_profit: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class StrategyContext:
    symbol: str
    timeframe: str
    candles: pd.DataFrame
    funding_rate: float = 0.0
    open_interest: float = 0.0
    orderbook: dict[str, Any] = field(default_factory=dict)
    latest_price: float = 0.0


class StrategyBase(ABC):
    """Abstract base class for all trading strategies."""

    name: str = "base"

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.enabled = config.get("enabled", True)

    @abstractmethod
    def analyze(self, context: StrategyContext) -> Signal | None:
        """Analyze market data and return a signal or None."""
        ...

    def _hold(self, context: StrategyContext) -> Signal:
        return Signal(
            symbol=context.symbol,
            action=SignalType.HOLD,
            price=context.latest_price,
            confidence=0.0,
            strategy=self.name,
            timeframe=context.timeframe,
        )
