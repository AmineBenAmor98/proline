#!/bin/sh
# Nightly dump of the lead database to the Lightsail bucket.
#
# The dump is the easy part. The part that matters is the heartbeat: on success
# this writes the timestamp to a volume the app mounts read-only, and /admin
# shows its age on every visit. A backup nobody would notice stopping is not a
# backup, and the usual way this fails is not a crash -- it is a disk filling,
# or a rotated key, four months before anyone looks.
#
# Exit codes are deliberate: any failure leaves the heartbeat stale rather than
# touching it, so a run that half-worked still raises the alarm.
set -eu

STATE_DIR=/var/lib/proline/backup
HEARTBEAT="$STATE_DIR/last-success"
LAST_ERROR="$STATE_DIR/last-error"
KEEP_DAYS="${KEEP_DAYS:-30}"

log() { echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') backup: $*"; }

fail() {
	log "FAILED: $*"
	mkdir -p "$STATE_DIR"
	printf '%s\n%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*" > "$LAST_ERROR"
	return 1
}

run_once() {
	mkdir -p "$STATE_DIR"

	[ -n "${BACKUP_BUCKET:-}" ] || { fail "BACKUP_BUCKET is not set"; return 1; }

	# The compose secret is a file; libpq wants it in the environment.
	if [ -n "${PGPASSFILE_SRC:-}" ] && [ -r "$PGPASSFILE_SRC" ]; then
		PGPASSWORD="$(cat "$PGPASSFILE_SRC")"
		export PGPASSWORD
	fi

	stamp="$(date -u '+%Y%m%dT%H%M%SZ')"
	tmp="/tmp/proline-$stamp.sql.gz"

	# --clean --if-exists so the dump restores over an existing database without
	# hand-dropping it first; that is the state you are in during a real
	# recovery, and a backup that only restores into an empty database is a
	# backup you will fight at the worst moment.
	if ! pg_dump --clean --if-exists --no-owner --no-privileges | gzip -9 > "$tmp"; then
		rm -f "$tmp"
		fail "pg_dump failed"
		return 1
	fi

	size=$(wc -c < "$tmp")
	# An empty or near-empty dump means pg_dump "succeeded" against nothing.
	# 1 KiB is far below a schema-only dump of this database.
	if [ "$size" -lt 1024 ]; then
		rm -f "$tmp"
		fail "dump was only ${size} bytes -- refusing to call that a backup"
		return 1
	fi

	if ! aws s3 cp "$tmp" "s3://$BACKUP_BUCKET/db/proline-$stamp.sql.gz" --only-show-errors; then
		rm -f "$tmp"
		fail "upload to s3://$BACKUP_BUCKET failed"
		return 1
	fi
	rm -f "$tmp"

	# Only now, with bytes confirmed in the bucket.
	date -u '+%Y-%m-%dT%H:%M:%SZ' > "$HEARTBEAT"
	rm -f "$LAST_ERROR"
	log "ok, ${size} bytes -> db/proline-$stamp.sql.gz"

	prune
}

# Old dumps cost $0.023/GB and hide the recent ones. Failure to prune is not
# failure to back up, so it never touches the heartbeat.
prune() {
	cutoff="$(date -u -d "-${KEEP_DAYS} days" '+%Y%m%d' 2>/dev/null || true)"
	[ -n "$cutoff" ] || return 0
	aws s3 ls "s3://$BACKUP_BUCKET/db/" 2>/dev/null | awk '{print $4}' | while read -r key; do
		[ -n "$key" ] || continue
		day="$(echo "$key" | sed -n 's/^proline-\([0-9]\{8\}\)T.*/\1/p')"
		[ -n "$day" ] || continue
		[ "$day" -lt "$cutoff" ] 2>/dev/null || continue
		aws s3 rm "s3://$BACKUP_BUCKET/db/$key" --only-show-errors || true
		log "pruned $key"
	done
}

case "${1:-}" in
--loop)
	log "started; nightly at 03:15 UTC, keeping ${KEEP_DAYS} days"
	# One run at boot: a fresh deploy should not wait until tomorrow to have a
	# backup, and a broken configuration should announce itself now.
	run_once || true
	while :; do
		now=$(date -u +%s)
		next=$(date -u -d 'tomorrow 03:15' +%s 2>/dev/null || echo $((now + 86400)))
		sleep $((next - now))
		run_once || true
	done
	;;
*)
	run_once
	;;
esac
