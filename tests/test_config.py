"""Configuration unit tests."""

from pathlib import Path

import pytest

from utils.config import AppConfig, Settings, TradingMode, load_yaml_config
from utils.helpers import clamp, pct_change, round_step, safe_float


class TestHelpers:
    def test_safe_float(self) -> None:
        assert safe_float("3.14") == pytest.approx(3.14)
        assert safe_float(None, 0.0) == 0.0
        assert safe_float("invalid", 1.0) == 1.0

    def test_round_step(self) -> None:
        assert round_step(1.2345, 0.01) == pytest.approx(1.23)

    def test_pct_change(self) -> None:
        assert pct_change(100, 110) == pytest.approx(10.0)

    def test_clamp(self) -> None:
        assert clamp(5, 0, 10) == 5
        assert clamp(-1, 0, 10) == 0
        assert clamp(15, 0, 10) == 10


class TestConfig:
    def test_load_yaml(self) -> None:
        config_path = Path("config/default.yaml")
        if not config_path.exists():
            pytest.skip("default.yaml not found")
        data = load_yaml_config(config_path)
        assert "symbols" in data
        assert "strategies" in data

    def test_trading_mode_enum(self) -> None:
        settings = Settings(trading_mode="paper")
        assert settings.trading_mode == TradingMode.PAPER

    def test_app_config_enabled_strategies(self) -> None:
        settings = Settings()
        yaml_data = {
            "symbols": ["BTCUSDT"],
            "strategies": {
                "ema_cross_rsi": {"enabled": True},
                "trend_following": {"enabled": False},
            },
        }
        config = AppConfig(yaml_data, settings)
        assert "ema_cross_rsi" in config.enabled_strategies()
        assert "trend_following" not in config.enabled_strategies()
