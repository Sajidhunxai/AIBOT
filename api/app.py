"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import accounts, ai, controls, leverage, logs, market, performance, positions, risk, signals, strategies, test_session, trades
from api.schemas.models import BotStatusResponse
from core.bot import TradingBot
from database.session import init_db
from utils.config import load_config
from utils.logger import get_logger, setup_logging

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    config = load_config()
    setup_logging(level=config.settings.log_level, log_dir=config.settings.log_dir)
    await init_db()
    bot = TradingBot(config)
    await bot.initialize_accounts()
    app.state.bot = bot
    logger.info("api_started")
    yield
    if bot._running:
        await bot.stop()
    logger.info("api_stopped")


app = FastAPI(
    title="AIBotTrade API",
    description="Binance Futures Trading Bot Dashboard API",
    version="1.0.0",
    lifespan=lifespan,
)

config = load_config()
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(trades.router, prefix="/api/v1")
app.include_router(signals.router, prefix="/api/v1")
app.include_router(performance.router, prefix="/api/v1")
app.include_router(positions.router, prefix="/api/v1")
app.include_router(controls.router, prefix="/api/v1")
app.include_router(logs.router, prefix="/api/v1")
app.include_router(market.router, prefix="/api/v1")
app.include_router(accounts.router, prefix="/api/v1")
app.include_router(risk.router, prefix="/api/v1")
app.include_router(leverage.router, prefix="/api/v1")
app.include_router(strategies.router, prefix="/api/v1")
app.include_router(test_session.router, prefix="/api/v1")
app.include_router(ai.router, prefix="/api/v1")


@app.get("/api/v1/status", response_model=BotStatusResponse)
async def get_status() -> BotStatusResponse:
    bot: TradingBot = app.state.bot
    status = await bot.get_status()
    return BotStatusResponse(**status)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}
