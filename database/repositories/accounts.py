"""Trading account repository."""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import AccountType, TradingAccount


class AccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self) -> list[TradingAccount]:
        result = await self.session.execute(
            select(TradingAccount).order_by(TradingAccount.id.asc())
        )
        return list(result.scalars().all())

    async def get_by_id(self, account_id: int) -> TradingAccount | None:
        result = await self.session.execute(
            select(TradingAccount).where(TradingAccount.id == account_id)
        )
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> TradingAccount | None:
        result = await self.session.execute(
            select(TradingAccount).where(TradingAccount.name == name)
        )
        return result.scalar_one_or_none()

    async def get_active(self) -> TradingAccount | None:
        result = await self.session.execute(
            select(TradingAccount).where(TradingAccount.is_active.is_(True)).limit(1)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        name: str,
        account_type: AccountType,
        paper_balance: float = 10000.0,
        notes: str | None = None,
        activate: bool = False,
    ) -> TradingAccount:
        account = TradingAccount(
            name=name,
            account_type=account_type,
            paper_balance=paper_balance,
            is_active=activate,
            notes=notes,
        )
        self.session.add(account)
        await self.session.flush()
        await self.session.refresh(account)
        return account

    async def set_active(self, account_id: int) -> TradingAccount | None:
        await self.session.execute(update(TradingAccount).values(is_active=False))
        account = await self.get_by_id(account_id)
        if account is None:
            return None
        account.is_active = True
        await self.session.flush()
        return account

    async def update_balance(self, account_id: int, balance: float) -> TradingAccount | None:
        account = await self.get_by_id(account_id)
        if account is None:
            return None
        account.paper_balance = balance
        await self.session.flush()
        return account
