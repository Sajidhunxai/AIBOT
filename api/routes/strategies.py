"""Strategy settings API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from api.schemas.models import StrategiesSettingsResponse, StrategiesSettingsUpdate

router = APIRouter(prefix="/strategies", tags=["strategies"])

KNOWN_STRATEGIES = {
    "ema_cross_rsi",
    "trend_following",
    "scalping",
    "breakout",
    "mean_reversion",
}


@router.get("/settings", response_model=StrategiesSettingsResponse)
async def get_strategy_settings(request: Request) -> StrategiesSettingsResponse:
    bot = getattr(request.app.state, "bot", None)
    if bot is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")
    data = bot.get_strategy_settings()
    return StrategiesSettingsResponse(**data)


@router.put("/settings", response_model=StrategiesSettingsResponse)
async def update_strategy_settings(
    request: Request,
    body: StrategiesSettingsUpdate,
) -> StrategiesSettingsResponse:
    bot = getattr(request.app.state, "bot", None)
    if bot is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")
    if not body.strategies:
        raise HTTPException(status_code=400, detail="No strategy settings provided")

    unknown = set(body.strategies.keys()) - KNOWN_STRATEGIES
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown strategies: {', '.join(sorted(unknown))}")

    for name, cfg in body.strategies.items():
        mode = cfg.get("signal_mode")
        if mode is not None and name == "ema_cross_rsi":
            if str(mode).lower() not in ("trend", "crossover"):
                raise HTTPException(
                    status_code=400,
                    detail="ema_cross_rsi signal_mode must be 'trend' or 'crossover'",
                )

    data = bot.apply_strategy_settings(body.strategies)
    return StrategiesSettingsResponse(**data)
