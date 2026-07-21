#!/bin/bash
# Недельный срез фото смен. Каталоги shift/ исключены из бэкапов Hestia
# (39G у fintech, 10G у форка — требование Hestia "свободно >= 2x размера юзера"
# месяцами роняло бэкап целиком). Здесь тарим только свежие файлы, архив кладём
# в /backup, откуда его забирает backup.sh с бэкап-сервера.

set -uo pipefail

DAYS=7
OUT=/backup
KEEP_LOCAL_DAYS=1
STAMP=$(date +%F_%H-%M-%S)
LOG=/var/log/backup-shift.log

declare -A SRC=(
	[shift_fintech]=/home/fintech/web/server.rusaifin.ru/public_html/storage/app/private/shift
	[shift_yandex]=/home/fintech_yandex/web/yandex.server.rusaifin.ru/public_html/storage/app/private/shift
)

log() { echo "$(date '+%F %T') $*" >> "$LOG"; }

log "=== старт (окно ${DAYS} дн.) ==="

rc_total=0
for name in "${!SRC[@]}"; do
	dir="${SRC[$name]}"

	if [ ! -d "$dir" ]; then
		log "$name: ОШИБКА — нет каталога $dir"
		rc_total=1
		continue
	fi

	list=$(mktemp)
	find "$dir" -type f -mtime -"$DAYS" -printf '%P\n' > "$list" 2>/dev/null
	cnt=$(wc -l < "$list")

	if [ "$cnt" -eq 0 ]; then
		log "$name: свежих файлов нет, архив не создаём"
		rm -f "$list"
		continue
	fi

	need_mb=$(find "$dir" -type f -mtime -"$DAYS" -printf '%s\n' 2>/dev/null | awk '{s+=$1} END {printf "%.0f", s/1024/1024}')
	free_mb=$(df -Pm "$OUT" | awk 'NR==2 {print $4}')
	if [ "$free_mb" -lt $((need_mb * 2)) ]; then
		log "$name: ОШИБКА — мало места (нужно ~$((need_mb * 2)) MB, свободно ${free_mb} MB)"
		rm -f "$list"
		rc_total=1
		continue
	fi

	target="$OUT/$name.$STAMP.tar"
	if nice -n 19 tar --ignore-failed-read -cf "$target" -C "$dir" -T "$list" 2>>"$LOG"; then
		size_mb=$(du -m "$target" | cut -f1)
		log "$name: OK — ${cnt} файлов, ${size_mb} MB → $(basename "$target")"
	else
		log "$name: ОШИБКА — tar завершился с кодом $?"
		rm -f "$target"
		rc_total=1
	fi
	rm -f "$list"

	# Старые локальные копии не нужны: их уже забрал бэкап-сервер
	find "$OUT" -maxdepth 1 -name "$name.*.tar" -mtime +"$KEEP_LOCAL_DAYS" -print -delete >> "$LOG" 2>&1
done

log "=== финиш (rc=$rc_total) ==="
exit $rc_total
