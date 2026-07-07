"""Trade repository."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Trade, TradeSide, TradeStatus


class TradeRepository:
    """CRUD operations for trades."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, trade: Trade) -> Trade:
        self.session.add(trade)
        await self.session.flush()
        await self.session.refresh(trade)
        return trade

    async def get_open_trades(
        self, symbol: str | None = None, account_id: int | None = None
    ) -> list[Trade]:
        query = select(Trade).where(Trade.status == TradeStatus.OPEN)
        if symbol:
            query = query.where(Trade.symbol == symbol)
        if account_id is not None:
            query = query.where(Trade.account_id == account_id)
        query = query.order_by(Trade.opened_at.desc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def close_open_trade(
        self,
        symbol: str,
        side: TradeSide,
        exit_price: float,
        pnl: float,
        account_id: int | None = None,
    ) -> Trade | None:
        trades = await self.get_open_trades(symbol=symbol, account_id=account_id)
        trade = next((t for t in trades if t.side == side), None)
        if trade is None:
            return None
        pnl_pct = (
            (pnl / (trade.entry_price * trade.quantity) * 100)
            if trade.entry_price and trade.quantity
            else 0.0
        )
        return await self.close_trade(trade.id, exit_price, pnl, pnl_pct)

    async def get_closed_trades(
        self, limit: int = 100, account_id: int | None = None
    ) -> list[Trade]:
        query = select(Trade).where(Trade.status == TradeStatus.CLOSED)
        if account_id is not None:
            query = query.where(Trade.account_id == account_id)
        query = query.order_by(Trade.closed_at.desc()).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update_open_trade_stops(
        self,
        trade_id: int,
        *,
        stop_loss: float | None = None,
        trailing_stop: float | None = None,
        metadata_json: dict | None = None,
    ) -> Trade | None:
        result = await self.session.execute(select(Trade).where(Trade.id == trade_id))
        trade = result.scalar_one_or_none()
        if trade is None or trade.status != TradeStatus.OPEN:
            return None
        if stop_loss is not None:
            trade.stop_loss = stop_loss
        if trailing_stop is not None:
            trade.trailing_stop = trailing_stop
        if metadata_json is not None:
            trade.metadata_json = metadata_json
        await self.session.flush()
        return trade

    async def close_trade(
        self,
        trade_id: int,
        exit_price: float,
        pnl: float,
        pnl_pct: float,
        commission: float = 0.0,
    ) -> Trade | None:
        result = await self.session.execute(select(Trade).where(Trade.id == trade_id))
        trade = result.scalar_one_or_none()
        if trade is None:
            return None
        trade.exit_price = exit_price
        trade.pnl = pnl
        trade.pnl_pct = pnl_pct
        trade.commission = commission
        trade.status = TradeStatus.CLOSED
        trade.closed_at = datetime.now(UTC)
        await self.session.flush()
        return trade

    async def get_daily_pnl(self, account_id: int | None = None) -> float:
        today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        query = select(func.coalesce(func.sum(Trade.pnl), 0.0)).where(
            Trade.status == TradeStatus.CLOSED,
            Trade.closed_at >= today,
        )
        if account_id is not None:
            query = query.where(Trade.account_id == account_id)
        result = await self.session.execute(query)
        return float(result.scalar_one())

    async def count_open_by_side(self, symbol: str, side: TradeSide) -> int:
        query = select(func.count()).where(
            Trade.symbol == symbol,
            Trade.side == side,
            Trade.status == TradeStatus.OPEN,
        )
        result = await self.session.execute(query)
        return int(result.scalar_one())

    async def get_strategy_stats(self, account_id: int | None = None) -> dict[str, dict[str, float]]:
        query = (
            select(
                Trade.strategy,
                func.count(Trade.id).label("total"),
                func.sum(Trade.pnl).label("total_pnl"),
                func.count().filter(Trade.pnl > 0).label("wins"),
            )
            .where(Trade.status == TradeStatus.CLOSED)
            .group_by(Trade.strategy)
        )
        if account_id is not None:
            query = query.where(Trade.account_id == account_id)
        result = await self.session.execute(query)
        stats: dict[str, dict[str, float]] = {}
        for row in result:
            total = int(row.total or 0)
            wins = int(row.wins or 0)
            stats[row.strategy] = {
                "total_trades": total,
                "wins": wins,
                "losses": total - wins,
                "win_rate": (wins / total * 100) if total > 0 else 0.0,
                "total_pnl": float(row.total_pnl or 0.0),
            }
        return stats

    async def delete_for_account(self, account_id: int) -> int:
        result = await self.session.execute(delete(Trade).where(Trade.account_id == account_id))
        return int(result.rowcount or 0)

    async def delete_demo_history(self, account_id: int) -> int:
        """Remove paper trades for account plus legacy rows without account_id."""
        result = await self.session.execute(
            delete(Trade).where(
                Trade.is_paper.is_(True),
                (Trade.account_id == account_id) | (Trade.account_id.is_(None)),
            )
        )
        return int(result.rowcount or 0)
