#!/usr/bin/env bash
# Pull latest main and restart live services on EC2.
# Used by GitHub Actions and manual: bash scripts/ec2-deploy-update.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.ec2-small.yml}"
PUBLIC_IP="${PUBLIC_IP:-$(curl -sf --max-time 2 http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || true)}"
PUBLIC_IP="${PUBLIC_IP:-18.222.16.206}"
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

sed -i 's/\r$//' scripts/*.sh docker/entrypoint.sh 2>/dev/null || true
chmod +x scripts/ec2-deploy-update.sh scripts/ec2-restart-dashboard.sh 2>/dev/null || true

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
  if curl -sf "${API_INTERNAL_URL}/health" >/dev/null 2>&1; then
    echo "API is up"
    break
  fi
  sleep 2
done
curl -sf "${API_INTERNAL_URL}/health" || { echo "API health check failed" >&2; exit 1; }
echo

echo "==> Rebuild dashboard (host Node)"
if ! command -v node >/dev/null 2>&1; then
  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
  sudo apt-get install -y nodejs
fi

cd dashboard/frontend
npm ci
export NEXT_PUBLIC_API_URL="${API_INTERNAL_URL}"
bash "$ROOT/scripts/ec2-restart-dashboard.sh"

curl -s -o /dev/null -w "dashboard:%{http_code} api:%{http_code}\n" \
  http://127.0.0.1:3000/ "${API_INTERNAL_URL}/api/v1/status"

echo ""
echo "Deploy complete: http://${PUBLIC_IP}:3000"
