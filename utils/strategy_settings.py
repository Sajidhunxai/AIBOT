"""Persist per-account strategy overrides from the dashboard."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from utils.logger import get_logger

logger = get_logger(__name__)

ACCOUNTS_DIR = Path("data/accounts")
LEGACY_STRATEGY_SETTINGS_PATH = Path("data/strategy_settings.json")


def account_strategy_path(account_id: int) -> Path:
    return ACCOUNTS_DIR / f"{account_id}_strategy.json"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError) as e:
        logger.error("strategy_settings_load_failed", path=str(path), error=str(e))
        return {}


def load_account_strategy(account_id: int, migrate_global: bool = True) -> dict[str, Any]:
    """Load strategy overrides for one account."""
    path = account_strategy_path(account_id)
    if path.exists():
        return _load_json(path)

    if migrate_global and LEGACY_STRATEGY_SETTINGS_PATH.exists():
        legacy = _load_json(LEGACY_STRATEGY_SETTINGS_PATH)
        if legacy:
            save_account_strategy(account_id, legacy)
            return legacy
    return {}


def save_account_strategy(account_id: int, strategies: dict[str, Any]) -> None:
    path = account_strategy_path(account_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(strategies, f, indent=2)
    logger.info("account_strategy_saved", account_id=account_id, file=str(path))


def merge_strategies(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for name, cfg in base.items():
        base_cfg = dict(cfg) if isinstance(cfg, dict) else {}
        over = overrides.get(name, {})
        if isinstance(over, dict):
            merged[name] = {**base_cfg, **over}
        else:
            merged[name] = base_cfg
    return merged


def get_merged_strategies_for_account(
    yaml_strategies: dict[str, Any],
    account_id: int,
) -> dict[str, Any]:
    return merge_strategies(yaml_strategies, load_account_strategy(account_id))
