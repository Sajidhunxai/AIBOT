"""Abstract exchange interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class OrderResult:
    order_id: str
    symbol: str
    side: str
    order_type: str
    price: float
    quantity: float
    status: str
    filled_quantity: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class PositionInfo:
    symbol: str
    side: str
    quantity: float
    entry_price: float
    unrealized_pnl: float
    leverage: int
    margin_type: str = "cross"
    opened_at: datetime | None = None
    position_side: str = ""


@dataclass
class TickerInfo:
    symbol: str
    price: float
    bid: float
    ask: float
    volume_24h: float
    price_change_pct: float


class ExchangeBase(ABC):
    """Abstract base for exchange clients."""

    @abstractmethod
    async def connect(self) -> None:
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        ...

    @abstractmethod
    async def get_balance(self) -> float:
        ...

    @abstractmethod
    async def get_positions(self, symbol: str | None = None) -> list[PositionInfo]:
        ...

    @abstractmethod
    async def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        position_side: str = "BOTH",
    ) -> OrderResult:
        ...

    @abstractmethod
    async def place_limit_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        position_side: str = "BOTH",
    ) -> OrderResult:
        ...

    @abstractmethod
    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        ...

    @abstractmethod
    async def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 500,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    async def get_orderbook(self, symbol: str, limit: int = 20) -> dict[str, Any]:
        ...

    @abstractmethod
    async def get_funding_rate(self, symbol: str) -> float:
        ...

    @abstractmethod
    async def get_open_interest(self, symbol: str) -> float:
        ...

    @abstractmethod
    async def set_leverage(self, symbol: str, leverage: int) -> None:
        ...

    @abstractmethod
    async def set_hedge_mode(self, enabled: bool) -> None:
        ...
