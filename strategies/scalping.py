"""Scalping strategy for short-term trades."""

from __future__ import annotations

from typing import Any

from indicators.momentum import rsi
from indicators.trend import ema
from indicators.volatility import atr, bollinger_bands
from strategies.base import Signal, SignalType, StrategyBase, StrategyContext


class ScalpingStrategy(StrategyBase):
    name = "scalping"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.ema_fast = int(config.get("ema_fast", 5))
        self.ema_slow = int(config.get("ema_slow", 13))
        self.rsi_period = int(config.get("rsi_period", 7))
        self.bb_period = int(config.get("bb_period", 20))
        self.bb_std = float(config.get("bb_std", 2.0))
        self.min_volume_ratio = float(config.get("min_volume_ratio", 1.2))

    def analyze(self, context: StrategyContext) -> Signal | None:
        df = context.candles
        if len(df) < self.bb_period + 5:
            return None

        close = df["close"]
        volume = df["volume"]
        price = context.latest_price or float(close.iloc[-1])

        fast = ema(close, self.ema_fast).values
        slow = ema(close, self.ema_slow).values
        rsi_vals = rsi(close, self.rsi_period).values
        bb = bollinger_bands(close, self.bb_period, self.bb_std).values
        atr_vals = atr(df, 14).values

        avg_volume = float(volume.rolling(20).mean().iloc[-1])
        curr_volume = float(volume.iloc[-1])
        volume_ratio = curr_volume / avg_volume if avg_volume > 0 else 0

        if volume_ratio < self.min_volume_ratio:
            return None

        curr_rsi = float(rsi_vals.iloc[-1])
        curr_fast = float(fast.iloc[-1])
        curr_slow = float(slow.iloc[-1])
        bb_lower = float(bb["lower"].iloc[-1])
        bb_upper = float(bb["upper"].iloc[-1])
        curr_atr = float(atr_vals.iloc[-1])

        if curr_fast > curr_slow and price <= bb_lower and curr_rsi < 35:
            return Signal(
                symbol=context.symbol,
                action=SignalType.BUY,
                price=price,
                confidence=0.65,
                strategy=self.name,
                timeframe=context.timeframe,
                stop_loss=price - 1.5 * curr_atr,
                take_profit=price + 2 * curr_atr,
                metadata={"rsi": curr_rsi, "volume_ratio": volume_ratio},
            )

        if curr_fast < curr_slow and price >= bb_upper and curr_rsi > 65:
            return Signal(
                symbol=context.symbol,
                action=SignalType.SELL,
                price=price,
                confidence=0.65,
                strategy=self.name,
                timeframe=context.timeframe,
                stop_loss=price + 1.5 * curr_atr,
                take_profit=price - 2 * curr_atr,
                metadata={"rsi": curr_rsi, "volume_ratio": volume_ratio},
            )
        return None
