"""Breakout strategy."""

from __future__ import annotations

from typing import Any

from indicators.support_resistance import find_support_resistance
from indicators.volatility import atr
from strategies.base import Signal, SignalType, StrategyBase, StrategyContext


class BreakoutStrategy(StrategyBase):
    name = "breakout"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.lookback = int(config.get("lookback_period", 20))
        self.volume_multiplier = float(config.get("volume_multiplier", 1.5))
        self.confirmation_candles = int(config.get("confirmation_candles", 1))

    def analyze(self, context: StrategyContext) -> Signal | None:
        df = context.candles
        if len(df) < self.lookback + 5:
            return None

        price = context.latest_price or float(df["close"].iloc[-1])
        high_range = float(df["high"].iloc[-self.lookback - 1 : -1].max())
        low_range = float(df["low"].iloc[-self.lookback - 1 : -1].min())

        avg_volume = float(df["volume"].iloc[-self.lookback - 1 : -1].mean())
        curr_volume = float(df["volume"].iloc[-1])
        atr_vals = atr(df, 14).values
        curr_atr = float(atr_vals.iloc[-1])

        sr = find_support_resistance(df, lookback=self.lookback)
        resistance = sr.metadata.get("nearest_resistance") if sr.metadata else None
        support = sr.metadata.get("nearest_support") if sr.metadata else None

        volume_confirmed = curr_volume >= avg_volume * self.volume_multiplier

        if price > high_range and volume_confirmed:
            stop = support if support else price - 2 * curr_atr
            return Signal(
                symbol=context.symbol,
                action=SignalType.BUY,
                price=price,
                confidence=0.75,
                strategy=self.name,
                timeframe=context.timeframe,
                stop_loss=stop,
                take_profit=price + 3 * curr_atr,
                metadata={
                    "breakout_level": high_range,
                    "volume_ratio": curr_volume / avg_volume if avg_volume else 0,
                    "resistance": resistance,
                },
            )

        if price < low_range and volume_confirmed:
            stop = resistance if resistance else price + 2 * curr_atr
            return Signal(
                symbol=context.symbol,
                action=SignalType.SELL,
                price=price,
                confidence=0.75,
                strategy=self.name,
                timeframe=context.timeframe,
                stop_loss=stop,
                take_profit=price - 3 * curr_atr,
                metadata={
                    "breakout_level": low_range,
                    "volume_ratio": curr_volume / avg_volume if avg_volume else 0,
                    "support": support,
                },
            )
        return None
