"""AI model storage and training API."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from ai.storage import ModelStore, DEFAULT_MODEL_NAME
from ai.trainer import train_from_market
from utils.config import load_config

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/models")
async def list_models() -> dict:
    store = ModelStore()
    active = store.path_for(DEFAULT_MODEL_NAME)
    return {
        "models_dir": str(store.models_dir),
        "active_model": str(active) if active.exists() else None,
        "active_ready": active.exists() and store.load(DEFAULT_MODEL_NAME).is_ready,
        "models": store.list_models(),
    }


@router.post("/train")
async def train_model(
    request: Request,
    symbol: str | None = Query(None, description="Single symbol (default: all configured)"),
    timeframe: str = Query("15m"),
    kline_limit: int = Query(1000, ge=100, le=1500),
) -> dict:
    bot = getattr(request.app.state, "bot", None)
    config = bot.config if bot else load_config()  # type: ignore[union-attr]
    symbols = [symbol] if symbol else None
    result = await train_from_market(
        config,
        symbols=symbols,
        timeframe=timeframe,
        kline_limit=kline_limit,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "Training failed"))

    if bot is not None:
        reloaded = bot.reload_ai_model()
        result["reloaded"] = reloaded

    return result


@router.post("/reload")
async def reload_model(request: Request, name: str = Query("trade_filter")) -> dict:
    bot = getattr(request.app.state, "bot", None)
    if bot is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")

    store = ModelStore()
    path = store.path_for(name)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Model not found: {path}")

    ready = bot.reload_ai_model(str(path))
    return {"ok": True, "path": str(path), "ready": ready}
