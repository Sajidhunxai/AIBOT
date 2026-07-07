"""Bot state persistence for crash recovery."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class BotState:
    balance: float = 0.0
    open_positions: list[dict[str, Any]] = field(default_factory=list)
    daily_pnl: float = 0.0
    total_trades: int = 0
    last_run: str = ""
    symbols: list[str] = field(default_factory=list)
    enabled_strategies: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class StateManager:
    """Persist and restore bot state across restarts."""

    def __init__(self, state_file: str = "data/bot_state.json") -> None:
        self.state_file = Path(state_file)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

    def save(self, state: BotState) -> None:
        state.last_run = datetime.now(UTC).isoformat()
        with self.state_file.open("w", encoding="utf-8") as f:
            json.dump(state.to_dict(), f, indent=2)
        logger.debug("state_saved", file=str(self.state_file))

    def load(self) -> BotState | None:
        if not self.state_file.exists():
            return None
        try:
            with self.state_file.open(encoding="utf-8") as f:
                data = json.load(f)
            return BotState(**data)
        except (json.JSONDecodeError, TypeError) as e:
            logger.error("state_load_failed", error=str(e))
            return None

    def clear(self) -> None:
        if self.state_file.exists():
            self.state_file.unlink()
