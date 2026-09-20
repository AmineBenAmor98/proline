# Proline Cleaning Solutions

Quote capture, pricing and admin for Proline Cleaning Solutions (Montreal).
One FastAPI process serves the API **and** the site — the same shape as kfz.

```
backend/     FastAPI: API, pricing engine, models, migrations
frontend/    static HTML, CSS and vanilla JS (FR + EN + /admin)
infra/       docker-compose for local Postgres, fly.toml for Toronto
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
| `/docs` | OpenAPI |

## Tests

```bash
cd backend
pytest                  # pricing engine + pages, no database needed
DATABASE_URL=postgresql+asyncpg://proline:proline@localhost:5432/proline pytest
ruff check app tests scripts
```

The API tests skip themselves when `DATABASE_URL` is unset, so the suite still runs on a
laptop with no Postgres.

## How pricing works

`backend/app/pricing/` is pure functions: inputs in, a breakdown out. No database, no clock,
no network, so its tests need nothing running.

- **Residential** — a flat grid by bedrooms and bathrooms, plus an area surcharge, priced
  extras and a recurring discount. Returned to the visitor as a firm price.
- **Commercial** — minutes of work per 100 sq ft per service, times the hourly rate, plus
  restrooms, night access and travel. Computed and stored, **never shown**: the client is
  told a written quote arrives within 24 h, and a human reviews the number first.

Rate cards are versioned rows (`rate_cards`). A price change creates a new row; old quotes
still recompute to what the client was given.

## What is still a placeholder

- **The rate grid** in `scripts/seed_rate_card.py` — every number is invented. Replace it
  with Proline's real figures before any price is shown publicly.
- **Admin auth** is one username and password from the environment, with a signed 12-hour
  token. Fine for one person; replace with per-user accounts before anyone else gets access.
  Local defaults: `admin` / `proline`.
- **Photos, review counts, email address** in the HTML, marked `[LIKE THIS]`. The logo is a
  350 px screenshot from Facebook; swap in the original file.
- **English pages** are generated: edit the French page, then run `python3 frontend/build_en.py`.
- **Notifications** are logged, not sent, until `RESEND_API_KEY` and the Twilio keys are set
  and `ENVIRONMENT` is not `local`.

## Deploy

```bash
fly deploy --config infra/fly.toml     # Toronto (yyz), the only Canadian region on Fly
```

Database and photo storage live in Supabase `ca-central-1` (Montreal), so client data stays
in Canada end to end.
