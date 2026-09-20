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

- **The rate grid** in `scripts/seed_rate_card.py` — every number is invented. Replace it
  with Proline's real figures before any price is shown publicly.
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
- **Notifications** are logged, not sent, until `RESEND_API_KEY` and the Twilio keys are set
  and `ENVIRONMENT` is not `local`.

## Deploy

```bash
fly deploy --config infra/fly.toml     # Toronto (yyz), the only Canadian region on Fly
```

Database and photo storage live in Supabase `ca-central-1` (Montreal), so client data stays
in Canada end to end.
