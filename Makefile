# Proline — everyday commands. `make dev` is the one that matters.
COMPOSE := docker compose -f infra/docker-compose.yml

.PHONY: dev up down logs rebuild seed shell psql test lint

dev: ## Postgres + schema + rate card + site on http://localhost:8000
	$(COMPOSE) up --build

up: ## Same, in the background
	$(COMPOSE) up --build -d

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

lint:
	cd backend && ruff check app tests scripts
