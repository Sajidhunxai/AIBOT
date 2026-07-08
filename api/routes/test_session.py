"""Test session tracking API — baseline metrics for bot evaluation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from api.schemas.models import TestSessionResponse
from utils.test_session import (
    compute_session_metrics,
    dedupe_closed_trades,
    ensure_test_session,
    load_test_session,
    parse_started_at,
    reset_test_session,
)

router = APIRouter(prefix="/test-session", tags=["test-session"])


def _as_utc(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        closed = value
    else:
        try:
            closed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if closed.tzinfo is None:
        return closed.replace(tzinfo=UTC)
    return closed.astimezone(UTC)


def _session_trades_from_rows(
    rows: list[dict[str, Any]],
    started_at: datetime,
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for row in rows:
        closed = _as_utc(row.get("closed_at"))
        if closed is None or closed < started_at:
            continue
        filtered.append(
            {
                "pnl": row.get("pnl"),
                "closed_at": closed,
                "symbol": row.get("symbol"),
                "side": row.get("side"),
                "strategy": row.get("strategy"),
            }
        )
    return dedupe_closed_trades(filtered)


async def _exchange_realized_trades_since(bot: object, started_at: datetime) -> list[dict[str, Any]]:
    """Fallback rows from Binance REALIZED_PNL income since session start."""
    rows: list[dict[str, Any]] = []
    if bot.config.is_paper:  # type: ignore[attr-defined]
        return rows

    await bot.exchange.connect()  # type: ignore[attr-defined]
    for symbol in bot.config.symbols:  # type: ignore[attr-defined]
        try:
            items = await bot.exchange.get_income_history(  # type: ignore[attr-defined]
                "REALIZED_PNL",
                symbol=symbol,
                limit=200,
            )
        except Exception:
            continue
        for item in items:
            ts_ms = int(item.get("time", 0))
            if not ts_ms:
                continue
            ts = datetime.fromtimestamp(ts_ms / 1000, tz=UTC)
            if ts < started_at:
                continue
            income = float(item.get("income") or 0)
            if abs(income) < 1e-12:
                continue
            rows.append(
                {
                    "pnl": income,
                    "closed_at": ts,
                    "symbol": symbol,
                    "side": "MIXED",
                    "strategy": "binance_income",
                }
            )
    return rows


async def _session_trades_for_account(
    bot: object,
    account_id: int,
    started_at: datetime,
) -> list[dict[str, Any]]:
    del account_id
    rows = await bot.get_merged_closed_trades(limit=2000)  # type: ignore[attr-defined]
    session_trades = _session_trades_from_rows(rows, started_at)
    if session_trades or bot.config.is_paper:  # type: ignore[attr-defined]
        return session_trades

    return dedupe_closed_trades(await _exchange_realized_trades_since(bot, started_at))


async def _current_equity(bot: object) -> float:
    if not bot.config.is_paper:  # type: ignore[attr-defined]
        await bot.sync_exchange_state()  # type: ignore[attr-defined]
    status = await bot.get_status()  # type: ignore[attr-defined]
    equity = float(status.get("equity", status["balance"]))
    if equity > 0:
        return equity
    return float(status["balance"])


async def _build_response(
    bot: object,
    account: object,
    account_id: int,
    auto_initialized: bool,
) -> TestSessionResponse:
    current_equity = await _current_equity(bot)
    status = await bot.get_status()  # type: ignore[attr-defined]
    mode = str(status.get("mode", "paper"))

    session = load_test_session(account_id)
    if session is None:
        raise HTTPException(status_code=500, detail="Failed to load test session")

    started_at = parse_started_at(str(session.get("started_at")))
    session_trades = await _session_trades_for_account(bot, account_id, started_at)
    metrics = compute_session_metrics(session, current_equity, session_trades)

    return TestSessionResponse(
        account_id=account_id,
        account_name=account.name,  # type: ignore[attr-defined]
        mode=mode,
        started_at=metrics["started_at"],
        days_running=metrics["days_running"],
        starting_balance=metrics["starting_balance"],
        current_equity=metrics["current_equity"],
        wallet_balance=float(status.get("balance", current_equity)),
        unrealized_pnl=float(status.get("unrealized_pnl", 0.0)),
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

    current_equity = await _current_equity(bot)
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

    current_equity = await _current_equity(bot)
    reset_test_session(account_id, current_equity)
    return await _build_response(bot, account, account_id, False)
