"""Signal repository."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Signal


class SignalRepository:
    """CRUD operations for trading signals."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, signal: Signal) -> Signal:
        self.session.add(signal)
        await self.session.flush()
        await self.session.refresh(signal)
        return signal

    async def get_recent(self, limit: int = 50, account_id: int | None = None) -> list[Signal]:
        query = select(Signal).order_by(Signal.created_at.desc()).limit(limit)
        if account_id is not None:
            query = query.where(Signal.account_id == account_id)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def delete_for_account(self, account_id: int) -> int:
        result = await self.session.execute(
            delete(Signal).where(Signal.account_id == account_id)
        )
        return int(result.rowcount or 0)

    async def delete_demo_history(self, account_id: int) -> int:
        result = await self.session.execute(
            delete(Signal).where(
                (Signal.account_id == account_id) | (Signal.account_id.is_(None))
            )
        )
        return int(result.rowcount or 0)

    async def get_by_strategy(self, strategy: str, limit: int = 50) -> list[Signal]:
        query = (
            select(Signal)
            .where(Signal.strategy == strategy)
            .order_by(Signal.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
