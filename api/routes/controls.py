"""Manual trade control routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from api.schemas.models import ClosePositionRequest, ManualTradeRequest

router = APIRouter(prefix="/controls", tags=["controls"])


async def _close_positions(bot: object, body: ClosePositionRequest) -> list[dict[str, object]]:
    aid = body.account_id or bot.account_manager.active_account_id  # type: ignore[attr-defined]
    if body.close_all:
        if bot.config.is_paper:  # type: ignore[attr-defined]
            return await bot.close_paper_positions(account_id=aid)  # type: ignore[attr-defined]
        return await bot.close_exchange_positions(account_id=aid)  # type: ignore[attr-defined]
    if body.position_id or body.symbol:
        if bot.config.is_paper:  # type: ignore[attr-defined]
            return await bot.close_paper_positions(  # type: ignore[attr-defined]
                position_id=body.position_id,
                symbol=body.symbol,
                account_id=aid,
            )
        return await bot.close_exchange_positions(  # type: ignore[attr-defined]
            position_id=body.position_id,
            symbol=body.symbol,
            account_id=aid,
        )
    raise HTTPException(status_code=400, detail="Provide position_id, symbol, or close_all=true")


@router.post("/trade")
async def manual_trade(request: Request, trade: ManualTradeRequest) -> dict[str, object]:
    bot = getattr(request.app.state, "bot", None)
    if bot is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")
    if not bot.running_accounts:
        raise HTTPException(status_code=400, detail="Start an account before placing manual trades")
    aid = bot.account_manager.active_account_id
    if aid not in bot.running_accounts:
        raise HTTPException(status_code=400, detail="Active account is not trading — use Switch & Start")

    side = trade.side.upper()
    try:
        result = await bot.place_manual_trade(
            symbol=trade.symbol,
            side=side,
            quantity=trade.quantity,
            stop_loss=None if trade.auto_sl_tp else trade.stop_loss,
            take_profit=None if trade.auto_sl_tp else trade.take_profit,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return {
        "status": "ok",
        "message": (
            f"{result['side']} {result['symbol']} · qty {result['quantity']} · "
            f"SL {result['stop_loss']:.2f} · TP {result['take_profit']:.2f}"
        ),
        **result,
    }


@router.post("/close")
async def close_position(request: Request, body: ClosePositionRequest) -> dict[str, object]:
    bot = getattr(request.app.state, "bot", None)
    if bot is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")

    try:
        closed = await _close_positions(bot, body)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if not closed:
        raise HTTPException(status_code=404, detail="No matching open position")

    total_pnl = sum(t["pnl"] for t in closed)
    balance = (
        bot.paper_trader.balance
        if bot.config.is_paper
        else bot._balance  # type: ignore[attr-defined]
    )
    return {
        "status": "ok",
        "closed": len(closed),
        "total_pnl": total_pnl,
        "balance": balance,
        "message": f"Closed {len(closed)} position(s), PnL: ${total_pnl:.2f}",
    }


@router.post("/close-all")
async def close_all_positions(request: Request) -> dict[str, object]:
    bot = getattr(request.app.state, "bot", None)
    if bot is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")

    aid = bot.account_manager.active_account_id
    try:
        if bot.config.is_paper:
            closed = await bot.close_paper_positions(account_id=aid)
        else:
            closed = await bot.close_exchange_positions(account_id=aid)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    total_pnl = sum(t["pnl"] for t in closed)
    balance = bot.paper_trader.balance if bot.config.is_paper else bot._balance
    return {
        "status": "ok",
        "closed": len(closed),
        "total_pnl": total_pnl,
        "balance": balance,
        "message": f"Closed all {len(closed)} position(s), PnL: ${total_pnl:.2f}",
    }


@router.post("/resume-risk")
async def resume_risk_trading(request: Request) -> dict[str, str]:
    bot = getattr(request.app.state, "bot", None)
    if bot is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")
    bot.risk_manager.resume_trading()
    return {"status": "ok", "message": "Risk trading resumed"}


@router.post("/start")
async def start_bot(request: Request) -> dict[str, str]:
    bot = getattr(request.app.state, "bot", None)
    if bot is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")
    aid = bot.account_manager.active_account_id
    if aid is None:
        raise HTTPException(status_code=400, detail="No active account")
    if aid in bot.running_accounts:
        return {"status": "already_running", "message": "Active account is already trading"}
    import asyncio

    account = bot.account_manager.active_account
    asyncio.create_task(bot.start_account(aid))
    account_name = account.name if account else "active account"
    return {
        "status": "started",
        "message": f"Started trading on {account_name} (other accounts keep running)",
    }


@router.post("/stop")
async def stop_bot(request: Request) -> dict[str, str]:
    bot = getattr(request.app.state, "bot", None)
    if bot is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")
    if not bot.running_accounts:
        return {"status": "already_stopped"}
    await bot.stop()
    return {"status": "stopped", "message": "Stopped all trading accounts"}
