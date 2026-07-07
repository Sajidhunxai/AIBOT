"""Trading strategies."""

from strategies.base import Signal, SignalType, StrategyBase, StrategyContext
from strategies.registry import StrategyRegistry
from strategies.breakout import BreakoutStrategy
from strategies.ema_cross_rsi import EMACrossRSIStrategy
from strategies.mean_reversion import MeanReversionStrategy
from strategies.scalping import ScalpingStrategy
from strategies.trend_following import TrendFollowingStrategy

__all__ = [
    "Signal",
    "SignalType",
    "StrategyBase",
    "StrategyContext",
    "StrategyRegistry",
    "EMACrossRSIStrategy",
    "TrendFollowingStrategy",
    "ScalpingStrategy",
    "BreakoutStrategy",
    "MeanReversionStrategy",
]
