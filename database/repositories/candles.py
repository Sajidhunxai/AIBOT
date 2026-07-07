"""Candle data repository."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Candle


class CandleRepository:
    """CRUD operations for candle data."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert_candles(self, candles: list[dict]) -> int:
        """Bulk upsert candles, ignoring duplicates."""
        if not candles:
            return 0
        stmt = insert(Candle).values(candles)
        stmt = stmt.on_conflict_do_nothing(
            index_elements=["symbol", "timeframe", "open_time"]
        )
        result = await self.session.execute(stmt)
        return result.rowcount or 0

    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 500,
    ) -> list[Candle]:
        """Fetch candles for symbol and timeframe."""
        query = (
            select(Candle)
            .where(Candle.symbol == symbol, Candle.timeframe == timeframe)
            .order_by(Candle.open_time.desc())
            .limit(limit)
        )
        if start:
            query = query.where(Candle.open_time >= start)
        if end:
            query = query.where(Candle.open_time <= end)
        result = await self.session.execute(query)
        candles = list(result.scalars().all())
        candles.reverse()
        return candles
