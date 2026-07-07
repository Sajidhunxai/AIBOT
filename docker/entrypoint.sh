#!/bin/sh
set -e

echo "AIBotTrade starting (mode=${TRADING_MODE:-paper})..."

if [ -n "$DATABASE_SYNC_URL" ] && echo "$DATABASE_SYNC_URL" | grep -qi postgres; then
  echo "Waiting for PostgreSQL..."
  python - <<'PY'
import os
import sys
import time

from sqlalchemy import create_engine, text

url = os.environ.get("DATABASE_SYNC_URL", "")
if not url or "sqlite" in url.lower():
    sys.exit(0)

engine = create_engine(url, pool_pre_ping=True)
for attempt in range(1, 31):
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("PostgreSQL is ready")
        sys.exit(0)
    except Exception as exc:
        print(f"PostgreSQL not ready ({attempt}/30): {exc}")
        time.sleep(2)

print("Timed out waiting for PostgreSQL", file=sys.stderr)
sys.exit(1)
PY
fi

echo "Running database migrations..."
alembic upgrade head

exec "$@"
