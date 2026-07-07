"""Lightweight SQLite schema upgrades for existing databases."""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

from utils.logger import get_logger

logger = get_logger(__name__)


async def upgrade_schema(engine: AsyncEngine) -> None:
    """Add new columns/tables on existing SQLite DBs without full Alembic."""
    async with engine.begin() as conn:
        def _upgrade(sync_conn: object) -> None:
            inspector = inspect(sync_conn)
            tables = inspector.get_table_names()

            if "trades" in tables:
                cols = {c["name"] for c in inspector.get_columns("trades")}
                if "account_id" not in cols:
                    sync_conn.execute(text("ALTER TABLE trades ADD COLUMN account_id INTEGER"))
                    logger.info("schema_added_column", table="trades", column="account_id")

            if "signals" in tables:
                cols = {c["name"] for c in inspector.get_columns("signals")}
                if "account_id" not in cols:
                    sync_conn.execute(text("ALTER TABLE signals ADD COLUMN account_id INTEGER"))
                    logger.info("schema_added_column", table="signals", column="account_id")

        await conn.run_sync(_upgrade)
