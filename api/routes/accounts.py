"""Trading account API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from utils.logger import get_logger

from api.schemas.models import (
    AccountResponse,
    ActivateAccountRequest,
    ActivateAccountResponse,
    CreateAccountRequest,
    ResetDemoRequest,
    SetBalanceRequest,
)

router = APIRouter(prefix="/accounts", tags=["accounts"])
logger = get_logger(__name__)


def _to_response(account: object, bot: object) -> AccountResponse:
    live_balance = None
    if not bot.config.is_paper:  # type: ignore[attr-defined]
        live_balance = bot._total_assets or bot._balance  # type: ignore[attr-defined]
    info = bot.account_manager.to_dict(  # type: ignore[attr-defined]
        account,
        running_account_ids=bot.running_accounts,  # type: ignore[attr-defined]
        live_balance=live_balance,
    )
    return AccountResponse(
        id=info["id"],
        name=info["name"],
        account_type=info["account_type"],
        paper_balance=info["paper_balance"],
        current_balance=info["current_balance"],
        is_active=info["is_active"],
        is_trading=info.get("is_trading", False),
        notes=info.get("notes"),
    )


@router.get("", response_model=list[AccountResponse])
async def list_accounts(request: Request) -> list[AccountResponse]:
    bot = getattr(request.app.state, "bot", None)
    if bot is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")
    if not bot.config.is_paper:
        try:
            await bot.sync_exchange_state()
        except Exception as e:
            logger.warning("exchange_balance_sync_failed", error=str(e))
    accounts = await bot.account_manager.list_accounts()
    return [_to_response(a, bot) for a in accounts]


@router.post("", response_model=AccountResponse)
async def create_account(request: Request, body: CreateAccountRequest) -> AccountResponse:
    bot = getattr(request.app.state, "bot", None)
    if bot is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")
    if bot._running:
        raise HTTPException(status_code=400, detail="Stop the bot before creating accounts")
    try:
        account = await bot.account_manager.create_account(
            name=body.name,
            account_type=body.account_type,
            paper_balance=body.paper_balance,
            notes=body.notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _to_response(account, bot)


@router.post("/{account_id}/activate", response_model=ActivateAccountResponse)
async def activate_account(
    request: Request,
    account_id: int,
    body: ActivateAccountRequest | None = None,
) -> ActivateAccountResponse:
    bot = getattr(request.app.state, "bot", None)
    if bot is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")
    start = body.start if body else False
    try:
        result = await bot.switch_account(account_id, start=start)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    account = bot.account_manager.active_account
    if account is None:
        raise HTTPException(status_code=500, detail="Account switch failed")

    if result["started"]:
        message = f"Trading started on {account.name} ({account.account_type.value}). Other accounts keep running."
    elif result["switched"]:
        message = f"Viewing {account.name}. Use Switch & Start to trade this account in parallel."
    elif result["running"]:
        message = f"{account.name} is already trading."
    else:
        message = f"{account.name} is active (not trading)."

    return ActivateAccountResponse(
        id=account.id,
        name=account.name,
        account_type=account.account_type.value,
        paper_balance=account.paper_balance,
        current_balance=bot.account_manager.trader_balance(account.id),
        is_active=True,
        is_trading=account.id in bot.running_accounts,
        notes=account.notes,
        switched=bool(result["switched"]),
        running=bool(result["running"]),
        running_accounts=result.get("running_accounts", []),
        started=bool(result["started"]),
        message=message,
    )


@router.post("/{account_id}/stop")
async def stop_account_trading(request: Request, account_id: int) -> dict[str, object]:
    bot = getattr(request.app.state, "bot", None)
    if bot is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")
    stopped = await bot.stop_account(account_id)
    if not stopped:
        raise HTTPException(status_code=400, detail="Account is not trading")
    account = await bot.account_manager.get_account(account_id)
    name = account.name if account else str(account_id)
    return {
        "status": "ok",
        "account_id": account_id,
        "message": f"Stopped trading on {name}",
        "running_accounts": bot._running_accounts_payload(),
    }


@router.put("/{account_id}/balance", response_model=AccountResponse)
async def set_account_balance(
    request: Request,
    account_id: int,
    body: SetBalanceRequest,
) -> AccountResponse:
    bot = getattr(request.app.state, "bot", None)
    if bot is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")
    if bot._running:
        raise HTTPException(
            status_code=400,
            detail="Stop the bot before changing balance (or use reset demo)",
        )
    try:
        account = await bot.account_manager.set_demo_balance(body.balance, account_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    bot._balance = bot.paper_trader.balance
    return _to_response(account, bot)


@router.post("/{account_id}/reset-demo")
async def reset_demo_account(
    request: Request,
    account_id: int,
    body: ResetDemoRequest,
) -> dict[str, object]:
    bot = getattr(request.app.state, "bot", None)
    if bot is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")
    if bot._running and body.close_positions:
        await bot.close_paper_positions()
    try:
        result = await bot.account_manager.reset_demo_account(
            account_id=account_id,
            balance=body.balance,
            clear_history=body.clear_history,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    bot._balance = bot.paper_trader.balance
    return {
        "status": "ok",
        **result,
        "message": (
            f"Demo reset: balance ${result['balance']:.2f}, "
            f"removed {result['deleted_trades']} trades and {result['deleted_signals']} signals"
        ),
    }
