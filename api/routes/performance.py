"""Performance API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.models import PerformanceResponse
from database.session import get_db

router = APIRouter(prefix="/performance", tags=["performance"])


@router.get("", response_model=PerformanceResponse)
async def get_performance(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> PerformanceResponse:
    del session  # kept for route compatibility
    bot = getattr(request.app.state, "bot", None)
    balance = 10000.0
    equity = balance
    open_positions = 0

    if bot:
        status = await bot.get_status()
        balance = status["balance"]
        equity = status.get("equity", balance)
        open_positions = status["open_positions"]

    account_id = bot.account_manager.active_account_id if bot else None
    account = bot.account_manager.active_account if bot else None

    closed_rows: list[dict[str, object]] = []
    daily_pnl = 0.0
    strategy_stats: dict[str, dict[str, float]] = {}

    if bot:
        closed_rows = await bot.get_merged_closed_trades(limit=1000)
        if bot.config.is_paper:
            from database.repositories.trades import TradeRepository
            from database.session import async_session_factory

            factory = async_session_factory()
            async with factory() as db_session:
                repo = TradeRepository(db_session)
                daily_pnl = await repo.get_daily_pnl(account_id=account_id)
        else:
            daily_pnl = await bot._exchange_daily_pnl()
        strategy_stats = bot.get_strategy_stats_from_trades(closed_rows)

    wins = sum(1 for t in closed_rows if t.get("pnl") and float(t["pnl"]) > 0)
    total = len(closed_rows)
    win_rate = (wins / total * 100) if total > 0 else 0.0

    gross_profit = sum(float(t["pnl"]) for t in closed_rows if t.get("pnl") and float(t["pnl"]) > 0)
    gross_loss = abs(sum(float(t["pnl"]) for t in closed_rows if t.get("pnl") and float(t["pnl"]) < 0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0

    return PerformanceResponse(
        balance=balance,
        equity=equity,
        win_rate=win_rate,
        profit_factor=profit_factor,
        max_drawdown=0.0,
        sharpe_ratio=0.0,
        total_trades=total,
        open_positions=open_positions,
        daily_pnl=daily_pnl,
        strategy_stats=strategy_stats,
        account_id=account_id,
        account_name=account.name if account else None,
    )
