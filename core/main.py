"""Application entry point."""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys

from backtest.engine import BacktestEngine
from core.bot import TradingBot
from exchange.binance_futures import BinanceFuturesClient
from utils.config import load_config
from utils.logger import get_logger, setup_logging

logger = get_logger(__name__)


async def run_bot() -> None:
    """Run the trading bot."""
    bot = TradingBot()
    loop = asyncio.get_event_loop()

    def shutdown_handler() -> None:
        logger.info("shutdown_signal_received")
        asyncio.create_task(bot.stop())

    if sys.platform != "win32":
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, shutdown_handler)

    try:
        await bot.start()
        while bot._running:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        await bot.stop()


async def run_backtest(symbol: str, timeframe: str) -> None:
    """Run backtest for a symbol."""
    config = load_config()
    setup_logging(level="INFO")

    exchange = BinanceFuturesClient(
        api_key=config.settings.binance_api_key,
        api_secret=config.settings.binance_api_secret,
        testnet=config.is_testnet,
    )
    await exchange.connect()
    candles = await exchange.get_klines(symbol, timeframe, limit=500)
    await exchange.disconnect()

    import pandas as pd

    df = pd.DataFrame(candles)
    engine = BacktestEngine(
        strategies_config=config.strategies,
        risk_config=config.risk,
        backtest_config=config.get("backtest", {}),
    )
    result = engine.run({symbol: df}, symbol, timeframe)
    print("\n=== Backtest Results ===")
    for key, value in result.metrics.to_dict().items():
        print(f"  {key}: {value}")
    print(f"\nCharts saved: {result.chart_paths}")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="AIBotTrade - Binance Futures Trading Bot")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("run", help="Start the trading bot")
    subparsers.add_parser("api", help="Start the API server")

    bt_parser = subparsers.add_parser("backtest", help="Run backtest")
    bt_parser.add_argument("--symbol", default="BTCUSDT")
    bt_parser.add_argument("--timeframe", default="15m")

    args = parser.parse_args()

    if args.command == "backtest":
        asyncio.run(run_backtest(args.symbol, args.timeframe))
    elif args.command == "api":
        import uvicorn

        config = load_config()
        uvicorn.run(
            "api.app:app",
            host=config.settings.api_host,
            port=config.settings.api_port,
            reload=config.settings.app_env == "development",
        )
    else:
        asyncio.run(run_bot())


if __name__ == "__main__":
    main()
