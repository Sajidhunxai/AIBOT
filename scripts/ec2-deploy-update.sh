#!/usr/bin/env bash
# Pull latest main and restart live services on EC2.
# Used by GitHub Actions and manual: bash scripts/ec2-deploy-update.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
PUBLIC_IP="${PUBLIC_IP:-$(curl -sf --max-time 2 http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || true)}"
PUBLIC_IP="${PUBLIC_IP:-3.135.190.132}"
API_INTERNAL_URL="${API_INTERNAL_URL:-http://127.0.0.1:8000}"
BRANCH="${DEPLOY_BRANCH:-main}"

echo "==> AIBotTrade deploy update (IP: $PUBLIC_IP, branch: $BRANCH)"

if [ -d .git ]; then
  echo "==> Pull latest from GitHub"
  git fetch origin "$BRANCH"
  git reset --hard "origin/$BRANCH"
else
  echo "ERROR: $ROOT is not a git repository" >&2
  exit 1
fi

if [ -f .env ]; then
  sed -i 's/\r$//' .env
  grep -q '^APP_ENV=' .env && sed -i 's/^APP_ENV=.*/APP_ENV=production/' .env || echo 'APP_ENV=production' >> .env
  sed -i "s|^NEXT_PUBLIC_API_URL=.*|NEXT_PUBLIC_API_URL=${API_INTERNAL_URL}|" .env
  grep -q '^NEXT_PUBLIC_API_URL=' .env || echo "NEXT_PUBLIC_API_URL=${API_INTERNAL_URL}" >> .env
  sed -i "s|^API_CORS_ORIGINS=.*|API_CORS_ORIGINS=http://${PUBLIC_IP}:3000,http://localhost:3000,http://127.0.0.1:3000|" .env
  grep -q '^API_CORS_ORIGINS=' .env || echo "API_CORS_ORIGINS=http://${PUBLIC_IP}:3000,http://localhost:3000,http://127.0.0.1:3000" >> .env
fi

echo "==> Rebuild and restart API (Docker)"
sudo docker compose -f "$COMPOSE_FILE" up -d --build --force-recreate bot

echo "==> Wait for API"
for _ in $(seq 1 30); do
  if curl -sf "${API_INTERNAL_URL}/api/v1/status" >/dev/null 2>&1; then
    echo "API is up"
    break
  fi
  sleep 2
done
curl -sf "${API_INTERNAL_URL}/api/v1/status" | head -c 120 || { echo "API health check failed" >&2; exit 1; }
echo

echo "==> Rebuild dashboard (host Node)"
if ! command -v node >/dev/null 2>&1; then
  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
  sudo apt-get install -y nodejs
fi

cd dashboard/frontend
npm ci
NEXT_PUBLIC_API_URL="${API_INTERNAL_URL}" npm run build

echo "==> Restart dashboard"
pkill -f "next start" 2>/dev/null || true
pkill -f "next-server" 2>/dev/null || true
sleep 2
nohup env NEXT_PUBLIC_API_URL="${API_INTERNAL_URL}" npm start > ~/dashboard.log 2>&1 &

for _ in $(seq 1 20); do
  if curl -sf http://127.0.0.1:3000/ >/dev/null 2>&1; then
    echo "Dashboard is up"
    break
  fi
  sleep 2
done

curl -s -o /dev/null -w "dashboard:%{http_code} api:%{http_code}\n" \
  http://127.0.0.1:3000/ "${API_INTERNAL_URL}/api/v1/status"

echo ""
echo "Deploy complete: http://${PUBLIC_IP}:3000"
