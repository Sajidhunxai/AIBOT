"""Per-account test period tracking for dashboard metrics."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from utils.logger import get_logger

logger = get_logger(__name__)

ACCOUNTS_DIR = Path("data/accounts")


def test_session_path(account_id: int) -> Path:
    return ACCOUNTS_DIR / f"{account_id}_test.json"


def load_test_session(account_id: int) -> dict[str, Any] | None:
    path = test_session_path(account_id)
    if not path.exists():
        return None
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError) as e:
        logger.error("test_session_load_failed", account_id=account_id, error=str(e))
        return None


def save_test_session(account_id: int, session: dict[str, Any]) -> None:
    ACCOUNTS_DIR.mkdir(parents=True, exist_ok=True)
    path = test_session_path(account_id)
    with path.open("w", encoding="utf-8") as f:
        json.dump(session, f, indent=2)


def ensure_test_session(account_id: int, starting_balance: float) -> dict[str, Any]:
    existing = load_test_session(account_id)
    if existing and existing.get("started_at"):
        return existing
    session = {
        "account_id": account_id,
        "started_at": datetime.now(UTC).isoformat(),
        "starting_balance": starting_balance,
    }
    save_test_session(account_id, session)
    return session


def reset_test_session(account_id: int, starting_balance: float) -> dict[str, Any]:
    session = {
        "account_id": account_id,
        "started_at": datetime.now(UTC).isoformat(),
        "starting_balance": starting_balance,
    }
    save_test_session(account_id, session)
    return session


def parse_started_at(value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(UTC)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def compute_max_drawdown_pct(starting_balance: float, session_trades: list[dict[str, Any]]) -> float:
    """Peak-to-trough drawdown on equity built from session closed trades (chronological)."""
    if starting_balance <= 0:
        return 0.0
    chronological = sorted(
        session_trades,
        key=lambda t: parse_started_at(str(t.get("closed_at") or "")),
    )
    equity = starting_balance
    peak = equity
    max_dd = 0.0
    for trade in chronological:
        pnl = float(trade.get("pnl") or 0)
        equity += pnl
        if equity > peak:
            peak = equity
        if peak > 0:
            dd = (peak - equity) / peak * 100
            if dd > max_dd:
                max_dd = dd
    return max_dd


def compute_session_metrics(
    session: dict[str, Any],
    current_equity: float,
    session_trades: list[dict[str, Any]],
) -> dict[str, Any]:
    started_at = parse_started_at(str(session.get("started_at")))
    starting_balance = float(session.get("starting_balance") or 0)
    now = datetime.now(UTC)
    days_running = max(0.0, (now - started_at).total_seconds() / 86400)

    return_pct = 0.0
    if starting_balance > 0:
        return_pct = (current_equity - starting_balance) / starting_balance * 100

    wins = sum(1 for t in session_trades if float(t.get("pnl") or 0) > 0)
    total = len(session_trades)
    win_rate = (wins / total * 100) if total > 0 else 0.0

    gross_profit = sum(float(t["pnl"]) for t in session_trades if float(t.get("pnl") or 0) > 0)
    gross_loss = abs(sum(float(t["pnl"]) for t in session_trades if float(t.get("pnl") or 0) < 0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0
    session_pnl = sum(float(t.get("pnl") or 0) for t in session_trades)

    return {
        "started_at": started_at,
        "days_running": round(days_running, 1),
        "starting_balance": starting_balance,
        "current_equity": current_equity,
        "return_pct": round(return_pct, 2),
        "session_pnl": round(session_pnl, 2),
        "max_drawdown_pct": round(compute_max_drawdown_pct(starting_balance, session_trades), 2),
        "closed_trades": total,
        "win_rate": round(win_rate, 1),
        "profit_factor": round(profit_factor, 2),
    }
