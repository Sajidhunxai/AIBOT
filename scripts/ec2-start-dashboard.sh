#!/usr/bin/env bash
# Start Next.js standalone dashboard on EC2 (after npm run build).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FRONTEND="$ROOT/dashboard/frontend"

cd "$FRONTEND"
export NEXT_PUBLIC_API_URL="${NEXT_PUBLIC_API_URL:-http://127.0.0.1:8000}"

if [ ! -f .next/standalone/server.js ]; then
  echo "Building dashboard..."
  npm run build
fi

mkdir -p .next/standalone/.next
rm -rf .next/standalone/.next/static
cp -r .next/static .next/standalone/.next/static
rm -rf .next/standalone/public
cp -r public .next/standalone/public

fuser -k 3000/tcp 2>/dev/null || true
sleep 1

cd .next/standalone
nohup env PORT=3000 HOSTNAME=0.0.0.0 node server.js > "$ROOT/dashboard.log" 2>&1 &
echo "Dashboard: http://$(curl -sf -H "X-aws-ec2-metadata-token: $(curl -sf -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')" http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo 127.0.0.1):3000"
