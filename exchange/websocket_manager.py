"""WebSocket manager for live market data."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

import websockets
from websockets.asyncio.client import ClientConnection

from utils.logger import get_logger

logger = get_logger(__name__)

TESTNET_WS = "wss://stream.binancefuture.com/ws"
LIVE_WS = "wss://fstream.binance.com/ws"


class WebSocketManager:
    """Manages WebSocket connections with automatic reconnection."""

    def __init__(
        self,
        testnet: bool = True,
        reconnect_delay: float = 5.0,
        max_reconnect_attempts: int = 10,
        ping_interval: float = 30.0,
    ) -> None:
        self.ws_base = TESTNET_WS if testnet else LIVE_WS
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_attempts = max_reconnect_attempts
        self.ping_interval = ping_interval
        self._connections: dict[str, ClientConnection] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._callbacks: dict[str, list[Callable[[dict[str, Any]], Awaitable[None]]]] = {}
        self._running = False

    def subscribe(
        self,
        stream: str,
        callback: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        """Register callback for a stream."""
        if stream not in self._callbacks:
            self._callbacks[stream] = []
        self._callbacks[stream].append(callback)

    async def start_stream(self, stream: str) -> None:
        """Start listening to a WebSocket stream."""
        if stream in self._tasks and not self._tasks[stream].done():
            return
        self._running = True
        self._tasks[stream] = asyncio.create_task(self._run_stream(stream))

    async def stop_stream(self, stream: str) -> None:
        """Stop a specific stream."""
        task = self._tasks.pop(stream, None)
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        conn = self._connections.pop(stream, None)
        if conn is not None:
            await conn.close()

    async def stop_all(self) -> None:
        """Stop all streams."""
        self._running = False
        streams = list(self._tasks.keys())
        for stream in streams:
            await self.stop_stream(stream)

    async def _run_stream(self, stream: str) -> None:
        attempts = 0
        while self._running and attempts < self.max_reconnect_attempts:
            try:
                url = f"{self.ws_base}/{stream}"
                async with websockets.connect(
                    url,
                    ping_interval=self.ping_interval,
                    ping_timeout=10,
                ) as ws:
                    self._connections[stream] = ws
                    attempts = 0
                    logger.info("websocket_connected", stream=stream)
                    async for message in ws:
                        data = json.loads(message)
                        await self._dispatch(stream, data)
            except asyncio.CancelledError:
                break
            except Exception as e:
                attempts += 1
                logger.warning(
                    "websocket_disconnected",
                    stream=stream,
                    attempt=attempts,
                    error=str(e),
                )
                await asyncio.sleep(self.reconnect_delay)
        if attempts >= self.max_reconnect_attempts:
            logger.error("websocket_max_reconnect", stream=stream)

    async def _dispatch(self, stream: str, data: dict[str, Any]) -> None:
        callbacks = self._callbacks.get(stream, [])
        for cb in callbacks:
            try:
                await cb(data)
            except Exception as e:
                logger.error("websocket_callback_error", stream=stream, error=str(e))

    @staticmethod
    def kline_stream(symbol: str, interval: str) -> str:
        """Build kline stream name."""
        return f"{symbol.lower()}@kline_{interval}"

    @staticmethod
    def depth_stream(symbol: str, levels: int = 20) -> str:
        """Build order book depth stream name."""
        return f"{symbol.lower()}@depth{levels}@100ms"
