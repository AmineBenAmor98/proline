#!/bin/sh
# Restore a dump from the bucket.
#
#   docker compose -f infra/docker-compose.prod.yml run --rm backup \
#       restore.sh                      # newest
#   docker compose ... run --rm backup \
#       restore.sh proline-20260924T031500Z.sql.gz
#
# THIS SCRIPT EXISTS TO BE RUN BEFORE YOU NEED IT. An untested restore is a
# hope, not a backup, and the failure modes -- a dump taken with the wrong
# credentials, a bucket policy that allows writes but not reads, a gzip
# truncated by a full disk -- all look like success until the day they don't.
# Run it once against a throwaway database and confirm a lead comes back.
set -eu

[ -n "${BACKUP_BUCKET:-}" ] || { echo "BACKUP_BUCKET is not set" >&2; exit 1; }

if [ -n "${PGPASSFILE_SRC:-}" ] && [ -r "$PGPASSFILE_SRC" ]; then
	PGPASSWORD="$(cat "$PGPASSFILE_SRC")"
	export PGPASSWORD
fi

key="${1:-}"
if [ -z "$key" ]; then
	key="$(aws s3 ls "s3://$BACKUP_BUCKET/db/" | awk '{print $4}' | sort | tail -1)"
	[ -n "$key" ] || { echo "no backups found in s3://$BACKUP_BUCKET/db/" >&2; exit 1; }
	echo "newest backup: $key"
fi

echo "This will OVERWRITE the database '${PGDATABASE:-proline}' on host '${PGHOST:-db}'."
printf 'Type the database name to confirm: '
read -r answer
[ "$answer" = "${PGDATABASE:-proline}" ] || { echo "aborted" >&2; exit 1; }

tmp=/tmp/restore.sql.gz
aws s3 cp "s3://$BACKUP_BUCKET/db/$key" "$tmp" --only-show-errors

# gzip -t first: a truncated upload restores halfway and leaves a database that
# looks populated and is missing its newest rows, which is worse than a clean
# failure.
gzip -t "$tmp" || { echo "archive is corrupt -- not restoring" >&2; exit 1; }

gunzip -c "$tmp" | psql --set ON_ERROR_STOP=on
rm -f "$tmp"
echo "restored $key"
