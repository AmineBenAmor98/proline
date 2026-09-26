# Proline — everyday commands. `make dev` is the one that matters.
COMPOSE := docker compose -p proline -f infra/docker-compose.yml

.PHONY: dev up down reset logs rebuild seed shell psql test test-form lint

dev: ## Postgres + schema + rate card + site on http://localhost:8000
	$(COMPOSE) up --build --remove-orphans

up: ## Same, in the background
	$(COMPOSE) up --build -d --remove-orphans

down: ## Stop everything (keeps the database volume)
	$(COMPOSE) down

reset: ## Stop and delete the database volume
	$(COMPOSE) down -v

logs:
	$(COMPOSE) logs -f app

rebuild: ## After changing requirements.txt
	$(COMPOSE) build --no-cache app

seed: ## Re-apply the rate card
	$(COMPOSE) exec app python -m scripts.seed_rate_card

shell:
	$(COMPOSE) exec app sh

psql:
	$(COMPOSE) exec db psql -U proline -d proline

test: ## Full suite inside the container, against the compose database
	$(COMPOSE) exec app sh -c "pip install -q -r requirements-dev.txt && pytest -q"

# The quote form in a real DOM. The Python suite is green on bugs this catches:
# a 422 the form showed as "sending failed, call us", a photo block that never
# appeared. Runs on the host, needs nothing running.
test-form: ## The quote form, both languages, in jsdom
	npm i --no-save --silent jsdom
	node frontend/test/check_form.js
	node frontend/test/check_form.js en/soumission.html


lint: ## Ruff, configured in backend/pyproject.toml
	cd backend && ruff check .
