"""Risk settings API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from api.schemas.models import RiskSettingsResponse, RiskSettingsUpdate
from utils.risk_settings import load_account_risk, save_account_risk

router = APIRouter(prefix="/risk", tags=["risk"])


def _settings_response(bot: object) -> RiskSettingsResponse:
    settings = bot.risk_manager.get_settings()  # type: ignore[attr-defined]
    settings["open_positions"] = (
        len(bot.paper_trader.positions) if bot.config.is_paper else 0  # type: ignore[attr-defined]
    )
    account = bot.account_manager.active_account  # type: ignore[attr-defined]
    if account:
        settings["account_id"] = account.id
        settings["account_name"] = account.name
    return RiskSettingsResponse(**settings)


@router.get("/settings", response_model=RiskSettingsResponse)
async def get_risk_settings(request: Request) -> RiskSettingsResponse:
    bot = getattr(request.app.state, "bot", None)
    if bot is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")
    return _settings_response(bot)


@router.put("/settings", response_model=RiskSettingsResponse)
async def update_risk_settings(
    request: Request,
    body: RiskSettingsUpdate,
) -> RiskSettingsResponse:
    bot = getattr(request.app.state, "bot", None)
    if bot is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")

    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No settings provided")

    emergency = updates.get("emergency_close_unrealized_loss_pct")
    unrealized = updates.get("max_unrealized_loss_pct")
    if emergency is not None and unrealized is not None and emergency < unrealized:
        raise HTTPException(
            status_code=400,
            detail="Emergency close % must be >= unrealized loss cap %",
        )

    bot.risk_manager.apply_settings(updates)

    account_id = bot.account_manager.active_account_id
    if account_id is None:
        raise HTTPException(status_code=400, detail="No active account")

    stored = {**load_account_risk(account_id, migrate_global=False), **updates}
    save_account_risk(account_id, stored)

    return _settings_response(bot)
