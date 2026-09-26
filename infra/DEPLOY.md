# Deploying Proline

One Lightsail instance in Montreal runs everything: the app, Postgres, nginx, and
a certbot whose only job is renewing the certificate — four containers. SES sends
the mail. Total ≈ $12/month on AWS, plus the domain and mailbox at GoDaddy.

**The recovery point is the instance's daily whole-disk snapshot**, nothing else.
That means one recovery point per day, and restoring means rebuilding the box from
a snapshot — the database is a Docker volume on that disk, so the snapshot does
cover it. There is no nightly dump to a bucket by choice; `git log -- infra/backup`
has that version if it is ever wanted.

The AWS side is Pulumi (`infra/pulumi/`). What is left by hand is deliberate and
small: the domain and its DNS, because it lives at GoDaddy; the SES production
request, because a person reviews it; and the secrets on the box (`.env` and
`db_password`), because putting those in user data or in stack state is how they
leak.

**Read this in order.** Step 2 is the only one with a queue in it — SES
production access is reviewed by a human and can take a day — so it comes before
the work that takes twenty minutes.

---

## 0. Secure the account

Once there is a running instance, the root account is a key to a live business.

- **MFA on the root user.** IAM → Security credentials.
- **No access keys on root.** If one exists, delete it.
- **An IAM admin user for yourself**, used for everything below. ✔ done
- **A budget alarm.** Billing → Budgets → monthly cost budget, $25, alert at
  80%. This is what catches a mistake while it is still cheap.

Put the IAM keys in a named AWS profile rather than in the repo:

```sh
aws configure --profile proline      # paste the access key and secret here
export AWS_PROFILE=proline
```

`infra/.env` is covered by `.gitignore`, so keys there are not going to be
committed — but credentials in `~/.aws` cannot be reached by a `.gitignore`
mistake, a `git clean -fdx`, or a stray `tar` of the working tree at all. Move
them and delete `infra/.env`.

---

## 1. The domain

`proline-cleaningsolutions.com` is already registered at GoDaddy — its
nameservers are `ns31/ns32.domaincontrol.com` and it currently answers on
GoDaddy's parking addresses. Nothing to buy. Step 3 repoints it — which is one
edit to the apex `A` record, since `www` is already a `CNAME` pointing at it.

**The domain already runs Microsoft 365 email** — its MX points at
`prolinecleaningsolutions-com01i.mail.protection.outlook.com`. So there is no
email plan to buy: confirm `contact@proline-cleaningsolutions.com` exists in the
Microsoft 365 admin centre, and create it there if not. That mailbox is where
clients' replies land — SES only *sends*, and `MAIL_REPLY_TO` points at it, so
replies bounce without it.

`infra/DNS.md` documents every record in the zone and which system owns it. Read
it before changing anything in GoDaddy: two mail systems share this domain, and
the SPF and DMARC records are shared between them.

---

## 2. Provision AWS

```sh
cd infra/pulumi
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
pulumi stack select prod --create

pulumi config set sshPublicKey "$(cat ~/.ssh/id_ed25519.pub)"
pulumi config set sshCidr 0.0.0.0/0
```

**`sshCidr` is 0.0.0.0/0 on purpose, and it has one prerequisite.** Port 22 open
to the internet is safe only because sshd accepts keys and not passwords — there
is nothing to guess. Confirm that on the box rather than assuming it:

```sh
sudo sshd -T | grep -iE 'passwordauthentication|permitrootlogin'
# passwordauthentication no
# permitrootlogin (prohibit-password|no)
```

If `passwordauthentication` says `yes`, fix that before leaving port 22 open —
`/etc/ssh/sshd_config.d/` on Ubuntu, then `sudo systemctl reload ssh`.

This started as a `/32` of the operator's own address and was changed
deliberately. The narrow thing a `/32` buys is cover against an sshd
vulnerability you have not patched yet: real, but low-probability, and paid for
with a lockout every time your address changes — one that presents as a dead
instance, because a dropped packet gets no reply while 80 and 443 answer
instantly. If you want it back, set `sshCidr` to your own `/32` and remember that
Pulumi writes it into `Pulumi.prod.yaml`, which is committed to a public repo.

Confirm the one value that cannot be looked up from code — AWS renamed the
bundle suffix from `_2_0` to `_3_0` when the current pricing landed, and a wrong
value fails with an unhelpful API error:

```sh
aws lightsail get-bundles --region ca-central-1 \
  --query 'bundles[?ramSizeInGb==`2.0`].[bundleId,price,ramSizeInGb,cpuCount]' \
  --output table
# if it is not small_3_0:  pulumi config set instanceBundle <what it says>
```

Then:

```sh
pulumi up
```

That creates the instance (Ubuntu 24.04, 2 GB / 2 vCPU / 60 GB / 3 TB, $12), its
static IP, a firewall that opens 80 and 443 to the world and 22 only to you,
daily whole-disk snapshots, the SES domain identity with Easy DKIM, and a
send-only IAM user for SMTP.

`user-data.sh` runs on first boot and installs Docker, 2 GB of swap, capped
container logging and unattended security upgrades. Give it two or three minutes
after `pulumi up` returns.

**Then verify it, before anything else.** This has already failed once, silently:
the script aborted on its own first line and did nothing, and the only symptom was
`docker: command not found` half an hour later, with apt reporting no installation
candidate for anything. Cloud-init reported `status: error` the whole time and
nobody looked.

```sh
sudo cloud-init status --long          # must say: status: done
docker --version && docker compose version
swapon --show                         # must list /swapfile, 2G
test -d /srv/proline && echo srv ok
```

If `cloud-init status` says `error`, read `/var/log/cloud-init-output.log` — the
script runs under `set -x`, so the last lines name the failing command outright.
Do not work around it by installing packages by hand: whatever it skipped, it
skipped in order, so the swap and `/srv/proline` are missing too, and a 2 GB box
with no swap gets OOM-killed during `up -d --build`. Re-run the whole thing
instead, from a clone on the box:

```sh
sudo bash infra/pulumi/user-data.sh    # idempotent: safe to re-run
```

Use `bash` explicitly. Cloud-init on Lightsail has been observed running user data
under `/bin/sh` regardless of the shebang, which is what broke it the first time.

**Then, in the console, request SES production access** — SES → Account
dashboard → Request production access. There is no API for it. Until it is
granted the account is in the *sandbox*, which can only send to addresses you
have individually verified, meaning **offer emails to real clients silently go
nowhere**. Approval is usually under 24 hours. Start it now, not on launch day.

---

## 3. DNS at GoDaddy

```sh
pulumi stack output dns_records
```

Enter those seven records, leaving GoDaddy's TTL at its default. The columns are
headed to match its form: TYPE, NAME, VALUE.

**Read them from that command, not from the summary `pulumi up` prints when it
finishes.** That summary truncates long strings with `...` and escapes the
newlines, so what it shows is an incomplete record set that looks complete —
which for a DKIM CNAME means mail quietly fails authentication.

**Do this before step 5.** The certificate is issued through an HTTP challenge
against both the apex and `www`, so *both* names must already resolve to the box.
Step 5 checks, and stops rather than burning a rate limit, but the wait is the
TTL either way — an hour on most of these records.

In practice only the apex `A` record changes. **Edit GoDaddy's existing `A @`**
from its parking address to the static IP; do not add a second one beside it.
**Leave `www` alone** — GoDaddy ships it as a `CNAME` to the apex, which is
exactly what you want, and a name cannot hold both a CNAME and an A record, so
there is no `A www` to delete or create.

**SPF and DMARC are the two records that can break your email**, because
Microsoft 365 shares them with SES. `infra/DNS.md` has the current values and
what each mechanism is for — read section 5 of it before touching either, and do
not take the SPF or DMARC wording from `pulumi stack output` at face value: it is
written for an empty zone, and this zone is not empty.

Confirm before continuing:

```sh
dig +short proline-cleaningsolutions.com      # the static IP
```

---

## 4. The secret file

SSH in with `$(pulumi stack output ssh)`.

**If that answers `Permission denied (publickey)` on a box you just created, wait
two minutes and try again before debugging anything.** Lightsail reports the
instance as running, and sshd answers, before cloud-init has written
`/home/ubuntu/.ssh/authorized_keys` — so the rejection looks like a wrong key and
is not one. To tell the two apart in one command, compare the fingerprints:

```sh
ssh-keygen -lf ~/.ssh/id_ed25519.pub
pulumi config get sshPublicKey | ssh-keygen -lf -
```

Equal means the key is right and the answer is patience. Different means
`pulumi config set sshPublicKey` captured the wrong file — fix it and re-run
`pulumi up`, which replaces the key pair without rebuilding the instance.

Then, on the box:

```sh
cd /srv/proline
git clone https://github.com/AmineBenAmor98/proline.git src

# The database password. Generated on the box, never typed, never in git,
# never in Pulumi state.
#
# HEX, NOT BASE64. This password gets pasted into DATABASE_URL below, and base64
# contains `+` and `/` -- about 74% of 32-byte base64 strings contain at least
# one. A `/` in the password ends the URL's authority section, so
# `postgresql+asyncpg://proline:ab/cd@db:5432/proline` parses with `proline` as
# the HOSTNAME. The app then fails to reach a database with an error that names
# neither the password nor the URL. Hex has 32 bytes of entropy and no character
# that means anything to a URL parser.
openssl rand -hex 32 > /srv/proline/db_password
chmod 600 /srv/proline/db_password
```

### `/srv/proline/.env`

```ini
# Must carry the same password as /srv/proline/db_password. The app does not
# read the secret file -- Postgres does. Paste it in.
DATABASE_URL=postgresql+asyncpg://proline:<contents of db_password>@db:5432/proline

# The app refuses to start in production on any of these defaults, which is the
# point. Generate, do not invent.
ADMIN_USERNAME=<not "admin">
ADMIN_PASSWORD=<openssl rand -hex 18>
SECRET_KEY=<openssl rand -hex 32>

# Paste the five lines from: pulumi stack output env_smtp --show-secrets
SMTP_HOST=...

# All three are the company mailbox, on purpose. See infra/IDENTITIES.md.
MAIL_FROM=Proline Cleaning Solutions <contact@proline-cleaningsolutions.com>
MAIL_REPLY_TO=contact@proline-cleaningsolutions.com
NOTIFY_EMAIL_TO=contact@proline-cleaningsolutions.com
```

`NOTIFY_EMAIL_TO` is the company mailbox rather than a personal address, and that
is not only tidiness. A lead notification is company correspondence: it has to
survive the person who set the site up losing their phone, changing address, or
leaving. It also keeps every trace of one enquiry — the notification and the
client's reply — in a single mailbox, instead of the notification in one inbox and
the reply in another.

It has a practical benefit too: while SES is in the sandbox it may only deliver to
addresses you have verified, and the whole domain is already a verified identity —
so notifications to `contact@` work today, where a Gmail address would need
verifying separately.

`ENVIRONMENT=production` is set by compose, not here — that is what arms the
refuse-to-start check above.

`chmod 600` it.

---

## 5. Deploy, and get the first certificate

**The first time, one command does both:**

```sh
cd /srv/proline/src
sudo infra/nginx/init-letsencrypt.sh <an email you actually read>
```

That builds the image, starts all four containers, and issues the certificate.
Use a real address — it is where Let's Encrypt writes if a renewal ever stops
working, and it is the only warning you get.

Why a script rather than `up -d`: nginx will not start without a certificate file,
and certbot cannot get a certificate without nginx already answering on port 80.
The script breaks that loop with a throwaway self-signed certificate, then
replaces it with the real one. It checks DNS first and does a staging dry run
before the real request, so a mistake costs a message rather than an hour of
Let's Encrypt rate limiting. The long comment at the top of the script explains
each step; **read it before changing any of them, particularly the order.**

Expect a browser certificate warning for the minute between nginx starting and
the script finishing. That is the throwaway certificate, and it is normal.

The image is built on the box rather than pulled; there is no registry and no pull
credential. The app container runs `alembic upgrade head` before uvicorn, so the
schema creates itself.

```sh
docker compose -f infra/docker-compose.prod.yml ps        # four services, healthy
curl -sS https://proline-cleaningsolutions.com/healthz
curl -sS https://www.proline-cleaningsolutions.com/healthz
curl -sI http://proline-cleaningsolutions.com/ | head -1   # 301 to https
```

**Renewal is automatic and needs no cron.** The certbot container tries twice a
day; certbot renews at 30 days remaining, so there are about sixty chances before
anything expires. nginx reloads itself every six hours to pick up a renewed
certificate — a reload it needs, because a new file on disk does nothing until
nginx re-reads it. Prove the whole path works today rather than finding out in
sixty days:

```sh
docker compose -f infra/docker-compose.prod.yml \
  run --rm --entrypoint certbot certbot renew --dry-run
```

If that fails, the usual cause is port 80: something must serve
`/.well-known/acme-challenge/` without redirecting it, which is the first
`location` block in `infra/nginx/conf.d/proline.conf`. Do not "tidy" that block
away into the HTTPS redirect — renewal is the only thing that uses it, and it
fails silently two months later.

---

## 6. Before you call it launched

- **Sign in to `/admin`** and confirm it loads and the request list appears.
- **Send yourself an offer** from a test lead. While SES is in the sandbox this
  only works to a verified address, which is exactly what you are testing.
- **Confirm a snapshot actually exists**, in the Lightsail console under the
  instance's Snapshots tab, the day after launch. An automatic snapshot nobody ever
  verified is the same as no snapshot. Note while you are there that restoring one
  creates a *new* instance — so recovery also means re-attaching the static IP,
  which is the step people forget under pressure.

- **Replace the placeholder prices** with real figures. The site quotes whatever
  is published.

- **Watch the disk, because photos land on it.** Customer photos go in the
  `photos` volume, on the same 60 GB disk as Postgres, and a full disk stops the
  database accepting writes — which loses leads, silently. The browser resizes
  each photo to roughly 200 KB before upload and the app caps count and size, so
  the realistic rate is about 1 MB per request; that is years of headroom, not
  months. Check it occasionally rather than trusting the arithmetic:

  ```sh
  df -h /                                      # past 60% is the moment to act
  docker system df -v | grep proline_photos    # what the photos themselves use
  ```

  Photos older than `PHOTO_RETENTION_DAYS` (a year by default) are deleted daily
  by the `photo-prune` container. To see what it would remove without removing
  anything:

  ```sh
  docker compose -f infra/docker-compose.prod.yml \
    run --rm --entrypoint "python -m scripts.prune_photos --dry-run" photo-prune
  ```

  Turning photos off entirely is one variable: unset `PHOTOS_DIR` and redeploy.
  The form hides its photo control and the upload endpoint answers 503 — no
  frontend change needed.

---

## Updating later

```sh
cd /srv/proline/src && git pull
docker compose -f infra/docker-compose.prod.yml up -d --build
```

Migrations run on container start. The build takes about ninety seconds and the
old container keeps serving until the new one is healthy.

**If the pull changed `infra/nginx/conf.d/`, add a reload.** The file is mounted
from the checkout, so `git pull` updates what is on disk — but compose only
recreates a service whose *definition* changed, and the nginx service definition
did not. So nginx keeps running the old configuration until its next six-hourly
reload, which looks exactly like the change not working:

```sh
docker compose -f infra/docker-compose.prod.yml exec nginx nginx -t   # check first
docker compose -f infra/docker-compose.prod.yml exec nginx nginx -s reload
```

`nginx -t` first, every time. A reload with a broken config is refused and the old
one keeps serving; a *restart* with a broken config leaves you with no web server.

Infrastructure changes go through `pulumi up` from your laptop. Note that
changing `blueprint_id`, `bundle_id` or `user_data` **replaces the instance** —
Lightsail cannot resize in place. Plan that as a rebuild: the database lives in
a Docker volume on that disk, so restore from the newest snapshot afterwards, and
check
`pulumi preview` for the word `replace` before accepting any infrastructure
change you did not expect to be destructive.
