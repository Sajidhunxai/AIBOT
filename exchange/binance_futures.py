"""Binance Futures REST API client."""

from __future__ import annotations

import hashlib
import hmac
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

import aiohttp
from tenacity import retry, stop_after_attempt, wait_exponential

from exchange.base import ExchangeBase, OrderResult, PositionInfo, TickerInfo
from exchange.rate_limiter import RateLimiter
from utils.helpers import (
    SymbolFilters,
    format_exchange_value,
    format_exchange_value_up,
    parse_symbol_filters,
    round_step,
    safe_float,
)
from utils.logger import get_logger

logger = get_logger(__name__)

TESTNET_BASE = "https://testnet.binancefuture.com"
LIVE_BASE = "https://fapi.binance.com"


class BinanceFuturesClient(ExchangeBase):
    """Async Binance Futures client with rate limiting and retries."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        testnet: bool = True,
        recv_window: int = 5000,
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self.recv_window = recv_window
        self.base_url = TESTNET_BASE if testnet else LIVE_BASE
        self._session: aiohttp.ClientSession | None = None
        self._rate_limiter = RateLimiter(rate=10.0, capacity=20.0)
        self._connected = False
        self._time_offset_ms = 0
        self._last_time_sync_mono = 0.0
        self._symbol_filters: dict[str, SymbolFilters] = {}

    async def connect(self) -> None:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"X-MBX-APIKEY": self.api_key},
                timeout=aiohttp.ClientTimeout(total=30),
            )
            logger.info("binance_connected", testnet=self.testnet)
        await self._sync_server_time()
        self._connected = True

    async def _ensure_time_sync(self, max_age_seconds: float = 30.0) -> None:
        """Re-sync clock if stale (PC drift causes -1021 recvWindow errors)."""
        if self._session is None or self._session.closed:
            return
        age = time.monotonic() - self._last_time_sync_mono
        if age >= max_age_seconds or self._last_time_sync_mono == 0:
            await self._sync_server_time()

    async def _sync_server_time(self) -> None:
        """Align signed request timestamps with Binance server clock."""
        if self._session is None:
            return
        try:
            local_before = time.time()
            url = f"{self.base_url}/fapi/v1/time"
            async with self._session.get(url) as resp:
                data = await resp.json()
            local_after = time.time()
            server_ms = int(data["serverTime"])
            local_mid_ms = int((local_before + local_after) * 500)
            self._time_offset_ms = server_ms - local_mid_ms
            self._last_time_sync_mono = time.monotonic()
            logger.debug("binance_time_synced", offset_ms=self._time_offset_ms)
        except Exception as e:
            logger.warning("binance_time_sync_failed", error=str(e))
            self._time_offset_ms = 0

    async def disconnect(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        self._connected = False
        logger.info("binance_disconnected")

    def _sign(self, params: dict[str, Any]) -> str:
        query = urlencode(params)
        return hmac.new(
            self.api_secret.encode("utf-8"),
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        signed: bool = False,
        benign_codes: frozenset[int] | None = None,
    ) -> Any:
        await self._rate_limiter.acquire()
        if self._session is None:
            raise RuntimeError("Client not connected")

        base_params = dict(params or {})
        last_error: aiohttp.ClientResponseError | None = None

        for attempt in range(2):
            params = dict(base_params)
            if signed:
                await self._ensure_time_sync()
                params["timestamp"] = int(time.time() * 1000) + self._time_offset_ms
                params["recvWindow"] = self.recv_window
                params["signature"] = self._sign(params)

            url = f"{self.base_url}{endpoint}"
            async with self._session.request(method, url, params=params) as resp:
                data = await resp.json()
                if resp.status >= 400:
                    code = data.get("code") if isinstance(data, dict) else None
                    if benign_codes and code in benign_codes:
                        logger.info(
                            "binance_api_benign",
                            code=code,
                            endpoint=endpoint,
                            msg=data.get("msg") if isinstance(data, dict) else None,
                        )
                        return data
                    if code == -1021 and signed and attempt == 0:
                        logger.warning("binance_timestamp_retry", endpoint=endpoint)
                        await self._sync_server_time()
                        last_error = aiohttp.ClientResponseError(
                            resp.request_info,
                            resp.history,
                            status=resp.status,
                            message=str(data),
                        )
                        continue
                    logger.error("binance_api_error", status=resp.status, data=data)
                    raise aiohttp.ClientResponseError(
                        resp.request_info,
                        resp.history,
                        status=resp.status,
                        message=str(data),
                    )
                return data

        if last_error is not None:
            raise last_error
        raise RuntimeError("Binance request failed without response")

    async def get_balance(self) -> float:
        snap = await self.get_wallet_snapshot()
        return snap["balance"]

    async def get_wallet_snapshot(self) -> dict[str, float]:
        """Return wallet balance, equity, and unrealized PnL from Binance Futures."""
        data = await self._request("GET", "/fapi/v2/account", signed=True)
        wallet = safe_float(data.get("totalWalletBalance"))
        unrealized = safe_float(data.get("totalUnrealizedProfit"))
        margin = safe_float(data.get("totalMarginBalance"))
        available = safe_float(data.get("availableBalance"))
        equity = margin if margin > 0 else wallet + unrealized
        return {
            "balance": wallet,
            "equity": equity,
            "unrealized_pnl": unrealized,
            "available": available,
        }

    async def get_positions(self, symbol: str | None = None) -> list[PositionInfo]:
        data = await self._request("GET", "/fapi/v2/positionRisk", signed=True)
        positions: list[PositionInfo] = []
        for p in data:
            qty = safe_float(p.get("positionAmt"))
            if qty == 0:
                continue
            sym = p.get("symbol", "")
            if symbol and sym != symbol:
                continue
            side = "LONG" if qty > 0 else "SHORT"
            opened_at = None
            update_ms = p.get("updateTime")
            if update_ms:
                opened_at = datetime.fromtimestamp(int(update_ms) / 1000, tz=UTC)
            positions.append(
                PositionInfo(
                    symbol=sym,
                    side=side,
                    quantity=abs(qty),
                    entry_price=safe_float(p.get("entryPrice")),
                    unrealized_pnl=safe_float(p.get("unRealizedProfit")),
                    leverage=int(safe_float(p.get("leverage"), 1)),
                    position_side=str(p.get("positionSide", "")),
                    opened_at=opened_at,
                )
            )
        return positions

    async def get_user_trades(self, symbol: str, limit: int = 100) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"symbol": symbol, "limit": min(limit, 1000)}
        data = await self._request("GET", "/fapi/v1/userTrades", params=params, signed=True)
        return data if isinstance(data, list) else []

    async def get_income_history(
        self,
        income_type: str = "REALIZED_PNL",
        symbol: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "incomeType": income_type,
            "limit": min(limit, 1000),
        }
        if symbol:
            params["symbol"] = symbol
        data = await self._request("GET", "/fapi/v1/income", params=params, signed=True)
        return data if isinstance(data, list) else []

    async def get_symbol_filters(self, symbol: str) -> SymbolFilters:
        if symbol not in self._symbol_filters:
            await self._load_exchange_info()
        return self._symbol_filters.get(symbol, SymbolFilters(tick_size=0.01, step_size=0.001))

    async def _load_exchange_info(self) -> None:
        data = await self._request("GET", "/fapi/v1/exchangeInfo")
        symbols = data.get("symbols", []) if isinstance(data, dict) else []
        for info in symbols:
            sym = info.get("symbol")
            if sym:
                self._symbol_filters[sym] = parse_symbol_filters(info)
        logger.debug("binance_exchange_info_loaded", symbols=len(self._symbol_filters))

    def format_price(self, symbol: str, price: float) -> str:
        filters = self._symbol_filters.get(symbol, SymbolFilters(tick_size=0.01, step_size=0.001))
        return format_exchange_value(price, filters.tick_size)

    def format_quantity(self, symbol: str, quantity: float, *, for_order: bool = False) -> str:
        filters = self._symbol_filters.get(symbol, SymbolFilters(tick_size=0.01, step_size=0.001))
        if for_order:
            return format_exchange_value_up(quantity, filters.step_size)
        return format_exchange_value(quantity, filters.step_size)

    async def order_quantity(
        self,
        symbol: str,
        quantity: float,
        entry_price: float,
    ) -> float:
        """Return quantity rounded up to lot step and meeting min notional."""
        from utils.helpers import ensure_min_notional_quantity

        filters = await self.get_symbol_filters(symbol)
        return ensure_min_notional_quantity(
            quantity,
            entry_price,
            filters.min_notional,
            filters.step_size,
            filters.min_qty,
        )

    async def _place_algo_conditional_order(
        self,
        symbol: str,
        position_side: str,
        order_type: str,
        trigger_price: float,
        *,
        hedge_mode: bool = True,
        working_type: str = "CONTRACT_PRICE",
    ) -> OrderResult:
        """Place STOP_MARKET / TAKE_PROFIT_MARKET via Binance Algo Order API."""
        pos = position_side.upper()
        close_side = "SELL" if pos == "LONG" else "BUY"
        await self.get_symbol_filters(symbol)
        params: dict[str, Any] = {
            "algoType": "CONDITIONAL",
            "symbol": symbol,
            "side": close_side,
            "type": order_type,
            "triggerPrice": self.format_price(symbol, trigger_price),
            "closePosition": "true",
            "workingType": working_type,
        }
        if hedge_mode:
            params["positionSide"] = pos
        data = await self._request("POST", "/fapi/v1/algoOrder", params=params, signed=True)
        return self._parse_algo_order(data)

    async def place_stop_loss_market(
        self,
        symbol: str,
        position_side: str,
        stop_price: float,
        *,
        hedge_mode: bool = True,
        working_type: str = "CONTRACT_PRICE",
    ) -> OrderResult:
        """Place a STOP_MARKET algo order that closes the full position."""
        return await self._place_algo_conditional_order(
            symbol,
            position_side,
            "STOP_MARKET",
            stop_price,
            hedge_mode=hedge_mode,
            working_type=working_type,
        )

    async def place_take_profit_market(
        self,
        symbol: str,
        position_side: str,
        stop_price: float,
        *,
        hedge_mode: bool = True,
        working_type: str = "CONTRACT_PRICE",
    ) -> OrderResult:
        """Place a TAKE_PROFIT_MARKET algo order that closes the full position."""
        return await self._place_algo_conditional_order(
            symbol,
            position_side,
            "TAKE_PROFIT_MARKET",
            stop_price,
            hedge_mode=hedge_mode,
            working_type=working_type,
        )

    async def cancel_algo_order(self, symbol: str, algo_id: str) -> bool:
        params = {"symbol": symbol, "algoId": algo_id}
        await self._request("DELETE", "/fapi/v1/algoOrder", params=params, signed=True)
        return True

    async def cancel_all_open_orders(self, symbol: str) -> None:
        params = {"symbol": symbol}
        for endpoint in ("/fapi/v1/allOpenOrders", "/fapi/v1/algoOpenOrders"):
            try:
                await self._request("DELETE", endpoint, params=params, signed=True)
            except Exception as e:
                logger.debug("cancel_open_orders_skipped", symbol=symbol, endpoint=endpoint, error=str(e))

    async def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        position_side: str = "BOTH",
        entry_price: float | None = None,
    ) -> OrderResult:
        if entry_price and entry_price > 0:
            quantity = await self.order_quantity(symbol, quantity, entry_price)
        else:
            await self.get_symbol_filters(symbol)
        params: dict[str, Any] = {
            "symbol": symbol,
            "side": side.upper(),
            "type": "MARKET",
            "quantity": self.format_quantity(symbol, quantity, for_order=True),
        }
        if position_side != "BOTH":
            params["positionSide"] = position_side
        data = await self._request("POST", "/fapi/v1/order", params=params, signed=True)
        return self._parse_order(data)

    async def close_position_market(
        self,
        symbol: str,
        position_side: str,
        quantity: float,
        *,
        hedge_mode: bool = True,
    ) -> OrderResult:
        """Close an open futures position with a market order."""
        order_side = "SELL" if position_side.upper() == "LONG" else "BUY"
        params: dict[str, Any] = {
            "symbol": symbol,
            "side": order_side,
            "type": "MARKET",
            "quantity": quantity,
        }
        if hedge_mode:
            params["positionSide"] = position_side.upper()
        else:
            params["reduceOnly"] = "true"
        data = await self._request("POST", "/fapi/v1/order", params=params, signed=True)
        return self._parse_order(data)

    async def place_limit_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        position_side: str = "BOTH",
    ) -> OrderResult:
        params: dict[str, Any] = {
            "symbol": symbol,
            "side": side.upper(),
            "type": "LIMIT",
            "quantity": quantity,
            "price": price,
            "timeInForce": "GTC",
        }
        if position_side != "BOTH":
            params["positionSide"] = position_side
        data = await self._request("POST", "/fapi/v1/order", params=params, signed=True)
        return self._parse_order(data)

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        params = {"symbol": symbol, "orderId": order_id}
        await self._request("DELETE", "/fapi/v1/order", params=params, signed=True)
        return True

    async def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 500,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"symbol": symbol, "interval": interval, "limit": limit}
        if start_time:
            params["startTime"] = int(start_time.timestamp() * 1000)
        if end_time:
            params["endTime"] = int(end_time.timestamp() * 1000)
        data = await self._request("GET", "/fapi/v1/klines", params=params)
        candles = []
        for k in data:
            candles.append(
                {
                    "open_time": datetime.fromtimestamp(k[0] / 1000, tz=UTC),
                    "open": safe_float(k[1]),
                    "high": safe_float(k[2]),
                    "low": safe_float(k[3]),
                    "close": safe_float(k[4]),
                    "volume": safe_float(k[5]),
                    "close_time": datetime.fromtimestamp(k[6] / 1000, tz=UTC),
                    "quote_volume": safe_float(k[7]),
                    "trades_count": int(k[8]),
                }
            )
        return candles

    async def get_orderbook(self, symbol: str, limit: int = 20) -> dict[str, Any]:
        params = {"symbol": symbol, "limit": limit}
        data = await self._request("GET", "/fapi/v1/depth", params=params)
        return {
            "bids": [[safe_float(b[0]), safe_float(b[1])] for b in data.get("bids", [])],
            "asks": [[safe_float(a[0]), safe_float(a[1])] for a in data.get("asks", [])],
            "last_update_id": data.get("lastUpdateId"),
        }

    async def get_funding_rate(self, symbol: str) -> float:
        params = {"symbol": symbol}
        data = await self._request("GET", "/fapi/v1/premiumIndex", params=params)
        return safe_float(data.get("lastFundingRate"))

    async def get_open_interest(self, symbol: str) -> float:
        params = {"symbol": symbol}
        data = await self._request("GET", "/fapi/v1/openInterest", params=params)
        return safe_float(data.get("openInterest"))

    async def set_hedge_mode(self, enabled: bool) -> None:
        params = {"dualSidePosition": "true" if enabled else "false"}
        await self._request(
            "POST",
            "/fapi/v1/positionSide/dual",
            params=params,
            signed=True,
            benign_codes=frozenset({-4059}),
        )

    async def set_leverage(self, symbol: str, leverage: int) -> None:
        params = {"symbol": symbol, "leverage": leverage}
        await self._request(
            "POST",
            "/fapi/v1/leverage",
            params=params,
            signed=True,
            benign_codes=frozenset({-4028}),
        )

    async def get_ticker(self, symbol: str) -> TickerInfo:
        params = {"symbol": symbol}
        data = await self._request("GET", "/fapi/v1/ticker/24hr", params=params)
        return TickerInfo(
            symbol=symbol,
            price=safe_float(data.get("lastPrice")),
            bid=safe_float(data.get("bidPrice")),
            ask=safe_float(data.get("askPrice")),
            volume_24h=safe_float(data.get("volume")),
            price_change_pct=safe_float(data.get("priceChangePercent")),
        )

    def _parse_algo_order(self, data: dict[str, Any]) -> OrderResult:
        return OrderResult(
            order_id=str(data.get("algoId", "")),
            symbol=data.get("symbol", ""),
            side=data.get("side", ""),
            order_type=str(data.get("orderType", data.get("type", ""))),
            price=safe_float(data.get("triggerPrice") or data.get("price")),
            quantity=safe_float(data.get("quantity")),
            status=str(data.get("algoStatus", "")),
            filled_quantity=0.0,
            raw=data,
        )

    def _parse_order(self, data: dict[str, Any]) -> OrderResult:
        return OrderResult(
            order_id=str(data.get("orderId", "")),
            symbol=data.get("symbol", ""),
            side=data.get("side", ""),
            order_type=data.get("type", ""),
            price=safe_float(data.get("price")),
            quantity=safe_float(data.get("origQty")),
            status=data.get("status", ""),
            filled_quantity=safe_float(data.get("executedQty")),
            raw=data,
        )
