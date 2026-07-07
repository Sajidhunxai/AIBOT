"""Persist risk limit overrides from the dashboard."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_RISK_SETTINGS_PATH = "data/risk_settings.json"
ACCOUNTS_DIR = Path("data/accounts")


def account_risk_path(account_id: int) -> Path:
    return ACCOUNTS_DIR / f"{account_id}_risk.json"


def load_account_risk(account_id: int | None, migrate_global: bool = True) -> dict[str, Any]:
    """Load risk overrides for a trading account."""
    if account_id is None:
        return {}
    path = account_risk_path(account_id)
    if path.exists():
        try:
            with path.open(encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError) as e:
            logger.error("account_risk_load_failed", account_id=account_id, error=str(e))
            return {}

    if migrate_global and account_id == 1:
        global_settings = load_risk_overrides(DEFAULT_RISK_SETTINGS_PATH)
        if global_settings:
            save_account_risk(account_id, global_settings)
            return global_settings
    return {}


def save_account_risk(account_id: int, settings: dict[str, Any]) -> None:
    path = account_risk_path(account_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
    logger.info("account_risk_saved", account_id=account_id, file=str(path))


def load_risk_overrides(path: str = DEFAULT_RISK_SETTINGS_PATH) -> dict[str, Any]:
    settings_path = Path(path)
    if not settings_path.exists():
        return {}
    try:
        with settings_path.open(encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError) as e:
        logger.error("risk_settings_load_failed", error=str(e))
        return {}


def save_risk_overrides(settings: dict[str, Any], path: str = DEFAULT_RISK_SETTINGS_PATH) -> None:
    settings_path = Path(path)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    with settings_path.open("w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
    logger.info("risk_settings_saved", file=str(settings_path))
