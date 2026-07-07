#!/usr/bin/env bash
# Deploy AIBotTrade on a small EC2 (no RDS) — Postgres + API in Docker, dashboard on host.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PUBLIC_IP="${PUBLIC_IP:-$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo "127.0.0.1")}"

echo "==> AIBotTrade EC2 deploy (IP: $PUBLIC_IP)"

if ! command -v docker >/dev/null 2>&1; then
  sudo apt-get update
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y docker.io docker-compose-v2 git curl
  sudo usermod -aG docker "$USER" || true
fi

if [ ! -f .env ]; then
  cp .env.example .env
fi

# Postgres URLs are set by docker-compose.ec2-small.yml — point browser URLs at this server.
sed -i "s|^NEXT_PUBLIC_API_URL=.*|NEXT_PUBLIC_API_URL=http://${PUBLIC_IP}:8000|" .env || true
grep -q '^NEXT_PUBLIC_API_URL=' .env || echo "NEXT_PUBLIC_API_URL=http://${PUBLIC_IP}:8000" >> .env
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
NEXT_PUBLIC_API_URL="http://${PUBLIC_IP}:8000" npm run build

echo ""
echo "Done. Start dashboard in another screen/tmux:"
echo "  cd $ROOT/dashboard/frontend && NEXT_PUBLIC_API_URL=http://${PUBLIC_IP}:8000 npm start"
echo ""
echo "Open: http://${PUBLIC_IP}:3000"
echo "API:  http://${PUBLIC_IP}:8000"
echo ""
echo "Edit Binance keys: nano $ROOT/.env && sudo docker compose -f docker-compose.ec2-small.yml restart bot"
