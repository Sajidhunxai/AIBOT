"""Mean Reversion strategy."""

from __future__ import annotations

from typing import Any

from indicators.momentum import adx, rsi
from indicators.volatility import atr, bollinger_bands
from strategies.base import Signal, SignalType, StrategyBase, StrategyContext


class MeanReversionStrategy(StrategyBase):
    name = "mean_reversion"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.bb_period = int(config.get("bb_period", 20))
        self.bb_std = float(config.get("bb_std", 2.0))
        self.rsi_period = int(config.get("rsi_period", 14))
        self.rsi_oversold = float(config.get("rsi_oversold", 25))
        self.rsi_overbought = float(config.get("rsi_overbought", 75))
        self.adx_max = float(config.get("adx_max", 20))

    def analyze(self, context: StrategyContext) -> Signal | None:
        df = context.candles
        if len(df) < self.bb_period + 5:
            return None

        close = df["close"]
        price = context.latest_price or float(close.iloc[-1])
        bb = bollinger_bands(close, self.bb_period, self.bb_std).values
        rsi_vals = rsi(close, self.rsi_period).values
        adx_result = adx(df, 14).values
        atr_vals = atr(df, 14).values

        curr_rsi = float(rsi_vals.iloc[-1])
        curr_adx = float(adx_result["adx"].iloc[-1])
        bb_lower = float(bb["lower"].iloc[-1])
        bb_upper = float(bb["upper"].iloc[-1])
        bb_middle = float(bb["middle"].iloc[-1])
        curr_atr = float(atr_vals.iloc[-1])

        if curr_adx > self.adx_max:
            return None

        if price <= bb_lower and curr_rsi <= self.rsi_oversold:
            return Signal(
                symbol=context.symbol,
                action=SignalType.BUY,
                price=price,
                confidence=min(0.85, 0.5 + (self.rsi_oversold - curr_rsi) / 50),
                strategy=self.name,
                timeframe=context.timeframe,
                stop_loss=price - 1.5 * curr_atr,
                take_profit=bb_middle,
                metadata={"rsi": curr_rsi, "adx": curr_adx, "bb_lower": bb_lower},
            )

        if price >= bb_upper and curr_rsi >= self.rsi_overbought:
            return Signal(
                symbol=context.symbol,
                action=SignalType.SELL,
                price=price,
                confidence=min(0.85, 0.5 + (curr_rsi - self.rsi_overbought) / 50),
                strategy=self.name,
                timeframe=context.timeframe,
                stop_loss=price + 1.5 * curr_atr,
                take_profit=bb_middle,
                metadata={"rsi": curr_rsi, "adx": curr_adx, "bb_upper": bb_upper},
            )
        return None
