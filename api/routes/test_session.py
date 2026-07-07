"""Test session tracking API — baseline metrics for bot evaluation."""

from __future__ import annotations

from datetime import UTC

from fastapi import APIRouter, HTTPException, Request

from api.schemas.models import TestSessionResponse
from database.repositories.trades import TradeRepository
from database.session import get_async_session
from utils.test_session import (
    compute_session_metrics,
    ensure_test_session,
    load_test_session,
    parse_started_at,
    reset_test_session,
)

router = APIRouter(prefix="/test-session", tags=["test-session"])


def _trade_row(t: object) -> dict[str, object]:
    return {
        "pnl": t.pnl,  # type: ignore[attr-defined]
        "closed_at": t.closed_at,  # type: ignore[attr-defined]
    }


async def _session_trades_for_account(account_id: int, started_at: object) -> list[dict[str, object]]:
    async with get_async_session() as session:
        repo = TradeRepository(session)
        rows = await repo.get_closed_trades(limit=2000, account_id=account_id)
    filtered: list[dict[str, object]] = []
    for t in rows:
        closed = t.closed_at
        if closed is None:
            continue
        if closed.tzinfo is None:
            closed = closed.replace(tzinfo=UTC)
        else:
            closed = closed.astimezone(UTC)
        if closed >= started_at:  # type: ignore[operator]
            filtered.append(_trade_row(t))
    return filtered


async def _build_response(
    bot: object,
    account: object,
    account_id: int,
    auto_initialized: bool,
) -> TestSessionResponse:
    status = await bot.get_status()  # type: ignore[attr-defined]
    current_equity = float(status.get("equity", status["balance"]))
    mode = str(status.get("mode", "paper"))

    session = load_test_session(account_id)
    if session is None:
        raise HTTPException(status_code=500, detail="Failed to load test session")

    started_at = parse_started_at(str(session.get("started_at")))
    session_trades = await _session_trades_for_account(account_id, started_at)
    metrics = compute_session_metrics(session, current_equity, session_trades)

    return TestSessionResponse(
        account_id=account_id,
        account_name=account.name,  # type: ignore[attr-defined]
        mode=mode,
        started_at=metrics["started_at"],
        days_running=metrics["days_running"],
        starting_balance=metrics["starting_balance"],
        current_equity=metrics["current_equity"],
        return_pct=metrics["return_pct"],
        session_pnl=metrics["session_pnl"],
        max_drawdown_pct=metrics["max_drawdown_pct"],
        closed_trades=metrics["closed_trades"],
        win_rate=metrics["win_rate"],
        profit_factor=metrics["profit_factor"],
        auto_initialized=auto_initialized,
    )


@router.get("", response_model=TestSessionResponse)
async def get_test_session(request: Request) -> TestSessionResponse:
    bot = getattr(request.app.state, "bot", None)
    if bot is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")

    account = bot.account_manager.active_account
    account_id = bot.account_manager.active_account_id
    if account is None or account_id is None:
        raise HTTPException(status_code=400, detail="No active account")

    status = await bot.get_status()
    current_equity = float(status.get("equity", status["balance"]))
    auto_initialized = load_test_session(account_id) is None
    ensure_test_session(account_id, current_equity)
    return await _build_response(bot, account, account_id, auto_initialized)


@router.post("/reset", response_model=TestSessionResponse)
async def reset_test_session_endpoint(request: Request) -> TestSessionResponse:
    bot = getattr(request.app.state, "bot", None)
    if bot is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")

    account = bot.account_manager.active_account
    account_id = bot.account_manager.active_account_id
    if account is None or account_id is None:
        raise HTTPException(status_code=400, detail="No active account")

    status = await bot.get_status()
    current_equity = float(status.get("equity", status["balance"]))
    reset_test_session(account_id, current_equity)
    return await _build_response(bot, account, account_id, False)
