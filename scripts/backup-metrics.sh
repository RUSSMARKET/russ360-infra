#!/usr/bin/env bash
#
# Экспорт состояния бэкапов в Prometheus (прод, root-cron каждые 15 минут).
#
# Зачем: бэкап fintech падал каждую ночь с февраля по июль 2026 с
# "not enough disk space" и об этом никто не знал — Hestia пишет ошибку
# только в свой лог, алерта не было. Пять месяцев боевой сервис с 47G
# данных существовал в единственной февральской копии.
#
# Метрики отдаём через textfile collector node_exporter'а; правила тревог
# живут в infra/observability/grafana/provisioning/alerting/rules.yaml.
#
# Источник правды — mtime свежего .tar в /backup: Hestia хранит там
# последнюю копию каждого пользователя (BACKUPS=1), и файл появляется
# только при успешном завершении.
#
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backup}"
TEXTFILE_DIR="${TEXTFILE_DIR:-/var/lib/node_exporter/textfile}"
HESTIA_LOG="${HESTIA_LOG:-/usr/local/hestia/log/backup.log}"
OUT="$TEXTFILE_DIR/backups.prom"

mkdir -p "$TEXTFILE_DIR"

now=$(date +%s)
tmp=$(mktemp "$OUT.XXXXXX")
# Незавершённую запись node_exporter читать не должен: пишем во временный
# файл и подменяем атомарным mv.
trap 'rm -f "$tmp"' EXIT

{
	echo "# HELP backup_last_success_timestamp_seconds Unixtime последнего успешно созданного архива."
	echo "# TYPE backup_last_success_timestamp_seconds gauge"
	echo "# HELP backup_size_bytes Размер последнего архива."
	echo "# TYPE backup_size_bytes gauge"
} >> "$tmp"

# Hestia-бэкапы пользователей: имя файла <user>.<дата>_<время>.tar
for f in "$BACKUP_DIR"/*.tar; do
	[ -e "$f" ] || continue
	base=$(basename "$f")
	name=${base%%.*}

	case "$name" in
		shift_*) scope="shift" ;;
		*)       scope="hestia" ;;
	esac

	mtime=$(stat -c %Y "$f")
	size=$(stat -c %s "$f")
	echo "backup_last_success_timestamp_seconds{scope=\"$scope\",user=\"$name\"} $mtime" >> "$tmp"
	echo "backup_size_bytes{scope=\"$scope\",user=\"$name\"} $size" >> "$tmp"
done

# Пользователи, у которых бэкап включён, но свежего архива в /backup нет
# вообще — иначе упавший пользователь просто исчезает из метрик и алерт
# по возрасту никогда не сработает.
{
	echo "# HELP backup_enabled Бэкап включён в настройках Hestia (BACKUPS != 0)."
	echo "# TYPE backup_enabled gauge"
} >> "$tmp"

for udir in /usr/local/hestia/data/users/*/; do
	user=$(basename "$udir")
	[ -f "$udir/user.conf" ] || continue
	backups=$(grep -oP "BACKUPS='\K[^']*" "$udir/user.conf" 2>/dev/null || echo 0)
	[ "${backups:-0}" != "0" ] || continue
	# Заблокированных Hestia не бэкапит — иначе вечный алерт "архива нет".
	suspended=$(grep -oP "SUSPENDED='\K[^']*" "$udir/user.conf" 2>/dev/null || echo no)
	[ "${suspended:-no}" != "yes" ] || continue
	echo "backup_enabled{user=\"$user\"} 1" >> "$tmp"
done

# Ошибки последнего прогона. Строки "Error:" в логе Hestia не датированы,
# поэтому привязываем их к последней встреченной отметке времени и считаем
# только те, что моложе суток — иначе однажды упавший бэкап держит тревогу
# до конца дня, даже если следующий прогон прошёл успешно.
{
	echo "# HELP backup_hestia_errors_recent Ошибки бэкапа Hestia за последние 26 часов."
	echo "# TYPE backup_hestia_errors_recent gauge"
} >> "$tmp"

errors=0
if [ -r "$HESTIA_LOG" ]; then
	errors=$(python3 - "$HESTIA_LOG" <<-'PY'
		import re, sys, time
		from datetime import datetime

		cutoff = time.time() - 26 * 3600
		stamp = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
		last_ts, count = None, 0

		with open(sys.argv[1], errors="replace") as fh:
		    for line in fh:
		        m = stamp.match(line)
		        if m:
		            last_ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").timestamp()
		        elif line.startswith("Error:") and last_ts and last_ts >= cutoff:
		            count += 1

		print(count)
	PY
	) || errors=0
fi
echo "backup_hestia_errors_recent $errors" >> "$tmp"

echo "# HELP backup_metrics_generated_timestamp_seconds Когда сборщик метрик отработал в последний раз." >> "$tmp"
echo "# TYPE backup_metrics_generated_timestamp_seconds gauge" >> "$tmp"
echo "backup_metrics_generated_timestamp_seconds $now" >> "$tmp"

chmod 644 "$tmp"
mv "$tmp" "$OUT"
trap - EXIT
