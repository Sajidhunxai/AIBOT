#!/usr/bin/env bash
# Retrain AI trade filter on EC2 (manual or GitHub Actions schedule).
set -euo pipefail

cd ~/AIBOT

SYMBOLS="${TRAIN_SYMBOLS:-BTCUSDT ETHUSDT}"
TIMEFRAME="${TRAIN_TIMEFRAME:-15m}"
KLINE_LIMIT="${TRAIN_KLINE_LIMIT:-1500}"
MODEL_NAME="${TRAIN_MODEL_NAME:-trade_filter}"
API_URL="${API_INTERNAL_URL:-http://127.0.0.1:8000}"

echo "==> AIBotTrade AI retrain (symbols: $SYMBOLS, tf: $TIMEFRAME, limit: $KLINE_LIMIT)"

if ! sudo docker compose ps --status running bot | grep -q bot; then
  echo "Bot container not running — starting..."
  sudo docker compose up -d bot
  sleep 12
fi

ARGS=()
for s in $SYMBOLS; do
  ARGS+=(--symbol "$s")
done

sudo docker compose exec -T bot python -m core.main train-ai \
  "${ARGS[@]}" \
  --timeframe "$TIMEFRAME" \
  --limit "$KLINE_LIMIT" \
  --name "$MODEL_NAME"

echo "==> Reload model into running API"
curl -sf -X POST "${API_URL}/api/v1/ai/reload?name=${MODEL_NAME}" | head -c 500
echo
echo "==> Done. Models on disk:"
ls -la ~/AIBOT/models/*.joblib 2>/dev/null | tail -5
