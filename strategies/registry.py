"""Strategy plugin registry."""

from __future__ import annotations

from typing import Any, Type

from strategies.base import StrategyBase
from strategies.breakout import BreakoutStrategy
from strategies.ema_cross_rsi import EMACrossRSIStrategy
from strategies.mean_reversion import MeanReversionStrategy
from strategies.scalping import ScalpingStrategy
from strategies.trend_following import TrendFollowingStrategy


class StrategyRegistry:
    """Plugin registry for trading strategies."""

    _strategies: dict[str, Type[StrategyBase]] = {
        "ema_cross_rsi": EMACrossRSIStrategy,
        "trend_following": TrendFollowingStrategy,
        "scalping": ScalpingStrategy,
        "breakout": BreakoutStrategy,
        "mean_reversion": MeanReversionStrategy,
    }

    @classmethod
    def register(cls, name: str, strategy_class: Type[StrategyBase]) -> None:
        cls._strategies[name] = strategy_class

    @classmethod
    def get(cls, name: str) -> Type[StrategyBase] | None:
        return cls._strategies.get(name)

    @classmethod
    def create_all(cls, config: dict[str, Any]) -> list[StrategyBase]:
        """Instantiate all enabled strategies from config."""
        instances: list[StrategyBase] = []
        for name, strategy_class in cls._strategies.items():
            strategy_config = config.get(name, {})
            if strategy_config.get("enabled", False):
                instances.append(strategy_class(strategy_config))
        return instances

    @classmethod
    def list_strategies(cls) -> list[str]:
        return list(cls._strategies.keys())
