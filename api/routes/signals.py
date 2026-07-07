"""Signal API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.models import SignalResponse
from database.repositories.signals import SignalRepository
from database.session import get_db

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("", response_model=list[SignalResponse])
async def get_signals(
    request: Request,
    limit: int = 50,
    session: AsyncSession = Depends(get_db),
) -> list[SignalResponse]:
    bot = getattr(request.app.state, "bot", None)
    account_id = bot.account_manager.active_account_id if bot else None
    repo = SignalRepository(session)
    signals = await repo.get_recent(limit=limit, account_id=account_id)
    return [
        SignalResponse(
            id=s.id,
            symbol=s.symbol,
            timeframe=s.timeframe,
            strategy=s.strategy,
            action=s.action.value,
            price=s.price,
            confidence=s.confidence,
            ai_approved=s.ai_approved,
            created_at=s.created_at,
        )
        for s in signals
    ]
