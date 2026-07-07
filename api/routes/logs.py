"""Log API routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Query

from api.schemas.models import LogResponse
from utils.config import get_settings

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("", response_model=list[LogResponse])
async def get_logs(
    limit: int = Query(default=100, le=500),
    level: str | None = None,
) -> list[LogResponse]:
    settings = get_settings()
    log_file = Path(settings.log_dir) / "aibottrade.log"
    if not log_file.exists():
        return []

    lines = log_file.read_text(encoding="utf-8").strip().split("\n")
    entries: list[LogResponse] = []
    for i, line in enumerate(reversed(lines[-limit:])):
        parts = line.split(" | ", 3)
        if len(parts) < 4:
            continue
        log_level = parts[1].strip()
        if level and log_level != level.upper():
            continue
        entries.append(
            LogResponse(
                id=i,
                level=log_level,
                logger_name=parts[2].strip(),
                message=parts[3].strip(),
            )
        )
    return entries
