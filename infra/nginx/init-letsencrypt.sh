#!/bin/sh
# Issue the FIRST TLS certificate, and bring the stack up around it. Run once,
# on the box, after DNS points at it:
#
#     cd /srv/proline/src
#     sudo infra/nginx/init-letsencrypt.sh you@example.com
#
# Every deploy after this one is just:
#
#     git pull && docker compose -f infra/docker-compose.prod.yml up -d --build
#
# ---------------------------------------------------------------------------
# WHY THIS SCRIPT HAS TO EXIST
#
# nginx refuses to start when `ssl_certificate` names a file that is not there.
# certbot's HTTP-01 challenge needs something already answering on port 80. So
# neither can go first, and a plain `docker compose up -d` on a fresh box gets
# stuck: nginx crash-loops, certbot never gets its challenge served.
#
# The way out is a throwaway self-signed certificate. nginx starts on that,
# certbot uses the running nginx to prove the domain, and the real certificate
# replaces the fake one. That is the whole trick, and it is all this script does.
#
# Caddy did this by itself -- it was the reason Caddy was here. This file is the
# honest price of running nginx instead. It is also the only place that price is
# paid: after today, certbot renews and nginx reloads on their own.
# ---------------------------------------------------------------------------
set -eu

DOMAIN=proline-cleaningsolutions.com
COMPOSE_FILE=infra/docker-compose.prod.yml
LIVE=/etc/letsencrypt/live/$DOMAIN

EMAIL=${1:-}
if [ -z "$EMAIL" ]; then
	echo "usage: $0 <email>" >&2
	echo "  The address Let's Encrypt mails if a renewal ever stops working." >&2
	echo "  Use one you actually read -- it is the only warning you get." >&2
	exit 2
fi

[ -f "$COMPOSE_FILE" ] || {
	echo "error: run this from the repo root on the box (/srv/proline/src)." >&2
	exit 2
}

compose() { docker compose -f "$COMPOSE_FILE" "$@"; }

# The certbot service's entrypoint is the renewal loop, so a one-off certbot
# command has to replace the entrypoint as well as the arguments. Without
# --entrypoint, the arguments below are handed to that loop and silently ignored.
certbot() { compose run --rm --entrypoint certbot certbot "$@"; }

# --- 1. Refuse to burn a rate limit -----------------------------------------
# Let's Encrypt allows 5 failed validations per hostname per hour. The single
# most common way to spend them is running this before DNS has propagated, so
# check first: it costs a second and turns an hour-long lockout into a message.
echo "==> checking DNS"
ip=$(curl -fsS https://checkip.amazonaws.com | tr -d '\n')
for name in "$DOMAIN" "www.$DOMAIN"; do
	got=$(getent hosts "$name" | awk '{print $1; exit}' || true)
	if [ "$got" != "$ip" ]; then
		echo "error: $name resolves to '${got:-nothing}', but this box is $ip." >&2
		echo "  Fix the records at GoDaddy first -- see infra/DNS.md -- and wait" >&2
		echo "  out the TTL (1 hour on most of them)." >&2
		exit 1
	fi
	echo "    $name -> $ip"
done

# --- 2. A fake certificate, so nginx can start ------------------------------
echo "==> placing a temporary self-signed certificate"
compose run --rm --entrypoint sh certbot -c "
	mkdir -p '$LIVE' &&
	openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
		-keyout '$LIVE/privkey.pem' -out '$LIVE/fullchain.pem' \
		-subj '/CN=$DOMAIN' 2>/dev/null
"

# --- 3. Start everything ----------------------------------------------------
# The build takes about ninety seconds the first time. nginx comes up on the fake
# certificate: browsers will warn, which is expected for the next minute.
echo "==> building and starting the stack"
compose up -d --build

echo "==> waiting for nginx to answer on port 80"
i=0
until curl -fsS -o /dev/null "http://localhost/nginx-healthz"; do
	i=$((i + 1))
	[ "$i" -lt 30 ] || {
		echo "error: nginx is not answering. Look at:" >&2
		echo "  docker compose -f $COMPOSE_FILE logs nginx" >&2
		exit 1
	}
	sleep 2
done

# --- 4. Drop the fake certificate BEFORE asking for the real one ------------
# Deliberately before, not after. certbot keys its state on the directory name,
# so a lineage already sitting there turns a clean first issuance into an
# ambiguous renew-or-expand decision, which is where this step goes wrong when
# people script it. Removing it first means certbot starts from nothing.
#
# The nginx already running is unaffected: it read those files at startup and
# holds them in memory. It only needs them on disk again at the next reload --
# which is step 6, by which point the real ones are there.
echo "==> removing the temporary certificate"
compose run --rm --entrypoint sh certbot -c "
	rm -rf '/etc/letsencrypt/live/$DOMAIN' \
	       '/etc/letsencrypt/archive/$DOMAIN' \
	       '/etc/letsencrypt/renewal/$DOMAIN.conf'
"

# --- 5. Dry run, then the real thing ----------------------------------------
# The dry run goes to Let's Encrypt's staging service: it performs the identical
# challenge, writes nothing, and does not count against the rate limit. If the
# challenge is going to fail, it fails here for free.
echo "==> dry run against staging"
certbot certonly --webroot -w /var/www/certbot \
	-d "$DOMAIN" -d "www.$DOMAIN" \
	--email "$EMAIL" --agree-tos --no-eff-email --non-interactive --dry-run

echo "==> requesting the real certificate"
# The FIRST -d sets the directory name under live/, which the nginx config names
# literally. Keep the apex first.
certbot certonly --webroot -w /var/www/certbot \
	-d "$DOMAIN" -d "www.$DOMAIN" \
	--email "$EMAIL" --agree-tos --no-eff-email --non-interactive

# --- 6. Hand it to nginx ----------------------------------------------------
echo "==> reloading nginx"
compose exec nginx nginx -s reload

echo
echo "Done. Check it:"
echo "  curl -sS https://$DOMAIN/healthz"
echo "  curl -sS https://www.$DOMAIN/healthz"
echo
echo "Renewal is automatic from here: the certbot container tries twice a day and"
echo "nginx reloads every six hours. Nothing to schedule and no cron to write."
echo "To prove that works without waiting 60 days:"
echo "  docker compose -f $COMPOSE_FILE run --rm --entrypoint certbot certbot renew --dry-run"
