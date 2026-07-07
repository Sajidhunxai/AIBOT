"""Pytest configuration and fixtures."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def sample_ohlcv() -> pd.DataFrame:
    """Generate sample OHLCV data for testing."""
    np.random.seed(42)
    n = 200
    close = 50000 + np.cumsum(np.random.randn(n) * 100)
    high = close + np.abs(np.random.randn(n) * 50)
    low = close - np.abs(np.random.randn(n) * 50)
    open_ = close + np.random.randn(n) * 20
    volume = np.abs(np.random.randn(n) * 1000) + 500

    return pd.DataFrame(
        {
            "open_time": pd.date_range("2024-01-01", periods=n, freq="15min"),
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "close_time": pd.date_range("2024-01-01", periods=n, freq="15min") + pd.Timedelta(minutes=14),
            "quote_volume": volume * close,
            "trades_count": np.random.randint(100, 1000, n),
        }
    )


@pytest.fixture
def risk_config() -> dict:
    return {
        "risk_per_trade_pct": 1.0,
        "max_daily_loss_pct": 3.0,
        "max_drawdown_pct": 10.0,
        "max_concurrent_positions": 3,
        "max_positions_per_symbol": 1,
        "cooldown_after_loss_minutes": 30,
        "signal_cooldown_minutes": 15,
        "max_unrealized_loss_pct": 5.0,
        "emergency_close_unrealized_loss_pct": 8.0,
        "max_total_exposure_pct": 100.0,
        "block_duplicate_side": True,
        "atr_stop_multiplier": 2.0,
        "take_profit_rr": 2.0,
    }


@pytest.fixture
def strategies_config() -> dict:
    return {
        "ema_cross_rsi": {
            "enabled": True,
            "fast_ema": 9,
            "slow_ema": 21,
            "rsi_period": 14,
            "rsi_filter_long_min": 40,
            "rsi_filter_short_max": 60,
        },
        "trend_following": {"enabled": False},
        "scalping": {"enabled": False},
        "breakout": {"enabled": False},
        "mean_reversion": {"enabled": False},
    }
