"""Per-account leverage overrides from the dashboard."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from utils.logger import get_logger

logger = get_logger(__name__)

ACCOUNTS_DIR = Path("data/accounts")


def account_leverage_path(account_id: int) -> Path:
    return ACCOUNTS_DIR / f"{account_id}_leverage.json"


def default_from_config(config: object) -> dict[str, Any]:
    """Build leverage settings dict from global YAML config."""
    per_symbol = config.get("leverage.per_symbol", {})  # type: ignore[attr-defined]
    if not isinstance(per_symbol, dict):
        per_symbol = {}
    return {
        "default": int(config.get("leverage.default", 10)),  # type: ignore[attr-defined]
        "per_symbol": {str(k): int(v) for k, v in per_symbol.items()},
    }


def load_account_leverage(account_id: int | None, config: object) -> dict[str, Any]:
    """Load leverage overrides for a trading account."""
    base = default_from_config(config)
    if account_id is None:
        return base
    path = account_leverage_path(account_id)
    if not path.exists():
        return base
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return base
        merged = {
            "default": int(data.get("default", base["default"])),
            "per_symbol": {**base["per_symbol"], **(data.get("per_symbol") or {})},
        }
        for key, value in (data.get("per_symbol") or {}).items():
            merged["per_symbol"][str(key)] = int(value)
        return merged
    except (json.JSONDecodeError, OSError, TypeError, ValueError) as e:
        logger.error("account_leverage_load_failed", account_id=account_id, error=str(e))
        return base


def save_account_leverage(account_id: int, settings: dict[str, Any]) -> None:
    path = account_leverage_path(account_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "default": int(settings.get("default", 10)),
        "per_symbol": {
            str(k): int(v) for k, v in (settings.get("per_symbol") or {}).items()
        },
    }
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    logger.info("account_leverage_saved", account_id=account_id, file=str(path))


def leverage_for_symbol(settings: dict[str, Any], symbol: str) -> int:
    per_symbol = settings.get("per_symbol") or {}
    if symbol in per_symbol:
        return int(per_symbol[symbol])
    return int(settings.get("default", 10))
