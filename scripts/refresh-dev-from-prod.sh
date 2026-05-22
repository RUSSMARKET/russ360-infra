#!/usr/bin/env bash
#
# Заливка dev из prod с анонимизацией.
#
# Прод трогаем ТОЛЬКО на чтение: mysqldump (SELECT/LOCK TABLES) и pg_dump.
# Никаких ALTER/INSERT/UPDATE на прод-БД из этого скрипта быть не должно.
#
# Использование:
#   scripts/refresh-dev-from-prod.sh             # полный цикл: dump → restore → anonymize
#   scripts/refresh-dev-from-prod.sh --dump      # только дампы с прода в DUMP_DIR
#   scripts/refresh-dev-from-prod.sh --restore   # restore локально из DUMP_DIR + anonymize
#   scripts/refresh-dev-from-prod.sh --anonymize # только прогон artisan db:anonymize
#
# Перед первым запуском:
#   cp scripts/refresh-dev-from-prod.env.example scripts/refresh-dev-from-prod.env
#   заполнить PROD_* блок.

set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${REPO_ROOT}/scripts/refresh-dev-from-prod.env"
DUMP_DIR="${DUMP_DIR:-${REPO_ROOT}/scripts/dumps}"
EXCLUSIONS_FILE="${DUMP_DIR}/anonymize-exclusions.json"

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "ERROR: ${ENV_FILE} не найден."
    echo "Скопируй: cp scripts/refresh-dev-from-prod.env.example scripts/refresh-dev-from-prod.env"
    echo "И заполни PROD_* секцию."
    exit 1
fi

# shellcheck disable=SC1090
source "${ENV_FILE}"

mkdir -p "${DUMP_DIR}"

MODE="all"
case "${1:-}" in
    --dump) MODE="dump" ;;
    --restore) MODE="restore" ;;
    --anonymize) MODE="anonymize" ;;
    --help|-h) sed -n '3,20p' "$0"; exit 0 ;;
    "") MODE="all" ;;
    *) echo "Неизвестный флаг: $1"; exit 1 ;;
esac

log() { printf '\033[1;34m[%(%H:%M:%S)T]\033[0m %s\n' -1 "$*"; }
die() { printf '\033[1;31m[ERROR]\033[0m %s\n' "$*" >&2; exit 1; }

ssh_prod() {
    if [[ -n "${PROD_SSH_PASSWORD:-}" ]]; then
        sshpass -p "${PROD_SSH_PASSWORD}" ssh -o StrictHostKeyChecking=no \
            "${PROD_SSH_USER}@${PROD_SSH_HOST}" "$@"
    else
        ssh "${PROD_SSH_USER}@${PROD_SSH_HOST}" "$@"
    fi
}

scp_from_prod() {
    local remote="$1" local_dst="$2"
    if [[ -n "${PROD_SSH_PASSWORD:-}" ]]; then
        sshpass -p "${PROD_SSH_PASSWORD}" scp -o StrictHostKeyChecking=no \
            "${PROD_SSH_USER}@${PROD_SSH_HOST}:${remote}" "${local_dst}"
    else
        scp "${PROD_SSH_USER}@${PROD_SSH_HOST}:${remote}" "${local_dst}"
    fi
}

# ---------- DUMP ----------

dump_mysql() {
    local db="$1" out="$2"
    log "mysqldump prod ${db} → ${out}"
    if [[ "${MYSQL_VIA_SSH:-0}" == "1" ]]; then
        # mysqldump на прод-хосте, stdout стримим в локальный gzip
        ssh_prod "mysqldump --single-transaction --quick --routines --triggers \
            --set-gtid-purged=OFF \
            -h '${PROD_MYSQL_HOST}' -P '${PROD_MYSQL_PORT}' \
            -u '${PROD_MYSQL_USER}' -p'${PROD_MYSQL_PASSWORD}' '${db}'" \
            | gzip > "${out}"
    else
        mysqldump --single-transaction --quick --routines --triggers \
            --set-gtid-purged=OFF \
            -h "${PROD_MYSQL_HOST}" -P "${PROD_MYSQL_PORT}" \
            -u "${PROD_MYSQL_USER}" -p"${PROD_MYSQL_PASSWORD}" "${db}" \
            | gzip > "${out}"
    fi
    [[ -s "${out}" ]] || die "Пустой дамп ${out}"
}

dump_pg() {
    local container="$1" db="$2" user="$3" out="$4"
    log "pg_dump prod ${db} (контейнер ${container}) → ${out}"
    if [[ "${PG_VIA_DOCKER:-0}" == "1" ]]; then
        # pg_dump внутри контейнера на проде, custom-format поток → локальный файл
        ssh_prod "docker exec -i '${container}' pg_dump -U '${user}' -d '${db}' -Fc --no-owner --no-privileges" \
            > "${out}"
    else
        die "Прямой pg_dump к проду без docker не настроен; реализуй сам или используй SSH+docker."
    fi
    [[ -s "${out}" ]] || die "Пустой дамп ${out}"
}

do_dump() {
    [[ -n "${PROD_SSH_USER:-}" ]] || die "PROD_SSH_USER пустой — заполни env."
    [[ -n "${PROD_MYSQL_USER:-}" ]] || die "PROD_MYSQL_USER пустой — заполни env."

    log "=== Этап 1: дампы с прода (read-only) ==="
    dump_mysql "${PROD_RUSAIFIN_DB}"   "${DUMP_DIR}/rusaifin.sql.gz"

    if [[ "${PROD_RUSAISKLAD_ENGINE:-pg}" == "mysql" ]]; then
        dump_mysql "${PROD_RUSAISKLAD_DB}" "${DUMP_DIR}/rusaisklad.sql.gz"
    else
        dump_pg "${PROD_RUSAISKLAD_PG_CONTAINER}" "${PROD_RUSAISKLAD_DB}" "${PROD_RUSAISKLAD_DB_USER}" "${DUMP_DIR}/rusaisklad.dump"
    fi

    dump_pg "${PROD_RUSAIAUTH_PG_CONTAINER}" "${PROD_RUSAIAUTH_DB}" "${PROD_RUSAIAUTH_DB_USER}" "${DUMP_DIR}/rusaiauth.dump"
    dump_pg "${PROD_RUSAICORE_PG_CONTAINER}" "${PROD_RUSAICORE_DB}" "${PROD_RUSAICORE_DB_USER}" "${DUMP_DIR}/rusaicore.dump"
    log "Дампы готовы в ${DUMP_DIR}"
}

# ---------- RESTORE ----------

restore_mysql() {
    local db="$1" dump="$2"
    log "MySQL restore: ${db} ← ${dump}"
    local mysql_args=(-h "${LOCAL_MYSQL_HOST}" -P "${LOCAL_MYSQL_PORT}" -u "${LOCAL_MYSQL_USER}")
    [[ -n "${LOCAL_MYSQL_PASSWORD}" ]] && mysql_args+=(-p"${LOCAL_MYSQL_PASSWORD}")

    mysql "${mysql_args[@]}" -e "DROP DATABASE IF EXISTS \`${db}\`; CREATE DATABASE \`${db}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
    gunzip -c "${dump}" | mysql "${mysql_args[@]}" "${db}"
}

restore_pg() {
    local container="$1" db="$2" user="$3" dump="$4"
    log "PG restore: ${db} (контейнер ${container}) ← ${dump}"

    docker exec "${container}" psql -U "${user}" -d postgres -c "DROP DATABASE IF EXISTS \"${db}\";"
    docker exec "${container}" psql -U "${user}" -d postgres -c "CREATE DATABASE \"${db}\";"
    docker exec -i "${container}" pg_restore -U "${user}" -d "${db}" --no-owner --no-privileges < "${dump}"
}

do_restore() {
    log "=== Этап 2: restore в локальные БД ==="

    [[ -f "${DUMP_DIR}/rusaifin.sql.gz" ]] || die "Нет дампа rusaifin: ${DUMP_DIR}/rusaifin.sql.gz"
    [[ -f "${DUMP_DIR}/rusaiauth.dump" ]]  || die "Нет дампа rusaiauth: ${DUMP_DIR}/rusaiauth.dump"
    [[ -f "${DUMP_DIR}/rusaicore.dump" ]]  || die "Нет дампа rusaicore: ${DUMP_DIR}/rusaicore.dump"

    restore_mysql "${LOCAL_RUSAIFIN_DB}" "${DUMP_DIR}/rusaifin.sql.gz"

    if [[ "${PROD_RUSAISKLAD_ENGINE:-pg}" == "mysql" ]]; then
        [[ -f "${DUMP_DIR}/rusaisklad.sql.gz" ]] || die "Нет дампа rusaisklad: ${DUMP_DIR}/rusaisklad.sql.gz"
        # На проде MySQL → локально нужен MySQL. Если локально PG — это несовместимо.
        die "PROD_RUSAISKLAD_ENGINE=mysql, но локальный rusaisklad на PG. Реализуй сам или унифицируй движки."
    else
        [[ -f "${DUMP_DIR}/rusaisklad.dump" ]] || die "Нет дампа rusaisklad: ${DUMP_DIR}/rusaisklad.dump"
        restore_pg "${LOCAL_RUSAISKLAD_PG_CONTAINER}" "${LOCAL_RUSAISKLAD_DB}" "${LOCAL_RUSAISKLAD_DB_USER}" "${DUMP_DIR}/rusaisklad.dump"
    fi

    restore_pg "${LOCAL_RUSAIAUTH_PG_CONTAINER}" "${LOCAL_RUSAIAUTH_DB}" "${LOCAL_RUSAIAUTH_DB_USER}" "${DUMP_DIR}/rusaiauth.dump"
    restore_pg "${LOCAL_RUSAICORE_PG_CONTAINER}" "${LOCAL_RUSAICORE_DB}" "${LOCAL_RUSAICORE_DB_USER}" "${DUMP_DIR}/rusaicore.dump"
}

# ---------- ANONYMIZE ----------

artisan() {
    local container="$1"; shift
    docker exec "${container}" php /var/www/html/artisan "$@"
}

do_anonymize() {
    log "=== Этап 3: анонимизация ==="

    log "rusaifin db:anonymize (генерирует exclusions.json)"
    artisan "${LOCAL_RUSAIFIN_APP_CONTAINER}" db:anonymize --force \
        --exclusions-out=/var/www/html/storage/app/anonymize-exclusions.json

    # Достаём exclusions из контейнера
    docker cp "${LOCAL_RUSAIFIN_APP_CONTAINER}:/var/www/html/storage/app/anonymize-exclusions.json" \
        "${EXCLUSIONS_FILE}"
    log "exclusions: $(jq '.identity_user_ids | length' "${EXCLUSIONS_FILE}" 2>/dev/null || echo '?') UUID"

    # Раскидываем по остальным контейнерам
    for c in "${LOCAL_RUSAIAUTH_APP_CONTAINER}" "${LOCAL_RUSAICORE_APP_CONTAINER}" "${LOCAL_RUSAISKLAD_APP_CONTAINER}"; do
        docker cp "${EXCLUSIONS_FILE}" "${c}:/tmp/anonymize-exclusions.json"
    done

    log "rusaiauth db:anonymize"
    artisan "${LOCAL_RUSAIAUTH_APP_CONTAINER}" db:anonymize --force --exclusions=/tmp/anonymize-exclusions.json

    log "rusaicore db:anonymize"
    artisan "${LOCAL_RUSAICORE_APP_CONTAINER}" db:anonymize --force --exclusions=/tmp/anonymize-exclusions.json

    log "rusaisklad_back db:anonymize"
    artisan "${LOCAL_RUSAISKLAD_APP_CONTAINER}" db:anonymize --force --exclusions=/tmp/anonymize-exclusions.json

    log "Готово."
}

case "${MODE}" in
    dump)      do_dump ;;
    restore)   do_restore; do_anonymize ;;
    anonymize) do_anonymize ;;
    all)       do_dump; do_restore; do_anonymize ;;
esac
