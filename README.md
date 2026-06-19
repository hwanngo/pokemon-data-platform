# Pokémon Data Analytics Platform

An end-to-end data platform that ingests Pokémon data from [PokéAPI](https://pokeapi.co/),
transforms and loads it into PostgreSQL, orchestrates the pipeline with Apache Airflow,
and serves it through a FastAPI REST API and a Streamlit dashboard.

**Stack:** Python 3.14 · [uv](https://docs.astral.sh/uv/) · FastAPI · SQLAlchemy 2.0 ·
PostgreSQL · Apache Airflow 3 · Streamlit + Plotly · httpx · Docker

---

## Features

- **ETL pipeline** — extract from PokéAPI, transform to a normalized schema, load into PostgreSQL.
- **Apache Airflow orchestration** — one config-driven DAG (`pokeapi_mirror`) ingests every resource in dependency order.
- **Concurrent, rate-limited, cached ingestion** — a thread pool saturates the network under a thread-safe rate limiter, with tenacity retries and readable on-disk JSON caching (re-runs hit the cache, not the API).
- **REST API** (FastAPI) — query Pokémon and run analytics endpoints.
- **Interactive dashboard** (Streamlit) — stats rankings, type distribution, and the type-effectiveness matrix.
- **Reproducible environments** — every dependency pinned in `uv.lock`; one-command Docker stack.

---

## Architecture

```
PokéAPI ──▶ generic mirror engine ──────────────────────▶ PostgreSQL ──▶ analytics
            (registry → concurrent fetch → transform → upsert)         ├─▶ FastAPI  (REST)
                                                                       └─▶ Streamlit (dashboard)
                       one config-driven Airflow DAG (pokeapi_mirror)
```

A single engine ingests every resource: simple ones map to one table, the core
entities (pokemon/type/ability/move) fan a response out to several tables.

Data is loaded **parents first** so foreign keys stay valid:
`types → abilities → moves → pokemon` (and the Pokémon associations).

---

## Project structure

```
pokemon-data-platform/
├── src/
│   ├── ingestion/        # mirror engine: resource registry + concurrent fetcher + API client
│   ├── transformation/   # Raw API → DB-shaped dict transformers
│   ├── loading/          # atomic upsert loader (resource_loader)
│   ├── models/           # SQLAlchemy ORM models
│   ├── analytics/        # Stats/type analyzers + Streamlit dashboard
│   ├── dags/             # Airflow DAG definitions
│   └── main.py           # FastAPI app + CLI entry point
├── database/
│   ├── initdb/           # schema.sql (source of truth) + init.sh
│   └── migrations/       # Versioned SQL migrations
├── docker/               # Dockerfiles + dev/prod compose files
├── tests/                # pytest suite
├── pyproject.toml        # Project metadata & dependencies (uv)
├── uv.lock               # Pinned, reproducible lockfile
└── Makefile              # Developer task runner
```

---

## Prerequisites

- **Docker** and **Docker Compose** (for the full stack)
- **Python 3.14** and **[uv](https://docs.astral.sh/uv/)** (for local development)

Install uv:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## Quick start (Docker)

```bash
make start            # build + start the dev stack (ENV=dev by default)
make start ENV=prod   # production compose
make logs             # tail logs
make stop             # stop everything
```

Services:

| Service   | URL                     |
|-----------|-------------------------|
| REST API  | http://localhost:8000   |
| Airflow   | http://localhost:8080   |
| Streamlit | http://localhost:8501 (prod) |

> The database schema is created automatically from `database/initdb/schema.sql`
> on first Postgres startup.

---

## Local development (uv)

```bash
make install          # create .venv and install all deps (or: uv sync --all-extras)
make api              # run the FastAPI server with autoreload
make dashboard        # run the Streamlit dashboard
make test             # run the test suite
make check            # format-check + lint + typecheck + test
```

`make install` creates a `.venv/`; run any command inside it with `uv run <cmd>`.
A reachable PostgreSQL is required — point `DATABASE_URL` at one (see
[Configuration](#configuration)) or use the Docker `postgres` service.

---

## Usage

### CLI

The pipeline is driven through `src.main`:

```bash
# Load the core analytics entities (type, ability, move, pokemon) via the engine.
# FK parents are loaded first automatically.
make fetch                          # uv run python -m src.main fetch --all
uv run python -m src.main fetch --types       # a single core entity
uv run python -m src.main fetch --pokemon     # pokemon (+ its FK deps)

# Run analytics
make analytics                      # uv run python -m src.main analytics
uv run python -m src.main analytics --type stats|types|all
```

> `fetch` is a convenience alias over the mirror engine for the analytics subset;
> `mirror --all` ingests everything (48 resources). There is one ingestion engine
> and one DAG (`pokeapi_mirror`).

### PokéAPI mirror

A generic, config-driven engine mirrors the rest of PokéAPI (Berries, Contests,
Encounters, Evolution, Games, Items, Locations, Machines, plus Move/Pokémon
lookups) — 48 resources in `src/ingestion/resources.py`, including the core
`pokemon/type/ability/move` entities (which fan a single response out to several
tables). High-value resources get
relational tables; the long tail lands in a single `api_resource` JSONB table.

```bash
uv run python -m src.main mirror --all                 # mirror everything
uv run python -m src.main mirror --only nature,berry   # a subset (FK deps auto-included)
```

> A full mirror is **thousands** of requests. Detail records are fetched
> **concurrently** (a thread pool, `API_CONCURRENCY`, default 8) under a
> thread-safe rate limiter (`API_RATE_LIMIT`), so raising both makes it much
> faster. Raw responses are cached as readable JSON in `./cache`
> (`<resource>__<id>.json`), so re-runs re-ingest from disk with no repeated API
> calls. The `pokeapi_mirror` Airflow DAG runs it weekly (one task per resource,
> dependency-ordered). Query the tail with JSONB, e.g.
> `SELECT data->>'flavor_text' FROM api_resource WHERE resource_type='berry-flavor'`.

### REST API

| Method & path                              | Description                              |
|--------------------------------------------|------------------------------------------|
| `GET /`                                    | Health/welcome message                   |
| `GET /pokemon?skip=&limit=`                | List Pokémon with their types            |
| `GET /pokemon/{id}`                        | One Pokémon with stats and types         |
| `GET /analytics/top-pokemon?limit=`        | Top Pokémon by total base stats          |
| `GET /analytics/type-distribution`         | Count of Pokémon per type                |
| `GET /analytics/pokemon/{id}/counters`     | Recommended counter types                |

Interactive docs are served at `http://localhost:8000/docs`.

---

## Data model

**Core ETL** — nine tables, kept in sync between `src/models/` and `database/initdb/schema.sql`:

| Table                | Purpose                                                        |
|----------------------|----------------------------------------------------------------|
| `pokemon`            | Core Pokémon (id, name, height, weight, base XP, is_default…)  |
| `pokemon_stats`      | Per-Pokémon base stats (HP, Attack, …)                         |
| `types`              | Pokémon types                                                  |
| `pokemon_types`      | Pokémon ↔ type, with slot                                      |
| `type_effectiveness` | Attacking→defending multipliers (0.0 / 0.5 / 2.0; 1.0 implied) |
| `abilities`          | Ability definitions (effect text)                              |
| `pokemon_abilities`  | Pokémon ↔ ability, with hidden flag and slot                  |
| `moves`              | Move definitions (power, pp, accuracy, type, damage class)     |
| `pokemon_moves`      | Pokémon ↔ move, with level and learn method                    |

> Type effectiveness stores only non-neutral relations; an **absent** row means
> neutral (×1.0).

**Mirror** (`src/models/mirror.py` + `api_resource`) — 15 relational tables for
high-value resources (`regions, generations, version_groups, versions, pokedexes,
item_categories, items, berries, machines, locations, location_areas,
pokemon_species, egg_groups, natures, contest_types`) plus the `api_resource`
JSONB table holding every other mirrored resource.

---

## Make targets

Run `make help` for the full list. Highlights:

| Target          | Description                                            |
|-----------------|--------------------------------------------------------|
| `install`       | Create the venv and install all deps                   |
| `sync` / `lock` | Sync to / regenerate `uv.lock`                         |
| `upgrade`       | Bump every dependency to the latest compatible version |
| `api`           | Run the FastAPI server                                  |
| `dashboard`     | Run the Streamlit dashboard                             |
| `fetch`         | Fetch + load all PokéAPI data                          |
| `analytics`     | Run analytics over the loaded data                     |
| `test` / `cov`  | Run tests (with coverage)                               |
| `lint` / `format` / `typecheck` | ruff check / ruff format+fix / mypy |
| `check`         | All quality gates                                      |
| `start` / `stop`| Start / stop the Docker stack (`ENV=dev\|prod`)        |
| `logs` / `ps`   | Tail logs / list services                              |
| `clean`         | Remove caches, build artifacts, and the venv           |

---

## Configuration

All configuration lives in a single **`.env`** file at the repo root. Copy the
template and edit as needed (`make start` auto-creates `.env` from it on first run):

```bash
cp .env.example .env
```

| Variable | Default | Purpose |
|---|---|---|
| `APP_PORT` / `AIRFLOW_PORT` / `STREAMLIT_PORT` | `8000` / `8080` / `8501` | Host ports (change to avoid conflicts) |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `postgres` / `postgres` / `pokemon_data` | Database credentials |
| `API_BASE_URL` / `API_RATE_LIMIT` / `API_CONCURRENCY` / `LOG_LEVEL` | PokéAPI / `20` / `8` / `INFO` | Ingestion (rate + concurrent fetch) + app |
| `AIRFLOW_FERNET_KEY` / `AIRFLOW_JWT_SECRET` | generated by `make _env` | Airflow encryption + api-server auth (no in-repo default) |
| `AIRFLOW_ADMIN_USERNAME` / `AIRFLOW_ADMIN_PASSWORD` / `AIRFLOW_ADMIN_EMAIL` | `admin` / `admin` / … | Airflow admin user |

`DATABASE_URL` and Airflow's connection string are composed from the `POSTGRES_*`
values, so you only set the credentials once. Shell variables override `.env`
(e.g. `APP_PORT=8001 make start`).

> **Security:** `.env` is gitignored and there are **no secret defaults in the
> compose files** — `make _env` generates a fresh Fernet key + JWT secret into
> `.env` on first run. Both dev and prod compose require `AIRFLOW_FERNET_KEY` and
> `AIRFLOW_JWT_SECRET` (and prod additionally requires `AIRFLOW_ADMIN_PASSWORD` /
> `POSTGRES_PASSWORD`) — they fail loudly if missing. Generate a Fernet key
> manually via `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.

---

## Testing & quality

```bash
make test         # pytest
make cov          # pytest with coverage report
make check        # format-check, lint, typecheck, and tests
```

---

## License

MIT
