"""Market data aggregation and caching."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from exchange.base import ExchangeBase
from exchange.websocket_manager import WebSocketManager
from utils.logger import get_logger

logger = get_logger(__name__)


class MarketDataManager:
    """Manages historical and live market data across symbols and timeframes."""

    def __init__(
        self,
        exchange: ExchangeBase,
        ws_manager: WebSocketManager,
        symbols: list[str],
        timeframes: list[str],
        candle_limit: int = 500,
    ) -> None:
        self.exchange = exchange
        self.ws_manager = ws_manager
        self.symbols = symbols
        self.timeframes = timeframes
        self.candle_limit = candle_limit
        self._candles: dict[str, dict[str, pd.DataFrame]] = defaultdict(dict)
        self._orderbooks: dict[str, dict[str, Any]] = {}
        self._funding_rates: dict[str, float] = {}
        self._open_interest: dict[str, float] = {}
        self._latest_prices: dict[str, float] = {}
        self._pending_bar_close: set[tuple[str, str]] = set()
        self._initial_strategy_eval: set[tuple[str, str]] = set()

    async def initialize(self) -> None:
        """Download historical candles and start WebSocket streams."""
        for symbol in self.symbols:
            for tf in self.timeframes:
                await self.download_candles(symbol, tf)
                stream = WebSocketManager.kline_stream(symbol, tf)
                self.ws_manager.subscribe(stream, self._make_kline_handler(symbol, tf))
                await self.ws_manager.start_stream(stream)
            depth_stream = WebSocketManager.depth_stream(symbol)
            self.ws_manager.subscribe(depth_stream, self._make_depth_handler(symbol))
            await self.ws_manager.start_stream(depth_stream)
            self._funding_rates[symbol] = await self.exchange.get_funding_rate(symbol)
            self._open_interest[symbol] = await self.exchange.get_open_interest(symbol)

    async def download_candles(self, symbol: str, timeframe: str) -> pd.DataFrame:
        """Download historical candles from exchange."""
        raw = await self.exchange.get_klines(symbol, timeframe, limit=self.candle_limit)
        df = self._to_dataframe(raw)
        self._candles[symbol][timeframe] = df
        if not df.empty:
            self._latest_prices[symbol] = float(df["close"].iloc[-1])
        logger.info("candles_downloaded", symbol=symbol, timeframe=timeframe, count=len(df))
        return df

    def get_candles(self, symbol: str, timeframe: str) -> pd.DataFrame:
        """Get cached candle DataFrame."""
        return self._candles.get(symbol, {}).get(timeframe, pd.DataFrame())

    def get_latest_price(self, symbol: str) -> float:
        return self._latest_prices.get(symbol, 0.0)

    def get_funding_rate(self, symbol: str) -> float:
        return self._funding_rates.get(symbol, 0.0)

    def get_open_interest(self, symbol: str) -> float:
        return self._open_interest.get(symbol, 0.0)

    def get_orderbook(self, symbol: str) -> dict[str, Any]:
        return self._orderbooks.get(symbol, {"bids": [], "asks": []})

    async def refresh_funding_and_oi(self, symbol: str) -> None:
        self._funding_rates[symbol] = await self.exchange.get_funding_rate(symbol)
        self._open_interest[symbol] = await self.exchange.get_open_interest(symbol)

    def _make_kline_handler(self, symbol: str, timeframe: str):
        async def handler(data: dict[str, Any]) -> None:
            kline = data.get("k", data)
            if not kline:
                return
            candle = {
                "open_time": datetime.fromtimestamp(kline["t"] / 1000, tz=UTC),
                "open": float(kline["o"]),
                "high": float(kline["h"]),
                "low": float(kline["l"]),
                "close": float(kline["c"]),
                "volume": float(kline["v"]),
                "close_time": datetime.fromtimestamp(kline["T"] / 1000, tz=UTC),
                "quote_volume": float(kline.get("q", 0)),
                "trades_count": int(kline.get("n", 0)),
            }
            self._update_candle(symbol, timeframe, candle, is_closed=kline.get("x", False))
            self._latest_prices[symbol] = candle["close"]

        return handler

    def _make_depth_handler(self, symbol: str):
        async def handler(data: dict[str, Any]) -> None:
            self._orderbooks[symbol] = {
                "bids": [[float(b[0]), float(b[1])] for b in data.get("b", [])],
                "asks": [[float(a[0]), float(a[1])] for a in data.get("a", [])],
                "last_update_id": data.get("u"),
            }

        return handler

    def _update_candle(
        self,
        symbol: str,
        timeframe: str,
        candle: dict[str, Any],
        is_closed: bool,
    ) -> None:
        if timeframe not in self._candles[symbol]:
            self._candles[symbol][timeframe] = self._to_dataframe([candle])
            return
        df = self._candles[symbol][timeframe]
        open_time = candle["open_time"]
        if not df.empty and df["open_time"].iloc[-1] == open_time:
            for col in ["open", "high", "low", "close", "volume", "close_time"]:
                df.at[df.index[-1], col] = candle[col]
        elif is_closed or df.empty:
            new_row = pd.DataFrame([candle])
            self._candles[symbol][timeframe] = pd.concat([df, new_row], ignore_index=True)
            if len(self._candles[symbol][timeframe]) > self.candle_limit:
                self._candles[symbol][timeframe] = self._candles[symbol][timeframe].iloc[
                    -self.candle_limit :
                ]
        if is_closed:
            self._pending_bar_close.add((symbol, timeframe))

    def should_evaluate_strategies(self, symbol: str, timeframe: str) -> bool:
        """Run strategies on startup and when a candle closes (avoids repeat entries)."""
        key = (symbol, timeframe)
        if key not in self._initial_strategy_eval:
            self._initial_strategy_eval.add(key)
            return True
        if key in self._pending_bar_close:
            self._pending_bar_close.discard(key)
            return True
        return False

    @staticmethod
    def _to_dataframe(candles: list[dict[str, Any]]) -> pd.DataFrame:
        if not candles:
            return pd.DataFrame(
                columns=[
                    "open_time",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "close_time",
                    "quote_volume",
                    "trades_count",
                ]
            )
        return pd.DataFrame(candles)
