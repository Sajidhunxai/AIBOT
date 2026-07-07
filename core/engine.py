"""Strategy evaluation engine."""

from __future__ import annotations

from typing import Any

import pandas as pd

from ai.filter import AIFilter
from exchange.market_data import MarketDataManager
from strategies.base import Signal, StrategyBase, StrategyContext
from strategies.registry import StrategyRegistry
from utils.logger import get_logger

logger = get_logger(__name__)


class StrategyEngine:
    """Evaluate all enabled strategies and produce signals."""

    def __init__(
        self,
        strategies_config: dict[str, Any],
        ai_filter: AIFilter | None = None,
        primary_timeframe: str = "15m",
    ) -> None:
        self.strategies = StrategyRegistry.create_all(strategies_config)
        self.ai_filter = ai_filter
        self.primary_timeframe = primary_timeframe
        self._prev_open_interest: dict[str, float] = {}

    def evaluate(
        self,
        symbol: str,
        market_data: MarketDataManager,
        timeframe: str | None = None,
    ) -> list[Signal]:
        """Run all strategies and return actionable signals."""
        tf = timeframe or self.primary_timeframe
        candles = market_data.get_candles(symbol, tf)
        if candles.empty or len(candles) < 30:
            return []

        context = StrategyContext(
            symbol=symbol,
            timeframe=tf,
            candles=candles,
            funding_rate=market_data.get_funding_rate(symbol),
            open_interest=market_data.get_open_interest(symbol),
            orderbook=market_data.get_orderbook(symbol),
            latest_price=market_data.get_latest_price(symbol),
        )

        signals: list[Signal] = []
        prev_oi = self._prev_open_interest.get(symbol, 0.0)

        for strategy in self.strategies:
            try:
                signal = strategy.analyze(context)
                if signal is None:
                    continue

                if self.ai_filter:
                    approved, confidence, features = self.ai_filter.evaluate(
                        signal,
                        candles,
                        context.funding_rate,
                        context.open_interest,
                        prev_oi,
                    )
                    signal.metadata["ai_approved"] = approved
                    signal.metadata["ai_confidence"] = confidence
                    signal.metadata["ai_features"] = features
                    if not approved:
                        logger.info(
                            "signal_rejected_by_ai",
                            strategy=signal.strategy,
                            symbol=symbol,
                        )
                        continue

                signals.append(signal)
                logger.info(
                    "signal_generated",
                    strategy=signal.strategy,
                    symbol=symbol,
                    action=signal.action.value,
                    confidence=signal.confidence,
                )
            except Exception as e:
                logger.error(
                    "strategy_error",
                    strategy=strategy.name,
                    symbol=symbol,
                    error=str(e),
                )

        self._prev_open_interest[symbol] = context.open_interest
        return signals

    def reload(self, strategies_config: dict[str, Any]) -> None:
        """Hot-reload strategy instances after dashboard settings change."""
        self.strategies = StrategyRegistry.create_all(strategies_config)
        logger.info("strategies_reloaded", active=self.active_strategies)

    def diagnose(self, symbol: str, market_data: MarketDataManager) -> dict[str, Any]:
        """Explain why strategies are or are not signaling (for dashboard)."""
        tf = self.primary_timeframe
        candles = market_data.get_candles(symbol, tf)
        price = market_data.get_latest_price(symbol)
        if candles.empty or len(candles) < 30:
            return {"symbol": symbol, "timeframe": tf, "price": price, "ready": False, "strategies": {}}

        context = StrategyContext(
            symbol=symbol,
            timeframe=tf,
            candles=candles,
            funding_rate=market_data.get_funding_rate(symbol),
            open_interest=market_data.get_open_interest(symbol),
            orderbook=market_data.get_orderbook(symbol),
            latest_price=price,
        )
        results: dict[str, Any] = {}
        for strategy in self.strategies:
            try:
                signal = strategy.analyze(context)
                results[strategy.name] = {
                    "signal": signal.action.value if signal else None,
                    "confidence": signal.confidence if signal else None,
                }
            except Exception as e:
                results[strategy.name] = {"signal": None, "error": str(e)}
        return {
            "symbol": symbol,
            "timeframe": tf,
            "price": price,
            "ready": True,
            "strategies": results,
        }

    @property
    def active_strategies(self) -> list[str]:
        return [s.name for s in self.strategies]
