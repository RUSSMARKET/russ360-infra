#!/usr/bin/env bash
#
# Refresh dev-БД на 82.146.57.149 из prod-снимка с анонимизацией.
#
# Запускается НА САМОМ СЕРВЕРЕ от root:
#   bash /root/refresh-dev-from-prod.server.sh [--dry-run]
#
# Что делает (по этапам):
#   1) Sanity: жёсткая проверка hardcoded имён БД (защита от опечаток в коде).
#   2) Дамп dev rusaiauth.oauth_clients (его сохраняем — содержит dev redirect_uri).
#   3) mysqldump fintech_base + pg_dump rusaiauth_prod/rusaicore_prod/rusaisklad_prod_db.
#   4) DROP + CREATE dev-БД + restore из дампов.
#   5) Откатить dev.oauth_clients из шага 2 поверх данных.
#   6) artisan db:anonymize в каждом dev-сервисе (с прокидыванием exclusions.json).
#
# Прод трогается ТОЛЬКО на чтение: mysqldump --single-transaction + pg_dump.
# Никаких DROP/INSERT/UPDATE на prod-БД быть не должно.

set -Eeuo pipefail

# ============================================================
# КОНФИГ (hardcoded — не env, чтобы не было опечаток на месте)
# ============================================================

# host MySQL
PROD_MYSQL_DB="fintech_base"
DEV_MYSQL_DB="fintech_devbase"

# rusaiauth
PROD_AUTH_CONT="rusaiauth_back_prod-db"
PROD_AUTH_DB="rusaiauth_prod"
PROD_AUTH_USER="rusaiauth_prod"
DEV_AUTH_CONT="rusaiauth_back_dev-db"
DEV_AUTH_DB="rusaiauth_dev"
DEV_AUTH_USER="rusaiauth_dev"

# rusaicore
PROD_CORE_CONT="rusaicore_back_prod-pgsql-1"
PROD_CORE_DB="rusaicore_prod"
PROD_CORE_USER="rusaicore_prod"
DEV_CORE_CONT="rusaicore_back_dev-pgsql-1"
DEV_CORE_DB="rusaicore_dev"
DEV_CORE_USER="rusaicore_dev"

# rusaisklad
PROD_SKL_CONT="rusaisklad_back_prod-pgsql-1"
PROD_SKL_DB="rusaisklad_prod_db"
PROD_SKL_USER="rusaisklad_prod_db"
DEV_SKL_CONT="rusaisklad_back_dev-pgsql-1"
DEV_SKL_DB="rusaisklad_dev_db"
DEV_SKL_USER="rusaisklad_dev_db"

# App-контейнеры/пути для artisan
RUSAIFIN_DIR="/home/fintech/web/dev.server.rusaifin.ru/public_html"
APP_AUTH="rusaiauth_back_dev-app"
APP_CORE="rusaicore_back_dev-app-1"
APP_SKL="rusaisklad_back_dev-app-1"

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then DRY_RUN=1; fi

DUMP_DIR="/tmp/refresh-dev-$(date -u +%Y%m%d-%H%M%S)"
mkdir -p "$DUMP_DIR"
chmod 700 "$DUMP_DIR"

log()  { printf '\033[1;34m[%(%H:%M:%S)T]\033[0m %s\n' -1 "$*"; }
warn() { printf '\033[1;33m[WARN]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[FATAL]\033[0m %s\n' "$*" >&2; exit 1; }

run() {
    if [[ $DRY_RUN -eq 1 ]]; then
        printf '\033[1;36m[dry-run]\033[0m %s\n' "$*"
    else
        eval "$*"
    fi
}

# ============================================================
# Sanity checks
# ============================================================

log "Sanity checks…"

# Имена БД должны быть РАЗНЫМИ
[[ "$PROD_MYSQL_DB" != "$DEV_MYSQL_DB" ]]  || die "PROD_MYSQL_DB == DEV_MYSQL_DB"
[[ "$PROD_AUTH_DB" != "$DEV_AUTH_DB" ]]    || die "PROD_AUTH_DB == DEV_AUTH_DB"
[[ "$PROD_CORE_DB" != "$DEV_CORE_DB" ]]    || die "PROD_CORE_DB == DEV_CORE_DB"
[[ "$PROD_SKL_DB" != "$DEV_SKL_DB" ]]      || die "PROD_SKL_DB == DEV_SKL_DB"

# Имена БД должны соответствовать ожидаемому формату prod/dev
[[ "$DEV_MYSQL_DB" =~ devbase$ ]]          || die "DEV_MYSQL_DB '$DEV_MYSQL_DB' не похоже на dev"
[[ "$DEV_AUTH_DB" =~ _dev$ ]]              || die "DEV_AUTH_DB '$DEV_AUTH_DB' не похоже на dev"
[[ "$DEV_CORE_DB" =~ _dev$ ]]              || die "DEV_CORE_DB '$DEV_CORE_DB' не похоже на dev"
[[ "$DEV_SKL_DB" =~ _dev_db$ ]]            || die "DEV_SKL_DB '$DEV_SKL_DB' не похоже на dev"

# Контейнеры должны быть живы
for c in "$PROD_AUTH_CONT" "$DEV_AUTH_CONT" "$PROD_CORE_CONT" "$DEV_CORE_CONT" \
         "$PROD_SKL_CONT" "$DEV_SKL_CONT" "$APP_AUTH" "$APP_CORE" "$APP_SKL"; do
    docker inspect -f '{{.State.Running}}' "$c" 2>/dev/null | grep -q true || die "Контейнер $c не запущен"
done

# rusaifin dev path
[[ -d "$RUSAIFIN_DIR" ]] || die "$RUSAIFIN_DIR не найдено"
[[ -f "$RUSAIFIN_DIR/artisan" ]] || die "$RUSAIFIN_DIR/artisan не найдено"

# Host MySQL access (root socket)
mysql -BNe "SELECT 1" >/dev/null 2>&1 || die "Нет доступа к host MySQL (mysql -BNe 'SELECT 1')"

log "Sanity checks ok. Dump dir: $DUMP_DIR. dry-run=$DRY_RUN"
echo ""

# ============================================================
# Этап 1: бэкап dev-oauth_clients (восстановим поверх prod-данных)
# ============================================================

log "[1] Backup dev rusaiauth.oauth_clients (dev redirect_uri-ев)"
run "docker exec '$DEV_AUTH_CONT' pg_dump -U '$DEV_AUTH_USER' -d '$DEV_AUTH_DB' -t oauth_clients --data-only --column-inserts > '$DUMP_DIR/dev_oauth_clients.sql'"
if [[ $DRY_RUN -eq 0 ]]; then
    rows=$(grep -c '^INSERT INTO' "$DUMP_DIR/dev_oauth_clients.sql" || true)
    log "  → сохранил $rows строк в $DUMP_DIR/dev_oauth_clients.sql"
fi

echo ""

# ============================================================
# Этап 2: дампы с прода (read-only)
# ============================================================

log "[2a] mysqldump $PROD_MYSQL_DB"
run "mysqldump --single-transaction --quick --routines --triggers '$PROD_MYSQL_DB' | gzip > '$DUMP_DIR/rusaifin.sql.gz'"

log "[2b] pg_dump $PROD_AUTH_DB"
run "docker exec '$PROD_AUTH_CONT' pg_dump -U '$PROD_AUTH_USER' -d '$PROD_AUTH_DB' -Fc --no-owner --no-privileges > '$DUMP_DIR/rusaiauth.dump'"

log "[2c] pg_dump $PROD_CORE_DB"
run "docker exec '$PROD_CORE_CONT' pg_dump -U '$PROD_CORE_USER' -d '$PROD_CORE_DB' -Fc --no-owner --no-privileges > '$DUMP_DIR/rusaicore.dump'"

log "[2d] pg_dump $PROD_SKL_DB"
run "docker exec '$PROD_SKL_CONT' pg_dump -U '$PROD_SKL_USER' -d '$PROD_SKL_DB' -Fc --no-owner --no-privileges > '$DUMP_DIR/rusaisklad.dump'"

if [[ $DRY_RUN -eq 0 ]]; then
    log "  Размер дампов:"
    ls -lh "$DUMP_DIR"/*.{gz,dump} 2>/dev/null | awk '{print "    " $9, $5}'
fi

echo ""

# ============================================================
# Этап 3: restore в dev-БД (DROP + CREATE + restore)
# ============================================================

log "[3a] restore $PROD_MYSQL_DB → $DEV_MYSQL_DB"
run "mysql -e \"DROP DATABASE IF EXISTS \\\`$DEV_MYSQL_DB\\\`; CREATE DATABASE \\\`$DEV_MYSQL_DB\\\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\""
run "gunzip -c '$DUMP_DIR/rusaifin.sql.gz' | mysql '$DEV_MYSQL_DB'"

restore_pg() {
    local cont="$1" db="$2" user="$3" dump="$4"
    # postgres-superuser в docker-image = $user (тот же что и POSTGRES_USER)
    run "docker exec '$cont' psql -U '$user' -d postgres -c \"DROP DATABASE IF EXISTS \\\"$db\\\";\""
    run "docker exec '$cont' psql -U '$user' -d postgres -c \"CREATE DATABASE \\\"$db\\\";\""
    run "docker exec -i '$cont' pg_restore -U '$user' -d '$db' --no-owner --no-privileges < '$dump'"
}

log "[3b] restore $PROD_AUTH_DB → $DEV_AUTH_DB"
restore_pg "$DEV_AUTH_CONT" "$DEV_AUTH_DB" "$DEV_AUTH_USER" "$DUMP_DIR/rusaiauth.dump"

log "[3c] restore $PROD_CORE_DB → $DEV_CORE_DB"
restore_pg "$DEV_CORE_CONT" "$DEV_CORE_DB" "$DEV_CORE_USER" "$DUMP_DIR/rusaicore.dump"

log "[3d] restore $PROD_SKL_DB → $DEV_SKL_DB"
restore_pg "$DEV_SKL_CONT" "$DEV_SKL_DB" "$DEV_SKL_USER" "$DUMP_DIR/rusaisklad.dump"

echo ""

# ============================================================
# Этап 4: восстановить dev oauth_clients поверх prod-данных
# ============================================================

log "[4] откатить dev oauth_clients (с dev redirect_uri-ями)"
run "docker exec '$DEV_AUTH_CONT' psql -U '$DEV_AUTH_USER' -d '$DEV_AUTH_DB' -c 'TRUNCATE TABLE oauth_clients CASCADE;'"
run "cat '$DUMP_DIR/dev_oauth_clients.sql' | docker exec -i '$DEV_AUTH_CONT' psql -U '$DEV_AUTH_USER' -d '$DEV_AUTH_DB'"

echo ""

# ============================================================
# Этап 5: artisan db:anonymize
# ============================================================

EXCL_HOST="$RUSAIFIN_DIR/storage/app/anonymize-exclusions.json"
EXCL_INCONT="/tmp/anonymize-exclusions.json"

log "[5a] rusaifin db:anonymize (генерирует exclusions.json)"
run "sudo -u fintech php8.3 '$RUSAIFIN_DIR/artisan' db:anonymize --force --exclusions-out='$EXCL_HOST'"

if [[ $DRY_RUN -eq 0 ]]; then
    [[ -f "$EXCL_HOST" ]] || die "exclusions.json не создан"
    log "  exclusions: $(jq '.identity_user_ids | length' "$EXCL_HOST" 2>/dev/null || echo '?') UUID"
fi

# Раскидать exclusions.json в три контейнера и прогнать anonymize
for app_cont in "$APP_AUTH" "$APP_CORE" "$APP_SKL"; do
    run "docker cp '$EXCL_HOST' '$app_cont:$EXCL_INCONT'"
done

log "[5b] rusaiauth db:anonymize"
run "docker exec '$APP_AUTH' php artisan db:anonymize --force --exclusions='$EXCL_INCONT'"

log "[5c] rusaicore db:anonymize"
run "docker exec '$APP_CORE' php artisan db:anonymize --force --exclusions='$EXCL_INCONT'"

log "[5d] rusaisklad db:anonymize"
run "docker exec '$APP_SKL' php artisan db:anonymize --force --exclusions='$EXCL_INCONT'"

echo ""
log "Готово. Дампы лежат в $DUMP_DIR (можно удалить после проверки)."
