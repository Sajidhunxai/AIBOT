#!/usr/bin/env bash
# Deploy AIBotTrade on a small EC2 (no RDS) — Postgres + API in Docker, dashboard on host.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ -z "${PUBLIC_IP:-}" ]; then
  _meta_token="$(curl -sf -X PUT "http://169.254.169.254/latest/api/token" \
    -H "X-aws-ec2-metadata-token-ttl-seconds: 21600" 2>/dev/null || true)"
  if [ -n "$_meta_token" ]; then
    PUBLIC_IP="$(curl -sf -H "X-aws-ec2-metadata-token: $_meta_token" \
      http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || true)"
  else
    PUBLIC_IP="$(curl -sf http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || true)"
  fi
  PUBLIC_IP="${PUBLIC_IP:-127.0.0.1}"
fi

echo "==> AIBotTrade EC2 deploy (IP: $PUBLIC_IP)"

if ! command -v docker >/dev/null 2>&1; then
  sudo apt-get update
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y docker.io docker-compose-v2 git curl
  sudo usermod -aG docker "$USER" || true
fi

if [ ! -f .env ]; then
  cp .env.example .env
fi

# CORS uses the browser origin; Next proxies /api/v1 to localhost (see next.config.js).
sed -i "s|^NEXT_PUBLIC_API_URL=.*|NEXT_PUBLIC_API_URL=http://127.0.0.1:8000|" .env || true
grep -q '^NEXT_PUBLIC_API_URL=' .env || echo "NEXT_PUBLIC_API_URL=http://127.0.0.1:8000" >> .env
sed -i "s|^API_CORS_ORIGINS=.*|API_CORS_ORIGINS=http://${PUBLIC_IP}:3000,http://localhost:3000|" .env || true
grep -q '^API_CORS_ORIGINS=' .env || echo "API_CORS_ORIGINS=http://${PUBLIC_IP}:3000,http://localhost:3000" >> .env

echo "==> Starting Postgres + API (Docker)..."
sudo docker compose -f docker-compose.ec2-small.yml up -d --build

echo "==> Dashboard (Node on host — lighter than Docker build)..."
if ! command -v node >/dev/null 2>&1; then
  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
  sudo apt-get install -y nodejs
fi

cd dashboard/frontend
npm ci
bash "$ROOT/scripts/ec2-restart-dashboard.sh"
echo ""
echo "Open: http://${PUBLIC_IP}:3000"
echo "API:  http://${PUBLIC_IP}:8000"
echo ""
echo "Edit Binance keys: nano $ROOT/.env && sudo docker compose -f docker-compose.ec2-small.yml restart bot"
