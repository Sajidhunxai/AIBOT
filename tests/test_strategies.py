"""Strategy unit tests."""

import pandas as pd

from strategies.base import SignalType, StrategyContext
from strategies.breakout import BreakoutStrategy
from strategies.ema_cross_rsi import EMACrossRSIStrategy
from strategies.mean_reversion import MeanReversionStrategy
from strategies.registry import StrategyRegistry
from strategies.scalping import ScalpingStrategy
from strategies.trend_following import TrendFollowingStrategy


class TestStrategyRegistry:
    def test_list_strategies(self) -> None:
        strategies = StrategyRegistry.list_strategies()
        assert "ema_cross_rsi" in strategies
        assert "trend_following" in strategies
        assert len(strategies) == 5

    def test_create_enabled(self, strategies_config: dict) -> None:
        instances = StrategyRegistry.create_all(strategies_config)
        assert len(instances) == 1
        assert instances[0].name == "ema_cross_rsi"


class TestEMACrossRSI:
    def test_analyze_returns_signal_or_none(self, sample_ohlcv: pd.DataFrame) -> None:
        strategy = EMACrossRSIStrategy({"enabled": True, "fast_ema": 9, "slow_ema": 21})
        context = StrategyContext(
            symbol="BTCUSDT",
            timeframe="15m",
            candles=sample_ohlcv,
            latest_price=float(sample_ohlcv["close"].iloc[-1]),
        )
        signal = strategy.analyze(context)
        if signal:
            assert signal.action in (SignalType.BUY, SignalType.SELL, SignalType.HOLD)
            assert signal.symbol == "BTCUSDT"

    def test_insufficient_data(self) -> None:
        strategy = EMACrossRSIStrategy({"enabled": True})
        df = pd.DataFrame({"close": [1, 2, 3], "high": [1, 2, 3], "low": [1, 2, 3], "volume": [1, 1, 1]})
        context = StrategyContext(symbol="BTCUSDT", timeframe="15m", candles=df, latest_price=3.0)
        assert strategy.analyze(context) is None


class TestOtherStrategies:
    def test_trend_following(self, sample_ohlcv: pd.DataFrame) -> None:
        strategy = TrendFollowingStrategy({"enabled": True})
        context = StrategyContext(
            symbol="BTCUSDT",
            timeframe="15m",
            candles=sample_ohlcv,
            latest_price=float(sample_ohlcv["close"].iloc[-1]),
        )
        signal = strategy.analyze(context)
        assert signal is None or signal.action in (SignalType.BUY, SignalType.SELL)

    def test_breakout(self, sample_ohlcv: pd.DataFrame) -> None:
        strategy = BreakoutStrategy({"enabled": True, "lookback_period": 20})
        context = StrategyContext(
            symbol="BTCUSDT",
            timeframe="15m",
            candles=sample_ohlcv,
            latest_price=float(sample_ohlcv["close"].iloc[-1]),
        )
        strategy.analyze(context)

    def test_scalping(self, sample_ohlcv: pd.DataFrame) -> None:
        strategy = ScalpingStrategy({"enabled": True})
        context = StrategyContext(
            symbol="BTCUSDT",
            timeframe="1m",
            candles=sample_ohlcv,
            latest_price=float(sample_ohlcv["close"].iloc[-1]),
        )
        strategy.analyze(context)

    def test_mean_reversion(self, sample_ohlcv: pd.DataFrame) -> None:
        strategy = MeanReversionStrategy({"enabled": True})
        context = StrategyContext(
            symbol="BTCUSDT",
            timeframe="15m",
            candles=sample_ohlcv,
            latest_price=float(sample_ohlcv["close"].iloc[-1]),
        )
        strategy.analyze(context)
