"""Trend Following strategy using EMA, ADX, and Supertrend."""

from __future__ import annotations

from typing import Any

from indicators.momentum import adx
from indicators.trend import ema, supertrend
from indicators.volatility import atr
from strategies.base import Signal, SignalType, StrategyBase, StrategyContext


class TrendFollowingStrategy(StrategyBase):
    name = "trend_following"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.ema_period = int(config.get("ema_period", 50))
        self.adx_period = int(config.get("adx_period", 14))
        self.adx_threshold = float(config.get("adx_threshold", 25))
        self.st_period = int(config.get("supertrend_period", 10))
        self.st_multiplier = float(config.get("supertrend_multiplier", 3.0))

    def analyze(self, context: StrategyContext) -> Signal | None:
        df = context.candles
        if len(df) < self.ema_period + 10:
            return None

        close = df["close"]
        price = context.latest_price or float(close.iloc[-1])
        ema_vals = ema(close, self.ema_period).values
        adx_result = adx(df, self.adx_period)
        st_result = supertrend(df, self.st_period, self.st_multiplier)
        atr_vals = atr(df, 14).values

        curr_ema = float(ema_vals.iloc[-1])
        curr_adx = float(adx_result.values["adx"].iloc[-1])
        st_direction = int(st_result.values["direction"].iloc[-1])
        curr_atr = float(atr_vals.iloc[-1])

        if curr_adx < self.adx_threshold:
            return None

        if price > curr_ema and st_direction == -1:
            return Signal(
                symbol=context.symbol,
                action=SignalType.BUY,
                price=price,
                confidence=min(0.95, 0.5 + curr_adx / 100),
                strategy=self.name,
                timeframe=context.timeframe,
                stop_loss=price - 2.5 * curr_atr,
                take_profit=price + 5 * curr_atr,
                metadata={"adx": curr_adx, "ema": curr_ema, "supertrend_dir": st_direction},
            )

        if price < curr_ema and st_direction == 1:
            return Signal(
                symbol=context.symbol,
                action=SignalType.SELL,
                price=price,
                confidence=min(0.95, 0.5 + curr_adx / 100),
                strategy=self.name,
                timeframe=context.timeframe,
                stop_loss=price + 2.5 * curr_atr,
                take_profit=price - 5 * curr_atr,
                metadata={"adx": curr_adx, "ema": curr_ema, "supertrend_dir": st_direction},
            )
        return None
