"""Trade API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.models import TradeResponse
from database.repositories.trades import TradeRepository
from database.session import get_db

router = APIRouter(prefix="/trades", tags=["trades"])


def _to_trade_response(row: dict[str, object]) -> TradeResponse:
    return TradeResponse(
        id=int(row["id"]),  # type: ignore[arg-type]
        symbol=str(row["symbol"]),
        side=str(row["side"]),
        status=str(row["status"]),
        strategy=str(row["strategy"]),
        entry_price=float(row["entry_price"]),  # type: ignore[arg-type]
        exit_price=float(row["exit_price"]) if row.get("exit_price") is not None else None,  # type: ignore[arg-type]
        quantity=float(row["quantity"]),  # type: ignore[arg-type]
        pnl=float(row["pnl"]) if row.get("pnl") is not None else None,  # type: ignore[arg-type]
        pnl_pct=float(row["pnl_pct"]) if row.get("pnl_pct") is not None else None,  # type: ignore[arg-type]
        opened_at=row.get("opened_at"),  # type: ignore[arg-type]
        closed_at=row.get("closed_at"),  # type: ignore[arg-type]
    )


@router.get("/open", response_model=list[TradeResponse])
async def get_open_trades(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> list[TradeResponse]:
    bot = getattr(request.app.state, "bot", None)
    account_id = bot.account_manager.active_account_id if bot else None
    repo = TradeRepository(session)
    trades = await repo.get_open_trades(account_id=account_id)
    return [
        TradeResponse(
            id=t.id,
            symbol=t.symbol,
            side=t.side.value,
            status=t.status.value,
            strategy=t.strategy,
            entry_price=t.entry_price,
            exit_price=t.exit_price,
            quantity=t.quantity,
            pnl=t.pnl,
            pnl_pct=t.pnl_pct,
            opened_at=t.opened_at,
            closed_at=t.closed_at,
        )
        for t in trades
    ]


@router.get("/closed", response_model=list[TradeResponse])
async def get_closed_trades(
    request: Request,
    limit: int = 100,
    session: AsyncSession = Depends(get_db),
) -> list[TradeResponse]:
    bot = getattr(request.app.state, "bot", None)
    if bot is None:
        return []

    rows = await bot.get_merged_closed_trades(limit=limit)
    return [_to_trade_response(row) for row in rows]
