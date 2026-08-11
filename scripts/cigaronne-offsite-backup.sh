#!/usr/bin/env bash
# Build the complete Cigaronne bundle on the storage-only host. Database and
# private-file streams cross SSH directly; production never stores a dump.

set -Eeuo pipefail
umask 077

PRODUCTION_HOST="${CIGARONNE_PRODUCTION_HOST:-82.146.57.149}"
PRODUCTION_USER="${CIGARONNE_PRODUCTION_USER:-root}"
SSH_KEY="${CIGARONNE_BACKUP_SSH_KEY:-/root/.ssh/id_backup2prod}"
REPO_DIR="${CIGARONNE_REPO_DIR:-/opt/cigaronne/repos/back}"
COMPOSE_FILE="${CIGARONNE_COMPOSE_FILE:-/opt/cigaronne/repos/back/compose.yaml}"
RUNTIME_ENV="${CIGARONNE_RUNTIME_ENV_FILE:-/opt/cigaronne/repos/back/.env}"
PROJECT_NAME="${CIGARONNE_COMPOSE_PROJECT_NAME:-cigaronne-back}"
BACKUP_DIR="${CIGARONNE_OFFSITE_BACKUP_DIR:-/home/backup/cigaronne}"
STAGING_DIR="${CIGARONNE_OFFSITE_STAGING_DIR:-/home/backup-staging}"
METRIC_PATH="${CIGARONNE_PRODUCTION_METRIC_PATH:-/var/lib/node_exporter/textfile/cigaronne_offsite_backup.prom}"
LOCK_FILE="${CIGARONNE_LOCK_FILE:-/run/lock/cigaronne-offsite-backup.lock}"

for command_name in chmod date flock install mktemp mv rm scp sha256sum ssh tar wc; do
	command -v "$command_name" >/dev/null 2>&1 || {
		echo "Required command is missing: $command_name" >&2
		exit 69
	}
done

exec 9>"$LOCK_FILE"
flock -n 9 || {
	echo "Another Cigaronne backup is already running." >&2
	exit 75
}

test -f "$SSH_KEY" || {
	echo "Backup SSH key is unavailable." >&2
	exit 66
}

install -d -m 0700 "$BACKUP_DIR" "$STAGING_DIR"
work_dir=$(mktemp -d "$STAGING_DIR/.cigaronne-backup.XXXXXX")
payload_dir="$work_dir/payload"
install -d -m 0700 "$payload_dir"
ssh_options=(-i "$SSH_KEY" -o BatchMode=yes -o ConnectTimeout=30)
remote_target="$PRODUCTION_USER@$PRODUCTION_HOST"
paused=0

remote() {
	ssh -n "${ssh_options[@]}" "$remote_target" "$@"
}

compose_prefix="cd '$REPO_DIR' && docker compose --project-name '$PROJECT_NAME' --file '$COMPOSE_FILE' --env-file '$RUNTIME_ENV'"

resume_application() {
	if (( paused == 1 )); then
		remote "$compose_prefix exec -T web php artisan up >/dev/null 2>&1 || true; $compose_prefix start worker scheduler >/dev/null 2>&1 || true"
		paused=0
	fi
}

cleanup() {
	resume_application || true
	rm -rf -- "$work_dir"
}
trap cleanup EXIT HUP INT TERM

for service_name in pgsql web worker scheduler; do
	remote "$compose_prefix ps --status running '$service_name' | grep -q '$service_name'"
done
remote "$compose_prefix exec -T web sh -eu -c 'test ! -f /var/www/html/storage/framework/down'"
paused=1
remote "$compose_prefix exec -T web php artisan down --retry=60 >/dev/null"
remote "$compose_prefix stop -t 30 worker scheduler >/dev/null"

remote "$compose_prefix exec -T pgsql sh -eu -c 'exec pg_dump --format=custom --compress=6 --no-owner --no-privileges --username=\"\$POSTGRES_USER\" \"\$POSTGRES_DB\"'" \
	>"$payload_dir/database.dump"

remote "$compose_prefix exec -T web sh -eu -c 'cd /var/www/html/storage/app/private && exec tar -cf - .'" \
	>"$payload_dir/private-files.tar"

remote "exec cat '$RUNTIME_ENV'" >"$payload_dir/runtime.env"
remote "$compose_prefix exec -T web sh -eu -c 'test -f /var/www/html/release-manifest.json; exec cat /var/www/html/release-manifest.json'" \
	>"$payload_dir/release-manifest.json"

timestamp=$(date -u +%Y-%m-%d_%H-%M-%S)
archive_name="cigaronne.${timestamp}.tar"
{
	echo 'schema=cigaronne.daily-backup.v2'
	echo "created_at_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
	echo 'created_on=storage-only-backup-host'
	echo 'production_local_dump=false'
	echo 'rpo_budget_seconds=86400'
	echo 'database_format=postgresql-custom'
	echo 'private_files_format=tar'
} >"$payload_dir/backup-metadata.txt"

(
	cd "$payload_dir"
	sha256sum database.dump private-files.tar runtime.env release-manifest.json backup-metadata.txt >SHA256SUMS
)

tar -C "$payload_dir" -cf "$work_dir/$archive_name" .
tar -tf "$work_dir/$archive_name" >/dev/null
archive_sha=$(sha256sum "$work_dir/$archive_name" | cut -d ' ' -f1)
archive_size=$(wc -c <"$work_dir/$archive_name")

resume_application

install -m 0600 "$work_dir/$archive_name" "$BACKUP_DIR/$archive_name.new"
mv -f -- "$BACKUP_DIR/$archive_name.new" "$BACKUP_DIR/$archive_name"

metric_tmp="$work_dir/cigaronne-offsite-backup.prom"
completed_at=$(date +%s)
{
	echo '# HELP cigaronne_offsite_backup_last_success_timestamp_seconds Unix time of the latest verified backup created on the storage-only host.'
	echo '# TYPE cigaronne_offsite_backup_last_success_timestamp_seconds gauge'
	echo "cigaronne_offsite_backup_last_success_timestamp_seconds $completed_at"
	echo '# HELP cigaronne_offsite_backup_archive_bytes Size of the latest verified Cigaronne archive.'
	echo '# TYPE cigaronne_offsite_backup_archive_bytes gauge'
	echo "cigaronne_offsite_backup_archive_bytes $archive_size"
	echo '# HELP cigaronne_offsite_backup_production_local_dump Whether this workflow stored a dump on production.'
	echo '# TYPE cigaronne_offsite_backup_production_local_dump gauge'
	echo 'cigaronne_offsite_backup_production_local_dump 0'
} >"$metric_tmp"
chmod 0644 "$metric_tmp"

scp -q "${ssh_options[@]}" "$metric_tmp" "$remote_target:$METRIC_PATH.tmp"
remote "chmod 0644 '$METRIC_PATH.tmp' && mv -f '$METRIC_PATH.tmp' '$METRIC_PATH'"

echo "Created verified offsite Cigaronne archive: $archive_name"
echo "Archive SHA-256: $archive_sha"
echo "Archive bytes: $archive_size"
