# Proline Cleaning Solutions

Quote capture, pricing and admin for Proline Cleaning Solutions (Montreal).
One FastAPI process serves the API **and** the site — the same shape as kfz.

```
backend/     FastAPI: API, pricing engine, models, migrations
frontend/    static HTML, CSS and vanilla JS (FR + EN + /admin)
infra/       docker-compose for local Postgres; the production stack, nginx/certbot and Pulumi for ca-central-1
             DEPLOY.md is the launch sequence in order; DNS.md is the zone, record by record
             IDENTITIES.md is who-is-who: the seven logins, where each secret lives, how mail flows
Dockerfile   one image: backend + frontend, migrations then uvicorn
```

## Run it locally

One command, everything included (Postgres, schema, rate card, site):

```bash
make dev          # or: docker compose -f infra/docker-compose.yml up --build
```

Then open http://localhost:8000. Code and pages are mounted, so edits reload without a
rebuild. `make down` stops it, `make reset` also deletes the database volume.

Other targets: `make test`, `make seed`, `make psql`, `make logs`, `make lint`.

### Without Docker

```bash
# 1. Postgres (brew install postgresql@16 && brew services start postgresql@16 && createdb proline)
#    then set DATABASE_URL in backend/.env

# 2. Python deps
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # then set ADMIN_USERNAME, ADMIN_PASSWORD, SECRET_KEY

# 3. Schema + a rate card so prices exist
alembic upgrade head
python -m scripts.seed_rate_card

# 4. Serve everything on http://localhost:8000
uvicorn app.main:app --reload
```

| URL | What |
| --- | --- |
| `/` `/commercial` `/soumission` | French site |
| `/en` `/en/commercial` `/en/soumission` | English site |
| `/admin` | Sign-in (ADMIN_USERNAME / ADMIN_PASSWORD), then the request list |
| `/api/quotes` `POST` | Submit a request |
| `/api/quotes/price` `POST` | Live residential price |
| `/api/admin/requests` | List / patch, Bearer token |
| `/admin/demande?id=…` | One request in full: photos, notes, the offer |
| `/docs` | OpenAPI |

## Tests

```bash
cd backend
pytest            # the API
```

```bash
make test-form    # the pages themselves, in a real DOM
```

Two suites, and the second one is not optional. `pytest` covers the API
thoroughly and is **green on every page-level bug this project has had**: a detail
page that rendered nothing, a price breakdown printing raw codes, a rejected
washroom count reported to the visitor as "sending failed, call us", a photo
block that never appeared because an unrelated crash killed the line that mounted
it. `make test-form` loads the real markup, runs the real scripts, and asserts on
what ends up on screen. Add a case there whenever something reaches the browser
that the API tests could not have caught.

```bash
cd backend
pytest
ruff check .
```

The suite owns its database. `DATABASE_URL` says which **server**; the tests run in a
`<name>_test` database beside it, which `tests/conftest.py` creates, migrates from scratch
and truncates-and-reseeds **before every test**. So running `pytest` twice gives the same
answer as running it once, and no test can be made to pass by what an earlier one left
behind. It does mean Postgres has to be up — `make up` is enough, and `make test` runs the
suite inside the compose container.

The schema under test is the one the migrations produce, never `create_all`, because a
migration that is broken should fail here rather than on deploy.

## How pricing works

`backend/app/pricing/` is pure functions: inputs in, a breakdown out. No database, no clock,
no network — so a pricing bug can always be reproduced in four lines, with no fixtures.

- **Residential** — a flat grid by bedrooms and bathrooms, plus an area surcharge, priced
  extras and a recurring discount. Returned to the visitor as a firm price.
- **Commercial** — minutes of work per 100 sq ft per service, times the hourly rate, plus
  restrooms, night access and travel. Computed and stored, **never shown**: the client is
  told a written quote arrives within 24 h, and a human reviews the number first.

**The order is fixed and tested**, because it used to be wrong:

```
base + area                          →  the work
work × modifiers (capped)            →  how hard this one is
        + modifier amounts
        + extras                     →  subtotal
subtotal − frequency discount        →  what the client is charged
floor at the minimum visit           →  total
```

A **modifier** is a question whose answer changes the price — *premier ménage*,
*état*, *animaux*, *vide*. A multiplier scales the work; an amount is added after
it, so two amounts never compound. Neither touches the extras, whose per-unit
prices already scale with their own quantity. Multipliers compound with each
other under `max_residential_multiplier`, and the line says `(plafonné)` when the
ceiling bites. Questions, answers and prices all live on the rate card — adding a
fifth question takes no code. See [`docs/PRICING-V2.md`](docs/PRICING-V2.md).

The **minimum visit is last**. It is a promise about what the client pays, not about the
arithmetic behind it. Applied before the discount — which is how it was — a weekly client
on a 120 $ minimum was quoted **102 $**, and the discount was computed on the floor rather
than on the work, inflating it as well. When the floor bites, the gap is reported as
`minimum_adjustment_cents` and rendered as its own line, so `lines − discount + minimum`
always equals the total. `test_the_breakdown_adds_up` holds that.

**The engine never invents an input.** No price is better than a wrong one, because "we
price this one by hand" is a sentence the form already knows how to say and a 409 the
frontend already handles. So it refuses rather than guesses when:

- a home is outside the grid (a studio, or eight bedrooms — it used to clamp to five and
  quote a different house);
- a bedroom/bathroom combination has no cell;
- an extra is priced per 100 sq ft and the request gives no area (it used to charge zero
  and the crew did the work for free);
- a commercial request ticks no service (it used to be priced as office cleaning).

Rate cards are versioned rows (`rate_cards`) — see the next section for how to change one.

## The request list

`/admin` is an inbox, so a status says where a request stands **with the client**,
and nothing else:

| | |
|---|---|
| **Nouvelle** | arrived, nobody has dealt with it |
| **Envoyée** | a price was sent — set automatically when you fill *Prix envoyé* |
| **Gagnée** / **Perdue** | how it ended |

It used to hold two more. `priced` was set on arrival whenever the engine produced
a number, which made it a second, worse copy of `computed_total_cents IS NULL` —
in the database it was exactly that: 23 rows `priced`, all 23 with a price; 8 rows
`new`, none with one. The cost was the inbox: a residential request that priced
arrived already "Chiffrée", so one nobody had opened looked like one already
handled, and "Nouvelles" listed only the requests the calculator had failed on.
`enriching` was never set by anything. Neither survives.

**Whether it priced is still on screen, and better:** the *Prix calculé* column
shows the number, or says **à chiffrer** when there is none — which is the queue
of requests needing a human price.

Adding a state later (`en cours`, say, for a job being scheduled) is one migration.
Note the enum friction under **The database** before you write it.

## The database

Six tables. `leads` → `properties` → `quote_requests` → `quotes`, plus `rate_cards`
(versioned, never edited) and `quote_photos` (reserved for the AI-enrichment project;
nothing writes it yet). Primary keys are uuid7, so they sort by creation time. All money
is integer cents. All timestamps carry a timezone.

Three rules the **database** enforces, rather than trusting whoever writes the next query:

- **One active rate card.** `uq_rate_cards_one_active`, a unique index on `is_active`
  where true. Every price on the site comes from `get_active_rate_card`, which takes the
  first row — two active cards would make the price depend on row order.
- **One quote per request.** The admin patch reads it with `.first()` and updates in
  place; a second row would duplicate the request in the listing.
- **A price is a price.** `computed_breakdown` is SQL NULL when a request got none. It
  used to hold the JSON literal `null` (SQLAlchemy's JSON default), so
  `computed_breakdown IS NOT NULL` answered yes for requests nobody could price. The
  models pass `none_as_null=True` now.

`leads`, `properties` and `quote_requests` are 1:1:1 today — every submission creates all
three. The split is deliberate and stays: a repeat client with the same condo is the whole
business model, and the join is two primary-key lookups. What is missing is the dedupe on
submit, not a flatter schema.

**Known friction:** `audience`, `property_type`, `frequency`, `request_status` and
`photo_zone` are Postgres enum types. `ALTER TYPE ... ADD VALUE` cannot be used in the same
transaction that adds it, and Alembic wraps each migration in one — so adding a status is
two migrations, or one with `op.execute("COMMIT")` before the value is used. Worth knowing
before Phase 6 adds a workflow state.

## Pricing: the rate card

> The next version of this — per-unit extras, modifiers, commercial fixtures and
> surfaces — is planned in [`docs/PRICING-V2.md`](docs/PRICING-V2.md). Read that
> before changing the grid's shape.


Every price the site shows comes from the **active rate card** row, read from the
database on each request. Changing a price does not need a deploy.

**Edit it at `/admin/tarifs`.** The screen edits a draft held in your browser
(it survives a reload); nothing reaches a visitor until you publish. Before you
publish, the right-hand panel prices three scenarios with the live card and with
your draft side by side -- that is the check that catches a decimal slip.

**Publishing INSERTs a new version.** It never rewrites a card, because
`computed_breakdown` on every stored request records the `rate_card_version` that
priced it: rewrite the card and a quote you already sent can no longer be
explained. Publishing closes the previous card (`effective_to`, `is_active=false`)
and opens the new one, in one transaction. `scripts/seed_rate_card` obeys the same
rule and is a no-op once its card exists.

**The one field edited in place is `residential_online_pricing`** -- the switch at
the top of the screen. It is not a price, so flipping it cannot change what an
old quote recomputes to, and a version nobody priced anything with would be noise
in the history. Off means residential requests stop getting a firm price and are
quoted by a person, exactly like commercial.

**An empty cell in the grid means "not offered online".** A bedroom/bathroom
combination with no price is not guessed or interpolated: the request comes in as
a lead and the form says it is chiffré à la main. Launch with the configurations
you have actually cleaned and add the rest later.

**Validation lives in `app/schemas/rate_card.py`.** The bounds are not opinions
about what to charge -- they exist so a slip (18500 typed where 1850 was meant) is
refused by the server rather than quoted to the next visitor. A base price below
the minimum visit is rejected outright, since the minimum would silently swallow it.

Endpoints, all under the admin token:

| | |
|---|---|
| `GET /api/admin/rate-card` | the active card |
| `GET /api/admin/rate-cards` | every version, with how many requests each priced |
| `POST /api/admin/rate-card/preview` | price scenarios against an unsaved draft; writes nothing |
| `POST /api/admin/rate-card` | publish a new version |
| `PATCH /api/admin/rate-card/online-pricing` | the switch |

**Adding an extra takes no code at all.** An extra lives entirely on the card:
its price, its wording in both languages, and the **unit** the price is per.

| unit | quantity comes from | example |
|---|---|---|
| `flat` | always 1 | `Intérieur du four — 30 $` |
| `each` | the visitor, via a stepper | `Vitres intérieures — 4 $ par fenêtre` |
| `per_100sqft` | the area, rounded up | `Plinthes — 14 $ par 100 pi²` |

Anything not `flat` must say what it counts (`per_fr` / `per_en`), because the
breakdown reads `Vitres intérieures × 6 par fenêtre` and without the last two
words the client has to guess. A `flat` extra must carry no unit label, for the
same reason in reverse. Both are enforced in `app/schemas/rate_card.py` and again
in `/admin/tarifs` before the round trip.

The extra's **code** (`windows`) is the stable key: stored requests and the quote
form agree on it, so it is lower-case ASCII and never changes. The wording is what
changes. Retiring an extra does not touch requests that already bought it — they
keep the wording and price from the card that quoted them, read back out of
`computed_breakdown`.

The form learns all of this from `GET /api/quotes/form-config`, which is derived
from the active card. That is the rule the whole pricing design rests on:

> **The form asks only what the active rate card can price.**

Adding a **service code**, by contrast, still means touching four places, because
nothing generates the frontend from the backend: `app/models/enums.py`
(`ServiceCode`), the seeded grid's `minutes_per_100sqft`, `SERVICE_LABELS` in
`frontend/js/admin-common.js`, and the checkboxes in `frontend/soumission.html`.
The test `test_every_service_the_form_offers_is_a_real_code` catches the last two
drifting apart; the first two are on you. Services should go the way extras did.

## The quote form

- **The property type is the only branching question.** Each tile in
  `frontend/soumission.html` carries `data-audience`, and `quote.js` derives the audience
  from it. There is no separate "residential or commercial" control, because two controls
  for one fact is how the form used to offer a commercial house.
- **`AUDIENCE_BY_PROPERTY_TYPE`** in `backend/app/models/enums.py` is the source of truth
  for that pairing. Both `QuoteRequestIn` and `PriceDraftIn` reject a mismatch with 422, so
  a stale or tampered client cannot store a row the pricing engine cannot read.
- **Every price line is written in both languages** (`label_fr` and `label_en` on `LineItem`).
  Add both when you add a line; the page renders the one matching its locale.
- **Each step is gated on itself**, and submitting re-checks all three, because the step
  pills let a visitor walk back and empty a field. Errors belong on the field; the alert box
  at the bottom of step 3 is only for a send that failed on the network.
- **Icons are inline SVG**, drawn on a 24x24 grid with `stroke-width: 1.5` and no fills, so
  they inherit `currentColor` and turn gold when their tile is selected. Check any new one at
  4x or 5x zoom: at 25px a factory easily reads as a bar chart and a traffic cone as a
  letter A. Do not replace them with generated images.

## Design rules

Everything visual comes from the tokens at the top of `frontend/css/app.css`. Adding a colour,
a size or a radius outside them is how this drifts, so don't.

- **Type scale.** Ten steps: 0.62 / 0.68 / 0.75 / 0.82 / 0.88 / 0.94 / 1 / 1.06 / 1.5 / 2.4 rem,
  plus the two `clamp()` headings. Pick the nearest step; never invent 0.93rem because 0.94
  felt slightly large. Near-identical sizes are what make a page feel subtly wrong.
- **The gold top edge marks one card picked out of a group of peers.** It is
  `var(--accent-top)`, an inset shadow (so it follows the corner radius) on a card with a navy
  border. Exactly two things use it: `.pathcard--lead` and `.card--feature`. Photos and the
  `.summary` price panel deliberately have none -- a panel with no peers has nothing to stand
  out from, and the accent stops meaning anything if it decorates everything.
- **Colours** are tokens only. The five remaining literal hexes are the admin status tints
  (`#eef4ff`, `#fff6e5`, `#ecfdf3`, `#fef3f2`, `#fecdc9`), each semantic and used once.
- **Transitions** are `var(--t)` (0.15s ease).
- **Tap targets** stay at 32px or more on small screens; footer links get `padding-block` for
  this reason.
- English pages are generated -- edit the French page, then `python3 frontend/build_en.py`.

## What is still a placeholder

- **The rate grid** — every number in `scripts/seed_rate_card.py` is invented. Replace them
  with Proline's real figures before any price is shown publicly. You no longer edit that
  file to do it: put the real numbers in at `/admin/tarifs` and publish. Until then, the
  honest option is the switch at the top of that screen, which stops the site quoting
  residential prices at all.
- **Admin auth** is one username and password from the environment, with a signed 12-hour
  token. Fine for one person; replace with per-user accounts before anyone else gets access.
  Local defaults: `admin` / `proline`.
- **Photos.** Eight are in place (`frontend/img/`): `hero-residential`, `hero-commercial`,
  `floor-waxing`, `sanitaires`, `post-construction`, `equipe`, and the `decapage-avant` /
  `decapage-apres` pair on the home page. None are Proline's own work. `equipe` shows two
  people who are not the real crew, so replace that one first; the before/after pair is not a
  Proline job either, and a real one from your own contract would carry more weight.
  Sizes are cut to match each container exactly, so `object-fit: cover` discards almost
  nothing: heroes are square (1400/800) because the hero box is near-square on desktop,
  split-section photos are 16:10 (1600/800), the before/after pair is 4:3 (1200/900/600), and
  the wide strip on `/commercial` is 21:9 (2240/1800/900). All JPEG q82, wired with `srcset`.
  Every photo is white-balanced to roughly the same warmth so the palette stays consistent;
  the two `decapage-*` halves share one identical correction so the comparison stays honest.
  `hero-residential.jpg`, `hero-commercial.jpg` and their `-800` variants are superseded and
  unreferenced -- safe to delete (about 500 KB).
- **The logo** is a screenshot from Facebook, downscaled here to 256 px (the 1050 px original
  is kept beside it as `logo-original.png`). Swap in the real file when you have it.
- **The crew promises** in the `#equipe` section on the home page (uniforms, instructions on
  file, planned cover, a supervisor reachable directly) are written as commitments. Confirm
  each one is true before the site goes live.
- **Review counts and the email address** in the HTML, marked `[LIKE THIS]`.
- **English pages** are generated: edit the French page, then run `python3 frontend/build_en.py`.
- **Notifications** are logged, not sent, until `SMTP_HOST` and `NOTIFY_EMAIL_TO` (or the
  Twilio keys) are set and `ENVIRONMENT` is not `local`.

## Deploy

One **Lightsail instance in `ca-central-1` (Montreal)** runs everything — app,
Postgres, nginx, certbot and a daily photo-retention sweep as containers. **$12/month.** The AWS side is Pulumi;
see `infra/pulumi/` and `infra/DEPLOY.md`. nginx terminates TLS and proxies to the
app; certbot renews the certificate and nginx reloads on a timer to pick it up, so
there is no cron and nothing to remember. The first certificate is the one manual
step — `infra/nginx/init-letsencrypt.sh`, run once, and its header explains why.

There is no registry and no CI: the image is **built on the box** from the root
`Dockerfile`, which is why the repo is cloned there rather than two files copied
up. The full sequence — Pulumi, DNS at GoDaddy, the SES production request, the
secret file — is `infra/DEPLOY.md`, in order. **`infra/DNS.md` documents every
record in the zone and which system owns it** — read that before editing anything
at GoDaddy, because two mail systems share this domain (Microsoft 365 for
mailboxes, Amazon SES for quote emails) and they share the SPF and DMARC records.

Once it is running, a deploy is:

```bash
# on the box
cd /srv/proline/src && git pull
docker compose -f infra/docker-compose.prod.yml up -d --build
```

**Why one box rather than a managed database.** Every platform priced for this
charges $15–20 for Postgres and another $18 for TLS and routing, and at this
scale both are containers on a machine you already rent — the $15 database tiers
are single instances too, so a host failure means restoring from backup either
way. What $12 buys is the same recovery story — **provided the recovery point is
real**, which is the next section.

Montreal is the region because the form collects names, phone numbers, emails and
addresses of Quebec residents, and Law 25 carries obligations about personal
information held outside the province. **Confirm that with someone qualified
before launch** — nothing here is legal advice.

### The recovery point

**The instance's daily whole-disk snapshot is the only backup.** One recovery
point per day, and restoring creates a *new* instance — so recovery also means
re-attaching the static IP, which is the step that gets forgotten under pressure.
Verify in the console that snapshots are actually being taken; an automatic
snapshot nobody checked is the same as no snapshot.

The database is in the `pgdata` Docker volume on that same disk, so the snapshot
does cover it — there is no second, database-level backup, and nothing in the app
monitors one.

There is deliberately **no nightly dump to a bucket**. A `pg_dump` to a Lightsail
bucket, its container, the Pulumi bucket and the `/admin` staleness banner all
existed and were removed together; `git log -- infra/backup` is where to find them
if a sub-daily recovery point ever becomes worth the moving parts.

### Before the first deploy

In `/srv/proline/.env`:

- `ENVIRONMENT=production` — this makes the app **refuse to start** on a default
  `ADMIN_PASSWORD` or `SECRET_KEY`. That is deliberate.
- `ADMIN_PASSWORD`, `SECRET_KEY` — real values. `proline` is in this public repo.
- `DATABASE_URL=postgresql+asyncpg://proline:<pw>@db:5432/proline`. Any libpq URL
  works too: `normalise_database_url` in `app/core/config.py` converts the scheme
  and translates `sslmode`, so a managed provider's string can be pasted as-is if
  you ever move off the box.
- `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `MAIL_FROM`, `MAIL_REPLY_TO` and
  `NOTIFY_EMAIL_TO` — or the Twilio keys. **Until one pair is set, a lead is
  written to the database and nobody is told about it.**

And `/srv/proline/db_password`, a single line, mounted as a Docker secret.
