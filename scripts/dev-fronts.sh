#!/usr/bin/env bash
# Запуск обоих фронтов в dev-режиме (HMR).
# fintech     -> http://localhost:3000
# rusaisklad  -> http://localhost:3001
#
# bibli (russ-ui) подхватывается автоматически из ../bibli — alias в nuxt.config.ts
# обоих фронтов проверяет существование локальной копии и предпочитает её node_modules.
#
# Логи пишутся в /tmp/russ360-fronts/{fintech,rusaisklad_front}.log
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOGS=/tmp/russ360-fronts
mkdir -p "$LOGS"

stop() {
  echo "Останавливаю фронты..."
  jobs -p | xargs -r kill 2>/dev/null || true
  exit 0
}
trap stop INT TERM

echo "=== Backend health check ==="
for svc in "rusaifin:8000" "rusaicore:8001" "rusaiauth:8002" "rusaisklad_back:8003"; do
  name="${svc%%:*}"; port="${svc##*:}"
  if curl -fsS -m 2 "http://localhost:$port" >/dev/null 2>&1 || nc -z localhost "$port" 2>/dev/null; then
    echo "  [up]   $name on :$port"
  else
    echo "  [down] $name on :$port — подними docker compose сервиса"
  fi
done

echo
echo "=== fintech (port 3000) ==="
(
  cd "$ROOT/fintech"
  exec node --max-old-space-size=8192 ./node_modules/nuxt/bin/nuxt.mjs dev --host 0.0.0.0 --port 3000 --dotenv .env.local 2>&1 | sed 's/^/[fintech] /'
) > "$LOGS/fintech.log" 2>&1 &
FIN_PID=$!
echo "  PID=$FIN_PID  log=$LOGS/fintech.log"

echo
echo "=== rusaisklad_front (port 3001) ==="
(
  cd "$ROOT/rusaisklad_front"
  exec node --max-old-space-size=8192 ./node_modules/nuxt/bin/nuxt.mjs dev --host 0.0.0.0 --port 3001 --dotenv .env.local 2>&1 | sed 's/^/[rusaisklad] /'
) > "$LOGS/rusaisklad_front.log" 2>&1 &
SKL_PID=$!
echo "  PID=$SKL_PID  log=$LOGS/rusaisklad_front.log"

echo
echo "Открой:"
echo "  fintech    -> http://localhost:3000"
echo "  rusaisklad -> http://localhost:3001"
echo
echo "Ctrl+C чтобы остановить оба."
wait
