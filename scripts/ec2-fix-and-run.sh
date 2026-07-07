#!/usr/bin/env bash
# One-shot fix + deploy on EC2 (Postgres + API in Docker, dashboard on host).
set -euo pipefail

cd ~/AIBOT

echo "==> 1/5 Ensure psycopg2 for Alembic"
grep -q '^psycopg2-binary' requirements.txt || echo 'psycopg2-binary==2.9.10' >> requirements.txt

echo "==> 2/5 Set public URLs"
IP="${PUBLIC_IP:-3.135.190.132}"
sed -i "s|^NEXT_PUBLIC_API_URL=.*|NEXT_PUBLIC_API_URL=http://${IP}:8000|" .env
sed -i "s|^API_CORS_ORIGINS=.*|API_CORS_ORIGINS=http://${IP}:3000,http://localhost:3000|" .env
grep -q '^NEXT_PUBLIC_API_URL=' .env || echo "NEXT_PUBLIC_API_URL=http://${IP}:8000" >> .env
grep -q '^API_CORS_ORIGINS=' .env || echo "API_CORS_ORIGINS=http://${IP}:3000,http://localhost:3000" >> .env

echo "==> 3/5 Rebuild API + Postgres"
sudo docker compose up -d --build postgres bot

echo "==> 4/5 Wait for API"
for i in $(seq 1 24); do
  if curl -sf http://127.0.0.1:8000/api/v1/status >/dev/null 2>&1; then
    echo "API is up"
    break
  fi
  sleep 5
done
curl -s http://127.0.0.1:8000/api/v1/status | head -c 200 || true
echo

echo "==> 5/5 Dashboard (Node)"
if ! command -v node >/dev/null 2>&1; then
  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
  sudo apt-get install -y nodejs
fi

cd dashboard/frontend
npm ci
NEXT_PUBLIC_API_URL="http://${IP}:8000" npm run build

# Run dashboard in background if not already running
if ! pgrep -f "next start" >/dev/null 2>&1; then
  nohup env NEXT_PUBLIC_API_URL="http://${IP}:8000" npm start > ~/dashboard.log 2>&1 &
  echo "Dashboard started in background (log: ~/dashboard.log)"
fi

sleep 5
curl -s -o /dev/null -w "dashboard_local:%{http_code}\n" http://127.0.0.1:3000/ || true

echo ""
echo "Done. Open: http://${IP}:3000"
echo "If browser still fails, open AWS Security Group inbound ports 3000 and 8000."
