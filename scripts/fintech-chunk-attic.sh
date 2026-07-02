#!/usr/bin/env bash
#
# Страж чанков fintech-фронта (прод, root-cron каждые 2 минуты).
#
# Зачем: каждый `nuxt generate` пересоздаёт .output/public/_nuxt со свежими
# хэшами и удаляет старые файлы. Клиент с открытой вкладкой прежнего билда
# запрашивает старый чанк -> 404 -> "Couldn't resolve component" / битый вход
# (волна после каждого деплоя фронта, см. GlitchTip fintech-front).
# В repo фронта есть deploy/deploy.sh с той же attic-логикой, но деплои
# регулярно идут мимо него (npm run generate:update напрямую). Этот cron
# сходится с любым способом деплоя за <=2 минуты.
#
# Инварианты:
#  - в раздачу (_nuxt) только ДОБАВЛЯЕМ недостающее (cp -an), никогда не удаляем:
#    очистку раздачи делает сам nuxt generate при следующем деплое;
#  - retention только в attic (файлы старше RETAIN_DAYS суток);
#  - attic совместим с deploy/deploy.sh фронта (тот же путь .chunk-attic).
#
set -euo pipefail

PUB="${PUB:-/home/fintech/web/fintech.rusaifin.ru/public_html/.output/public/_nuxt}"
ATTIC="${ATTIC:-/home/fintech/web/fintech.rusaifin.ru/public_html/.chunk-attic}"
RETAIN_DAYS="${RETAIN_DAYS:-7}"
LOCK="${LOCK:-/run/fintech-chunk-attic.lock}"

exec 9>"$LOCK"
flock -n 9 || exit 0

# Деплой в процессе / раздача отсутствует — не вмешиваемся, догоним следующим прогоном.
[ -d "$PUB" ] || exit 0

mkdir -p "$ATTIC"

# 1. Новые чанки текущего билда -> attic (аддитивно, mtime сохраняется).
cp -an "$PUB/." "$ATTIC/"

# 2. Вернуть в раздачу чанки прошлых билдов, которых нет в текущем.
cp -an "$ATTIC/." "$PUB/"

# 3. Retention: только attic. Из раздачи не удаляем ничего.
find "$ATTIC" -type f -mtime +"$RETAIN_DAYS" -delete
find "$ATTIC" -type d -empty -delete 2>/dev/null || true
