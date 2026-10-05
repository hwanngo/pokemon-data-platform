# Pokémon Data Analytics Platform — developer task runner.
# All Python tooling is driven through `uv`. Install it from https://docs.astral.sh/uv/.

# Default Docker Compose environment (dev|prod) — override: `make up ENV=prod`.
ENV ?= dev
# Each environment has its own configuration and Compose project/volumes.
ENV_FILE = .env.$(ENV)
COMPOSE = docker compose -f docker/docker-compose.$(ENV).yml --env-file $(ENV_FILE)

.DEFAULT_GOAL := help

.PHONY: help install sync lock upgrade airflow-pins secrets-scan hooks run api dashboard fetch analytics \
        test cov lint format format-check typecheck check \
        start stop up down logs ps clean _check-env _env

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# --- Environment -----------------------------------------------------------

install: ## Create the venv and install all deps (dev + prod + airflow)
	uv sync --all-extras

sync: ## Sync the venv to uv.lock (default deps + dev group)
	uv sync

lock: ## Re-resolve dependencies and update uv.lock
	uv lock

upgrade: ## Bump every dependency to the latest compatible version
	uv lock --upgrade
	python3 docker/sync_airflow_pins.py
	uv sync --all-extras --locked

airflow-pins: ## Check the Airflow image tag and requirements against uv.lock
	python3 docker/sync_airflow_pins.py --check

# --- Run the app -----------------------------------------------------------

api: ## Run the FastAPI server with autoreload
	uv run uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

dashboard: ## Run the Streamlit dashboard
	uv run --extra prod streamlit run src/analytics/dashboard.py

fetch: ## Fetch + load all PokéAPI data (override: make fetch ARGS="--pokemon")
	uv run python -m src.main fetch $(or $(ARGS),--all)

analytics: ## Run analytics over the loaded data
	uv run python -m src.main analytics

run: api ## Alias for `make api`

# --- Quality ---------------------------------------------------------------

test: ## Run the test suite
	uv run pytest

cov: ## Run tests with coverage report
	uv run pytest --cov=src --cov-report=term-missing

lint: ## Lint with ruff (incl. security rules)
	uv run ruff check src tests

format: ## Auto-format and apply lint fixes with ruff
	uv run ruff check --fix src tests
	uv run ruff format src tests

format-check: ## Check formatting/lint without modifying files
	uv run ruff format --check src tests
	uv run ruff check src tests

typecheck: ## Static type-check with mypy
	uv run mypy src

secrets-scan: ## Scan the repo for committed secrets (gitleaks via pre-commit)
	uv run pre-commit run gitleaks --all-files

hooks: ## Install the git pre-commit hooks (gitleaks, ruff, hygiene)
	uv run pre-commit install

check: format-check lint typecheck test secrets-scan ## Run all quality gates

# --- Docker (replaces the old start.sh / stop.sh) --------------------------

# Guard: ENV must be dev or prod.
_check-env:
	@if [ "$(ENV)" != "dev" ] && [ "$(ENV)" != "prod" ]; then \
		echo "Error: invalid ENV '$(ENV)'. Use 'dev' or 'prod' (e.g. make start ENV=prod)."; \
		exit 1; \
	fi

# Development secrets are generated once. Production configuration is explicit.
_env:
	@python3 docker/prepare_env.py $(ENV)

start: _check-env _env ## Build & start the full stack, then print access URLs (was start.sh)
	@echo "Starting Pokémon Data Analytics Platform in $(ENV) environment..."
	$(COMPOSE) up -d --build
	@echo ""
	@echo "Services are starting. Access points:"
	@app_port=$$(sed -n 's/^APP_PORT=//p' $(ENV_FILE) | tail -1); echo "  - API:               http://localhost:$${app_port:-8000}"
	@airflow_port=$$(sed -n 's/^AIRFLOW_PORT=//p' $(ENV_FILE) | tail -1); echo "  - Airflow UI:        http://localhost:$${airflow_port:-8080}"
	@if [ "$(ENV)" = "prod" ]; then streamlit_port=$$(sed -n 's/^STREAMLIT_PORT=//p' $(ENV_FILE) | tail -1); echo "  - Streamlit:         http://localhost:$${streamlit_port:-8501}"; fi
	@echo ""
	@echo "Tail logs with:  make logs ENV=$(ENV)"

stop: _check-env ## Stop the stack and remove containers (was stop.sh)
	@echo "Stopping Pokémon Data Platform services..."
	$(COMPOSE) down

up: start ## Alias for `make start`

down: stop ## Alias for `make stop`

logs: _check-env ## Tail stack logs
	$(COMPOSE) logs -f

ps: _check-env ## Show running services
	$(COMPOSE) ps

# --- Housekeeping ----------------------------------------------------------

clean: ## Remove caches, build artifacts, and the venv
	rm -rf .venv .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage build dist *.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
