"""EMA Cross with RSI Filter strategy."""

from __future__ import annotations

from typing import Any

import pandas as pd

from indicators.momentum import rsi
from indicators.trend import ema
from indicators.volatility import atr
from strategies.base import Signal, SignalType, StrategyBase, StrategyContext


class EMACrossRSIStrategy(StrategyBase):
    name = "ema_cross_rsi"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.fast_ema = int(config.get("fast_ema", 9))
        self.slow_ema = int(config.get("slow_ema", 21))
        self.rsi_period = int(config.get("rsi_period", 14))
        self.rsi_filter_long_min = float(config.get("rsi_filter_long_min", 40))
        self.rsi_filter_short_max = float(config.get("rsi_filter_short_max", 60))
        self.signal_mode = str(config.get("signal_mode", "trend")).lower()

    def analyze(self, context: StrategyContext) -> Signal | None:
        df = context.candles
        if len(df) < self.slow_ema + 5:
            return None

        close = df["close"]
        fast = ema(close, self.fast_ema).values
        slow = ema(close, self.slow_ema).values
        rsi_vals = rsi(close, self.rsi_period).values
        atr_vals = atr(df, 14).values

        prev_fast = float(fast.iloc[-2])
        prev_slow = float(slow.iloc[-2])
        curr_fast = float(fast.iloc[-1])
        curr_slow = float(slow.iloc[-1])
        curr_rsi = float(rsi_vals.iloc[-1])
        curr_atr = float(atr_vals.iloc[-1])
        price = context.latest_price or float(close.iloc[-1])

        bullish_cross = prev_fast <= prev_slow and curr_fast > curr_slow
        bearish_cross = prev_fast >= prev_slow and curr_fast < curr_slow
        bullish_trend = curr_fast > curr_slow
        bearish_trend = curr_fast < curr_slow

        long_ok = bullish_cross if self.signal_mode == "crossover" else bullish_trend
        short_ok = bearish_cross if self.signal_mode == "crossover" else bearish_trend

        if long_ok and curr_rsi > self.rsi_filter_long_min and curr_rsi < 70:
            return Signal(
                symbol=context.symbol,
                action=SignalType.BUY,
                price=price,
                confidence=min(0.9, 0.5 + (curr_rsi - 40) / 100),
                strategy=self.name,
                timeframe=context.timeframe,
                stop_loss=price - 2 * curr_atr,
                take_profit=price + 4 * curr_atr,
                metadata={"rsi": curr_rsi, "fast_ema": curr_fast, "slow_ema": curr_slow},
            )

        if short_ok and curr_rsi < self.rsi_filter_short_max and curr_rsi > 30:
            return Signal(
                symbol=context.symbol,
                action=SignalType.SELL,
                price=price,
                confidence=min(0.9, 0.5 + (60 - curr_rsi) / 100),
                strategy=self.name,
                timeframe=context.timeframe,
                stop_loss=price + 2 * curr_atr,
                take_profit=price - 4 * curr_atr,
                metadata={"rsi": curr_rsi, "fast_ema": curr_fast, "slow_ema": curr_slow},
            )
        return None
