# Pokémon Data Analytics Platform — developer task runner.
# All Python tooling is driven through `uv`. Install it from https://docs.astral.sh/uv/.

# Default Docker Compose environment (dev|prod) — override: `make up ENV=prod`.
ENV ?= dev
# All config lives in .env (see .env.example); --env-file makes it explicit.
COMPOSE = docker compose -f docker/docker-compose.$(ENV).yml --env-file .env

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

airflow-pins: ## Print uv.lock versions for the deps pinned in docker/Dockerfile.airflow
	@uv run python -c "import tomllib; d=tomllib.load(open('uv.lock','rb')); \
	pkgs={'pandas','numpy','psycopg2-binary','httpx','tenacity','python-dotenv', \
	'apache-airflow-providers-standard','apache-airflow-providers-postgres', \
	'apache-airflow-providers-common-sql','apache-airflow-providers-fab'}; \
	[print(f\"{p['name']}=={p['version']}\") for p in sorted(d['package'], key=lambda x: x['name']) if p['name'] in pkgs]"

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

# Create .env from the template on first use, generating fresh Airflow secrets
# (so no real secret is ever committed and each checkout gets unique keys).
_env:
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		fk=$$(python3 -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"); \
		js=$$(python3 -c "import secrets;print(secrets.token_hex(32))"); \
		sed -i.bak "s|^AIRFLOW_FERNET_KEY=.*|AIRFLOW_FERNET_KEY=$$fk|; s|^AIRFLOW_JWT_SECRET=.*|AIRFLOW_JWT_SECRET=$$js|" .env && rm -f .env.bak; \
		echo "Created .env from .env.example with freshly generated Airflow secrets."; \
	fi

start: _check-env _env ## Build & start the full stack, then print access URLs (was start.sh)
	@echo "Starting Pokémon Data Analytics Platform in $(ENV) environment..."
	$(COMPOSE) up -d --build
	@echo ""
	@echo "Services are starting. Access points:"
	@echo "  - API:               http://localhost:$${APP_PORT:-8000}"
	@echo "  - Airflow UI:        http://localhost:$${AIRFLOW_PORT:-8080}"
	@if [ "$(ENV)" = "prod" ]; then echo "  - Streamlit:         http://localhost:$${STREAMLIT_PORT:-8501}"; fi
	@echo ""
	@echo "Tail logs with:  make logs ENV=$(ENV)"

stop: _check-env _env ## Stop the stack and remove containers (was stop.sh)
	@echo "Stopping Pokémon Data Platform services..."
	$(COMPOSE) down

up: start ## Alias for `make start`

down: stop ## Alias for `make stop`

logs: _check-env _env ## Tail stack logs
	$(COMPOSE) logs -f

ps: _check-env _env ## Show running services
	$(COMPOSE) ps

# --- Housekeeping ----------------------------------------------------------

clean: ## Remove caches, build artifacts, and the venv
	rm -rf .venv .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage build dist *.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
