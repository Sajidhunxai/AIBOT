#!/bin/sh
set -e

echo "AIBotTrade starting (mode=${TRADING_MODE:-paper})..."

if [ -n "$DATABASE_URL" ] && echo "$DATABASE_URL" | grep -qi postgres; then
  echo "Waiting for PostgreSQL..."
  python - <<'PY'
import asyncio
import os
import sys
from urllib.parse import urlparse


async def wait_for_db() -> bool:
    url = os.environ.get("DATABASE_URL", "")
    if not url or "sqlite" in url.lower():
        return True

    import asyncpg

    normalized = url.replace("postgresql+asyncpg://", "postgresql://")
    parsed = urlparse(normalized)
    for attempt in range(1, 31):
        try:
            conn = await asyncpg.connect(
                host=parsed.hostname or "localhost",
                port=parsed.port or 5432,
                user=parsed.username or "aibottrade",
                password=parsed.password or "",
                database=(parsed.path or "/aibottrade").lstrip("/"),
            )
            await conn.close()
            print("PostgreSQL is ready")
            return True
        except Exception as exc:
            print(f"PostgreSQL not ready ({attempt}/30): {exc}")
            await asyncio.sleep(2)
    return False


if not asyncio.run(wait_for_db()):
    print("Timed out waiting for PostgreSQL", file=sys.stderr)
    sys.exit(1)
PY
fi

echo "Running database migrations..."
alembic upgrade head

exec "$@"
