"""Leverage settings API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from api.schemas.models import LeverageSettingsResponse, LeverageSettingsUpdate
from utils.leverage_settings import load_account_leverage, save_account_leverage

router = APIRouter(prefix="/leverage", tags=["leverage"])


def _max_leverage(bot: object) -> int:
    return int(bot.config.get("leverage.max", 125))  # type: ignore[attr-defined]


def _settings_response(bot: object) -> LeverageSettingsResponse:
    account = bot.account_manager.active_account  # type: ignore[attr-defined]
    account_id = bot.account_manager.active_account_id  # type: ignore[attr-defined]
    settings = load_account_leverage(account_id, bot.config)  # type: ignore[attr-defined]
    symbols = list(bot.config.symbols)  # type: ignore[attr-defined]
    resolved = {
        symbol: bot.leverage_for_symbol(symbol, account_id=account_id)  # type: ignore[attr-defined]
        for symbol in symbols
    }
    return LeverageSettingsResponse(
        default=int(settings["default"]),
        max_leverage=_max_leverage(bot),
        per_symbol={str(k): int(v) for k, v in (settings.get("per_symbol") or {}).items()},
        resolved_per_symbol=resolved,
        symbols=symbols,
        mode=bot.settings.trading_mode.value,  # type: ignore[attr-defined]
        account_id=account_id,
        account_name=account.name if account else None,
    )


@router.get("/settings", response_model=LeverageSettingsResponse)
async def get_leverage_settings(request: Request) -> LeverageSettingsResponse:
    bot = getattr(request.app.state, "bot", None)
    if bot is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")
    return _settings_response(bot)


@router.put("/settings", response_model=LeverageSettingsResponse)
async def update_leverage_settings(
    request: Request,
    body: LeverageSettingsUpdate,
) -> LeverageSettingsResponse:
    bot = getattr(request.app.state, "bot", None)
    if bot is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")

    account_id = bot.account_manager.active_account_id
    if account_id is None:
        raise HTTPException(status_code=400, detail="No active account")

    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No settings provided")

    max_lev = _max_leverage(bot)
    current = load_account_leverage(account_id, bot.config)

    if "default" in updates:
        default = int(updates["default"])
        if default < 1 or default > max_lev:
            raise HTTPException(status_code=400, detail=f"Default leverage must be 1–{max_lev}")
        current["default"] = default

    if "per_symbol" in updates:
        per_symbol = current.get("per_symbol") or {}
        for symbol, value in updates["per_symbol"].items():
            lev = int(value)
            if lev < 1 or lev > max_lev:
                raise HTTPException(
                    status_code=400,
                    detail=f"Leverage for {symbol} must be 1–{max_lev}",
                )
            per_symbol[str(symbol)] = lev
        current["per_symbol"] = per_symbol

    save_account_leverage(account_id, current)

    if not bot.config.is_paper:
        try:
            await bot.apply_account_leverage(account_id)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Saved settings but Binance rejected leverage change: {e}",
            ) from e

    return _settings_response(bot)
