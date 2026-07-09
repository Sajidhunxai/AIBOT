#!/usr/bin/env bash
# Build (optional) and start Next.js standalone dashboard via systemd.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FRONTEND="$ROOT/dashboard/frontend"
API_URL="${NEXT_PUBLIC_API_URL:-http://127.0.0.1:8000}"
DO_BUILD="${DO_BUILD:-1}"

cd "$FRONTEND"

if [ "$DO_BUILD" = "1" ]; then
  echo "==> Building dashboard..."
  export NEXT_PUBLIC_API_URL="$API_URL"
  npm run build
fi

echo "==> Preparing standalone assets..."
mkdir -p .next/standalone/.next
rm -rf .next/standalone/.next/static
cp -r .next/static .next/standalone/.next/static
rm -rf .next/standalone/public
cp -r public .next/standalone/public 2>/dev/null || true

echo "==> Restarting aibot-dashboard service..."
sudo systemctl stop aibot-dashboard 2>/dev/null || true
fuser -k 3000/tcp 2>/dev/null || true
pkill -f "next-server" 2>/dev/null || true
pkill -f "npm start" 2>/dev/null || true
sleep 2

if [ ! -f /etc/systemd/system/aibot-dashboard.service ]; then
  sudo tee /etc/systemd/system/aibot-dashboard.service > /dev/null << EOF
[Unit]
Description=AIBotTrade Dashboard (Next.js standalone)
After=network.target docker.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=$FRONTEND/.next/standalone
Environment=PORT=3000
Environment=HOSTNAME=0.0.0.0
Environment=NEXT_PUBLIC_API_URL=$API_URL
ExecStart=/usr/bin/node server.js
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
  sudo systemctl daemon-reload
  sudo systemctl enable aibot-dashboard
fi

sudo systemctl start aibot-dashboard
sleep 3

if ! systemctl is-active --quiet aibot-dashboard; then
  echo "ERROR: aibot-dashboard failed to start" >&2
  journalctl -u aibot-dashboard -n 20 --no-pager >&2 || true
  exit 1
fi

CHUNK=$(basename .next/static/chunks/app/page-*.js 2>/dev/null || echo "")
if [ -n "$CHUNK" ]; then
  code=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:3000/_next/static/chunks/app/$CHUNK" || echo "000")
  echo "chunk HTTP: $code"
fi

curl -sf http://127.0.0.1:3000/api/v1/status >/dev/null && echo "Dashboard proxy OK"
