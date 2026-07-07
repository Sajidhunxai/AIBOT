"""Configuration loading from YAML and environment variables."""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class TradingMode(str, Enum):
    LIVE = "live"
    TESTNET = "testnet"
    PAPER = "paper"


class Settings(BaseSettings):
    """Environment-based settings (secrets and runtime overrides)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = "development"
    log_level: str = "INFO"
    log_dir: str = "logs"
    config_path: str = "config/default.yaml"

    trading_mode: TradingMode = TradingMode.PAPER

    binance_api_key: str = ""
    binance_api_secret: str = ""
    binance_testnet: bool = True

    database_url: str = "postgresql+asyncpg://aibottrade:aibottrade@localhost:5432/aibottrade"
    database_sync_url: str = "postgresql://aibottrade:aibottrade@localhost:5432/aibottrade"

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_cors_origins: str = "http://localhost:3000"

    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    ai_filter_enabled: bool = False
    ai_model_path: str = "models/trade_filter.joblib"

    state_file: str = "data/bot_state.json"
    resume_on_start: bool = True

    @field_validator("trading_mode", mode="before")
    @classmethod
    def parse_trading_mode(cls, v: Any) -> TradingMode:
        if isinstance(v, TradingMode):
            return v
        return TradingMode(str(v).lower())

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]


class AppConfig:
    """Merged YAML + environment configuration."""

    def __init__(self, yaml_config: dict[str, Any], settings: Settings) -> None:
        self._config = yaml_config
        self.settings = settings

    @property
    def raw(self) -> dict[str, Any]:
        return self._config

    def get(self, key: str, default: Any = None) -> Any:
        keys = key.split(".")
        value: Any = self._config
        for k in keys:
            if not isinstance(value, dict):
                return default
            value = value.get(k)
            if value is None:
                return default
        return value

    @property
    def symbols(self) -> list[str]:
        return list(self.get("symbols", []))

    @property
    def timeframes(self) -> list[str]:
        return list(self.get("timeframes", []))

    @property
    def primary_timeframe(self) -> str:
        return str(self.get("primary_timeframe", "15m"))

    @property
    def hedge_mode(self) -> bool:
        return bool(self.get("exchange.hedge_mode", True))

    @property
    def risk(self) -> dict[str, Any]:
        return dict(self.get("risk", {}))

    @property
    def strategies(self) -> dict[str, Any]:
        return dict(self.get("strategies", {}))

    def enabled_strategies(self) -> list[str]:
        return [name for name, cfg in self.strategies.items() if cfg.get("enabled", False)]

    @property
    def leverage_default(self) -> int:
        return int(self.get("leverage.default", 10))

    def leverage_for_symbol(self, symbol: str) -> int:
        per_symbol = self.get("leverage.per_symbol", {})
        if isinstance(per_symbol, dict) and symbol in per_symbol:
            return int(per_symbol[symbol])
        return self.leverage_default

    @property
    def ai_filter_enabled(self) -> bool:
        env_override = self.settings.ai_filter_enabled
        yaml_enabled = bool(self.get("ai_filter.enabled", False))
        return env_override or yaml_enabled

    @property
    def is_paper(self) -> bool:
        return self.settings.trading_mode == TradingMode.PAPER

    @property
    def is_live(self) -> bool:
        return self.settings.trading_mode == TradingMode.LIVE

    @property
    def is_testnet(self) -> bool:
        return (
            self.settings.trading_mode == TradingMode.TESTNET
            or self.settings.binance_testnet
            or bool(self.get("exchange.testnet", True))
        )


def load_yaml_config(path: str | Path) -> dict[str, Any]:
    """Load YAML configuration file."""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    with config_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid YAML configuration in {config_path}")
    return data


def load_config(config_path: str | None = None) -> AppConfig:
    """Load merged application configuration."""
    settings = get_settings()
    path = config_path or settings.config_path
    yaml_config = load_yaml_config(path)
    return AppConfig(yaml_config, settings)


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
