"""Train AI trade filter from historical backtest labels."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ai.features import FeatureExtractor
from ai.model import TradeFilterModel
from ai.storage import ModelStore
from backtest.engine import BacktestEngine
from exchange.binance_futures import BinanceFuturesClient
from strategies.base import SignalType, StrategyContext
from utils.config import AppConfig, load_config
from utils.logger import get_logger

logger = get_logger(__name__)

MIN_SAMPLES = 30


def _collect_labeled_features(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    engine: BacktestEngine,
    feature_extractor: FeatureExtractor,
) -> tuple[np.ndarray, np.ndarray]:
    """Run a lightweight backtest loop and label entries win/loss."""
    X_rows: list[np.ndarray] = []
    y_rows: list[int] = []

    min_bars = 60
    open_position: dict[str, Any] | None = None
    entry_features: np.ndarray | None = None
    balance = engine.initial_balance

    for i in range(min_bars, len(df)):
        window = df.iloc[: i + 1].copy()
        price = float(window["close"].iloc[-1])
        context = StrategyContext(
            symbol=symbol,
            timeframe=timeframe,
            candles=window,
            latest_price=price,
        )

        if open_position:
            exit_reason = engine._check_exit(open_position, price, window)
            if exit_reason:
                pnl = engine._close_position(open_position, price, balance)
                if entry_features is not None:
                    X_rows.append(entry_features)
                    y_rows.append(1 if pnl > 0 else 0)
                entry_features = None
                open_position = None
                balance += pnl
            continue

        for strategy in engine.strategies:
            signal = strategy.analyze(context)
            if signal is None or signal.action == SignalType.HOLD:
                continue

            from indicators.volatility import atr
            from risk.manager import RiskContext

            atr_val = float(atr(window, 14).values.iloc[-1])
            risk_context = RiskContext(balance=balance, equity=balance, open_positions=[])
            risk_result = engine.risk_manager.check_signal(signal, risk_context, atr_val)
            if not risk_result.approved:
                continue

            entry_price = engine._apply_slippage(signal.price, signal.action)
            side = "LONG" if signal.action == SignalType.BUY else "SHORT"
            open_position = {
                "symbol": symbol,
                "side": side,
                "entry_price": entry_price,
                "quantity": risk_result.quantity,
                "stop_loss": risk_result.stop_loss,
                "take_profit": risk_result.take_profit,
            }
            entry_features = feature_extractor.extract(window)
            break

    if open_position and entry_features is not None:
        price = float(df["close"].iloc[-1])
        pnl = engine._close_position(open_position, price, balance)
        X_rows.append(entry_features)
        y_rows.append(1 if pnl > 0 else 0)

    if not X_rows:
        return np.empty((0, len(FeatureExtractor.FEATURE_NAMES))), np.empty((0,))

    return np.vstack(X_rows), np.array(y_rows, dtype=np.int32)


async def train_from_market(
    config: AppConfig | None = None,
    *,
    symbols: list[str] | None = None,
    timeframe: str = "15m",
    kline_limit: int = 1000,
    model_name: str = "trade_filter",
) -> dict[str, Any]:
    """Fetch klines, label entries from backtest logic, train and store model."""
    cfg = config or load_config()
    symbols = symbols or cfg.symbols
    store = ModelStore()

    exchange = BinanceFuturesClient(
        api_key=cfg.settings.binance_api_key,
        api_secret=cfg.settings.binance_api_secret,
        testnet=cfg.is_testnet,
    )
    await exchange.connect()

    engine = BacktestEngine(
        strategies_config=cfg.strategies,
        risk_config=cfg.risk,
        backtest_config=cfg.get("backtest", {}),
    )
    feature_extractor = FeatureExtractor()

    all_X: list[np.ndarray] = []
    all_y: list[np.ndarray] = []
    per_symbol: dict[str, int] = {}

    try:
        for symbol in symbols:
            candles = await exchange.get_klines(symbol, timeframe, limit=kline_limit)
            if not candles:
                logger.warning("train_ai_no_candles", symbol=symbol)
                continue
            df = pd.DataFrame(candles)
            X, y = _collect_labeled_features(df, symbol, timeframe, engine, feature_extractor)
            if len(y):
                all_X.append(X)
                all_y.append(y)
                per_symbol[symbol] = int(len(y))
    finally:
        await exchange.disconnect()

    if not all_y:
        return {
            "ok": False,
            "error": "No labeled samples collected. Try more symbols or a higher kline limit.",
            "samples": 0,
        }

    X = np.vstack(all_X)
    y = np.concatenate(all_y)
    if len(y) < MIN_SAMPLES:
        return {
            "ok": False,
            "error": f"Need at least {MIN_SAMPLES} samples, got {len(y)}.",
            "samples": int(len(y)),
            "per_symbol": per_symbol,
        }

    model = TradeFilterModel()
    metrics = model.train(X, y)
    path = store.save(model, name=model_name, set_active=True, archive=True)

    return {
        "ok": True,
        "path": str(path),
        "samples": int(len(y)),
        "wins": int(y.sum()),
        "losses": int(len(y) - y.sum()),
        "per_symbol": per_symbol,
        **metrics,
    }
