#!/usr/bin/env bash
# Pull production archives to the storage-only host with explicit SHA-256
# verification before atomic publication and retention.

set -Eeuo pipefail
umask 077

PRODUCTION_HOST="${PRODUCTION_HOST:-82.146.57.149}"
PRODUCTION_USER="${PRODUCTION_USER:-root}"
SSH_KEY="${SSH_KEY:-/root/.ssh/id_backup2prod}"
REMOTE_DIR="${REMOTE_DIR:-/backup}"
FILE_PATTERN="${FILE_PATTERN:-*.tar}"
STAGING_DIR="${STAGING_DIR:-/home/backup-staging}"
BACKUP_BASE_DIR="${BACKUP_BASE_DIR:-/home/backup}"
METRIC_PATH="${METRIC_PATH:-/var/lib/node_exporter/textfile/backup_puller.prom}"
LOCK_FILE="${LOCK_FILE:-/run/lock/russ360-backup-pull.lock}"

for command_name in awk basename chmod cut date df find flock grep head install mktemp mv rm scp sha256sum sort ssh stat tar; do
	command -v "$command_name" >/dev/null 2>&1 || {
		echo "Required command is missing: $command_name" >&2
		exit 69
	}
done

exec 9>"$LOCK_FILE"
flock -n 9 || {
	echo "Another backup pull is already running." >&2
	exit 75
}

test -f "$SSH_KEY" || {
	echo "Backup SSH key is unavailable." >&2
	exit 66
}

case "$FILE_PATTERN" in
	*[!A-Za-z0-9._*?-]*|'')
		echo "Unsafe archive file pattern." >&2
		exit 64
		;;
esac

install -d -m 0700 "$STAGING_DIR" "$BACKUP_BASE_DIR"
ssh_options=(-i "$SSH_KEY" -o BatchMode=yes -o ConnectTimeout=30)

mapfile -t files < <(
	ssh -n "${ssh_options[@]}" "$PRODUCTION_USER@$PRODUCTION_HOST" \
		"find '$REMOTE_DIR' -maxdepth 1 -type f -name '$FILE_PATTERN' -printf '%p\\n' | sort"
)

if ((${#files[@]} == 0)); then
	echo "No production archives were found." >&2
	exit 66
fi

total=${#files[@]}
success=0
failed=0
checksum_failures=0

for remote_file in "${files[@]}"; do
	filename=$(basename "$remote_file")
	case "$remote_file:$filename" in
		"$REMOTE_DIR"/*:*[!A-Za-z0-9._-]*|"$REMOTE_DIR"/:*)
			echo "Rejected unsafe archive path: $remote_file" >&2
			failed=$((failed + 1))
			continue
			;;
		"$REMOTE_DIR"/*:*) ;;
		*)
			echo "Rejected archive outside the configured directory: $remote_file" >&2
			failed=$((failed + 1))
			continue
			;;
	esac

	name_part=${filename%%.*}
	target_dir="$BACKUP_BASE_DIR/$name_part"
	archive_tmp=$(mktemp "$STAGING_DIR/.${name_part}.XXXXXX")

	if ! source_sha=$(ssh -n "${ssh_options[@]}" "$PRODUCTION_USER@$PRODUCTION_HOST" \
		"sha256sum -- '$remote_file'" | cut -d ' ' -f1); then
		echo "Unable to hash source archive: $filename" >&2
		rm -f -- "$archive_tmp"
		failed=$((failed + 1))
		continue
	fi

	if ! scp -q "${ssh_options[@]}" "$PRODUCTION_USER@$PRODUCTION_HOST:$remote_file" "$archive_tmp"; then
		echo "Unable to copy archive: $filename" >&2
		rm -f -- "$archive_tmp"
		failed=$((failed + 1))
		continue
	fi

	local_sha=$(sha256sum "$archive_tmp" | cut -d ' ' -f1)
	if [[ ! "$source_sha" =~ ^[0-9a-f]{64}$ ]] || [[ "$source_sha" != "$local_sha" ]]; then
		echo "SHA-256 mismatch: $filename" >&2
		rm -f -- "$archive_tmp"
		failed=$((failed + 1))
		checksum_failures=$((checksum_failures + 1))
		continue
	fi

	if ! tar -tf "$archive_tmp" >/dev/null; then
		echo "Unreadable tar archive: $filename" >&2
		rm -f -- "$archive_tmp"
		failed=$((failed + 1))
		continue
	fi

	install -d -m 0700 "$target_dir"
	install -m 0600 "$archive_tmp" "$target_dir/$filename.new"
	mv -f -- "$target_dir/$filename.new" "$target_dir/$filename"
	rm -f -- "$archive_tmp"
	echo "Verified: $filename ($local_sha)"
	success=$((success + 1))
done

get_timestamp() {
	local filename=$1 date_string
	date_string=$(grep -Eo '[0-9]{4}-[0-9]{2}-[0-9]{2}' <<<"$filename" | head -1)
	date -d "$date_string" +%s 2>/dev/null
}

cleanup_backups() {
	local backup_dir=$1 project_name current_ts file file_ts days_diff recent
	local ret_daily ret_weekly ret_monthly ret_semi
	project_name=$(basename "$backup_dir")
	case "$project_name" in
		fintech)        ret_daily=2; ret_weekly=33; ret_monthly=75; ret_semi=180 ;;
		fintech_yandex) ret_daily=1; ret_weekly=0;  ret_monthly=75; ret_semi=0   ;;
		shift_*)        ret_daily=6; ret_weekly=0;  ret_monthly=0;  ret_semi=0   ;;
		*)              ret_daily=6; ret_weekly=33; ret_monthly=75; ret_semi=180 ;;
	esac

	current_ts=$(date +%s)
	recent=0
	while IFS= read -r file; do
		file_ts=$(get_timestamp "$file" || true)
		if [[ "$file_ts" =~ ^[0-9]+$ ]] && (( current_ts - file_ts < 172800 )); then
			recent=1
			break
		fi
	done < <(find "$backup_dir" -maxdepth 1 -type f -name '*.tar' -printf '%f\n')
	if (( recent == 0 )); then
		echo "Retention skipped for $project_name: no source-dated archive newer than two days."
		return 0
	fi

	local daily_list weekly_list monthly_list semi_list keep_list
	daily_list=$(mktemp); weekly_list=$(mktemp); monthly_list=$(mktemp)
	semi_list=$(mktemp); keep_list=$(mktemp)

	while IFS= read -r file; do
		file_ts=$(get_timestamp "$file" || true)
		[[ "$file_ts" =~ ^[0-9]+$ ]] || continue
		days_diff=$(( (current_ts - file_ts) / 86400 ))
		if (( days_diff <= ret_daily )); then
			printf '%s %s\n' "$file" "$file_ts" >>"$daily_list"
		elif (( days_diff <= ret_weekly )); then
			printf '%s %s %s\n' "$file" "$file_ts" "$(date -d "@$file_ts - $(( $(date -d "@$file_ts" +%u) - 1 )) days" +%Y-%m-%d)" >>"$weekly_list"
		elif (( days_diff <= ret_monthly )); then
			printf '%s %s %s\n' "$file" "$file_ts" "$(date -d "@$file_ts" +%Y-%m-01)" >>"$monthly_list"
		elif (( days_diff <= ret_semi )); then
			printf '%s %s\n' "$file" "$file_ts" >>"$semi_list"
		fi
	done < <(find "$backup_dir" -maxdepth 1 -type f -name '*.tar' -printf '%f\n')

	awk '{print $1}' "$daily_list" >>"$keep_list"
	awk '{print $3, $1, $2}' "$weekly_list" | sort -k1,1 -k3,3nr | awk '!seen[$1]++ {print $2}' >>"$keep_list"
	awk '{print $3, $1, $2}' "$monthly_list" | sort -k1,1 -k3,3nr | awk '!seen[$1]++ {print $2}' >>"$keep_list"
	sort -k2,2nr "$semi_list" | awk 'NR==1 {print $1}' >>"$keep_list"

	while IFS= read -r file; do
		if ! grep -qxF "$file" "$keep_list"; then
			echo "Retention removes: $project_name/$file"
			rm -f -- "$backup_dir/$file"
		fi
	done < <(find "$backup_dir" -maxdepth 1 -type f -name '*.tar' -printf '%f\n')

	rm -f -- "$daily_list" "$weekly_list" "$monthly_list" "$semi_list" "$keep_list"
}

if (( failed == 0 )); then
	while IFS= read -r backup_dir; do
		cleanup_backups "$backup_dir"
	done < <(find "$BACKUP_BASE_DIR" -mindepth 1 -maxdepth 1 -type d | sort)
fi

completed_at=$(date +%s)
last_success=$completed_at
if (( failed > 0 )); then
	previous_line=$(ssh -n "${ssh_options[@]}" "$PRODUCTION_USER@$PRODUCTION_HOST" \
		"grep '^backup_puller_last_success_timestamp_seconds ' '$METRIC_PATH' 2>/dev/null || true")
	last_success=${previous_line##* }
	[[ "$last_success" =~ ^[0-9]+$ ]] || last_success=0
fi

metric_tmp=$(mktemp "$STAGING_DIR/.backup-puller-metric.XXXXXX")
trap 'rm -f -- "$metric_tmp"' EXIT
{
	echo '# HELP backup_puller_last_attempt_timestamp_seconds Unixtime последней попытки выкачки.'
	echo '# TYPE backup_puller_last_attempt_timestamp_seconds gauge'
	echo "backup_puller_last_attempt_timestamp_seconds $completed_at"
	echo '# HELP backup_puller_last_success_timestamp_seconds Unixtime последней полностью успешной выкачки.'
	echo '# TYPE backup_puller_last_success_timestamp_seconds gauge'
	echo "backup_puller_last_success_timestamp_seconds $last_success"
	echo '# HELP backup_puller_files_total Количество архивов в последней попытке.'
	echo '# TYPE backup_puller_files_total gauge'
	echo "backup_puller_files_total $total"
	echo '# HELP backup_puller_failed_files Количество не скопированных или не проверенных архивов.'
	echo '# TYPE backup_puller_failed_files gauge'
	echo "backup_puller_failed_files $failed"
	echo '# HELP backup_puller_checksum_failures SHA-256 mismatches в последней попытке.'
	echo '# TYPE backup_puller_checksum_failures gauge'
	echo "backup_puller_checksum_failures $checksum_failures"
	echo '# HELP backup_puller_disk_free_bytes Свободно на backup-сервере.'
	echo '# TYPE backup_puller_disk_free_bytes gauge'
	echo "backup_puller_disk_free_bytes $(df -PB1 /home | awk 'NR==2 {print $4}')"
	echo '# HELP backup_puller_disk_total_bytes Размер диска backup-сервера.'
	echo '# TYPE backup_puller_disk_total_bytes gauge'
	echo "backup_puller_disk_total_bytes $(df -PB1 /home | awk 'NR==2 {print $2}')"
} >"$metric_tmp"
chmod 0644 "$metric_tmp"

scp -q "${ssh_options[@]}" "$metric_tmp" "$PRODUCTION_USER@$PRODUCTION_HOST:$METRIC_PATH.tmp"
ssh -n "${ssh_options[@]}" "$PRODUCTION_USER@$PRODUCTION_HOST" \
	"chmod 0644 '$METRIC_PATH.tmp' && mv -f '$METRIC_PATH.tmp' '$METRIC_PATH'"

echo "Pull complete: total=$total success=$success failed=$failed checksum_failures=$checksum_failures"
(( failed == 0 ))
