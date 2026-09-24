# Deploying Proline

One Lightsail instance in Montreal runs everything: the app, Postgres, Caddy and
the nightly backup, as four containers. A $1 bucket holds the dumps. SES sends
the mail. Total ≈ $13/month on AWS, plus the domain and mailbox at GoDaddy.

The AWS side is Pulumi (`infra/pulumi/`). What is left by hand is deliberate and
small: the domain and its DNS, because it lives at GoDaddy; the SES production
request, because a person reviews it; and the two `.env` files on the box,
because putting secrets in user data or in stack state is how they leak.

**Read this in order.** Step 2 is the only one with a queue in it — SES
production access is reviewed by a human and can take a day — so it comes before
the work that takes twenty minutes.

---

## 0. Secure the account

Once there is a running instance and a bucket, the root account is a key to a
live business.

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

## 1. Buy the domain and mailbox at GoDaddy

- `prolinecleaningsolutions.ca`
- A mailbox at `info@prolinecleaningsolutions.ca` (GoDaddy's cheapest email
  plan).

This blocks steps 2 and 4, so it is first. The mailbox is where clients' replies
land; SES only *sends*.

---

## 2. Provision AWS

```sh
cd infra/pulumi
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
pulumi stack select prod --create

pulumi config set sshPublicKey "$(cat ~/.ssh/id_ed25519.pub)"
pulumi config set adminSshCidr "$(curl -s https://checkip.amazonaws.com)/32"
```

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
daily whole-disk snapshots, the $1 backup bucket with its own scoped access key,
the SES domain identity with Easy DKIM, and a send-only IAM user for SMTP.

`user-data.sh` runs on first boot and installs Docker, 2 GB of swap, capped
container logging and unattended security upgrades. Give it two or three minutes
after `pulumi up` returns; `/var/log/cloud-init-output.log` on the box says when
it finished.

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

Enter those seven records. **Do this before bringing Caddy up** — Caddy gets its
certificate through an HTTP challenge, which needs the name to already resolve
to the box.

Two traps, both in the records Pulumi prints:

- **SPF must be a single TXT record naming both senders.** SES sends the offers;
  GoDaddy sends whatever you type by hand from `info@`. Two SPF records on one
  name is a permanent failure, not a merge — if GoDaddy already made one, *edit*
  it. Check GoDaddy's current docs for their exact include; `secureserver.net`
  is the usual one and is what Pulumi prints, unverified.
- **DMARC starts at `p=none` on purpose**, so a misconfiguration arrives as a
  report instead of silently binning your mail. Tighten to `quarantine` after a
  few clean weeks.

Confirm before continuing:

```sh
dig +short prolinecleaningsolutions.ca      # the static IP
```

---

## 4. The two secret files

SSH in with `$(pulumi stack output ssh)`, then:

```sh
cd /srv/proline
git clone https://github.com/AmineBenAmor98/proline.git src
cp src/infra/Caddyfile /srv/proline/Caddyfile

# The database password. Generated on the box, never typed, never in git,
# never in Pulumi state.
openssl rand -base64 32 | tr -d '\n' > /srv/proline/db_password
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
ADMIN_PASSWORD=<openssl rand -base64 24>
SECRET_KEY=<openssl rand -hex 32>

# Paste the five lines from: pulumi stack output env_smtp --show-secrets
SMTP_HOST=...

MAIL_FROM=Proline Cleaning Solutions <info@prolinecleaningsolutions.ca>
MAIL_REPLY_TO=info@prolinecleaningsolutions.ca
NOTIFY_EMAIL_TO=<your inbox>
```

`ENVIRONMENT=production` is set by compose, not here — that is what arms the
refuse-to-start check above.

### `/srv/proline/.env.backup`

Separate on purpose: these are write credentials for every backup you have, and
the web process — the one container reachable from the internet — has no reason
to carry them.

```sh
pulumi stack output env_backup --show-secrets
```

`chmod 600` both files.

---

## 5. Deploy

```sh
cd /srv/proline/src
docker compose -f infra/docker-compose.prod.yml up -d --build
```

The image is built on the box rather than pulled; there is no registry and no
pull credential. The app container runs `alembic upgrade head` before uvicorn,
so the schema creates itself. The backup container runs once immediately rather
than waiting for 03:15, so a broken bucket credential announces itself now.

```sh
docker compose -f infra/docker-compose.prod.yml ps
docker compose -f infra/docker-compose.prod.yml logs backup   # "ok, N bytes -> db/..."
curl -sS https://prolinecleaningsolutions.ca/healthz
```

If Caddy is looping on certificate errors, DNS is not resolving to this box yet.
Let it retry — it backs off — rather than restarting it repeatedly, because
Let's Encrypt rate-limits failed validations per hostname per hour.

---

## 6. Before you call it launched

- **Sign in to `/admin`** and confirm the backup banner is *absent*. It appears
  when the last successful backup is more than 36 hours old.
- **Send yourself an offer** from a test lead. While SES is in the sandbox this
  only works to a verified address, which is exactly what you are testing.
- **Run the restore once, against a throwaway database:**

  ```sh
  docker compose -f infra/docker-compose.prod.yml run --rm \
    -e PGDATABASE=proline_restore_test backup restore.sh
  ```

  An untested restore is a hope. The failure modes — a bucket policy that allows
  writes but not reads, a dump taken with the wrong credentials, a gzip
  truncated by a full disk — all look exactly like success until the day they
  don't.
- **Replace the placeholder prices** with real figures. The site quotes whatever
  is published.

---

## Updating later

```sh
cd /srv/proline/src && git pull
docker compose -f infra/docker-compose.prod.yml up -d --build
```

Migrations run on container start. The build takes about ninety seconds and the
old container keeps serving until the new one is healthy.

Infrastructure changes go through `pulumi up` from your laptop. Note that
changing `blueprint_id`, `bundle_id` or `user_data` **replaces the instance** —
Lightsail cannot resize in place. Plan that as a rebuild: the database lives in
a Docker volume on that disk, so restore from the bucket afterwards, and check
`pulumi preview` for the word `replace` before accepting any infrastructure
change you did not expect to be destructive.
