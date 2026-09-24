# pg_dump has to match the server's major version, so this starts from the same
# Postgres image the database runs, and adds the S3 client on top rather than
# starting from an AWS image and trying to get a matching pg_dump into it.
FROM postgres:16-alpine

# coreutils is not optional. Alpine ships busybox `date`, which has no relative
# arithmetic: both `date -d 'tomorrow 03:15'` (the nightly schedule) and
# `date -d '-30 days'` (the prune cutoff) fail on it. Both calls have fallbacks,
# so without this the container would not crash -- it would quietly drift to
# "every 24h from whenever it last restarted" and silently stop pruning, which
# is precisely the kind of failure this whole service exists to prevent.
RUN apk add --no-cache aws-cli coreutils tzdata

COPY backup.sh /usr/local/bin/backup.sh
COPY restore.sh /usr/local/bin/restore.sh
RUN chmod +x /usr/local/bin/backup.sh /usr/local/bin/restore.sh

# No cron. A loop in PID 1 is restarted by Docker if it dies, and its output
# goes to `docker compose logs backup` -- neither is true of crond in a
# container, where a failing job writes to a mail spool nobody reads.
CMD ["/usr/local/bin/backup.sh", "--loop"]
