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
- **Concurrent, rate-limited, cached ingestion** — a thread pool fetches under a shared rate limiter, with retries and on-disk JSON caching governed by the mirror refresh policy.
- **REST API** (FastAPI) — query Pokémon and run analytics endpoints.
- **Interactive dashboard** (Streamlit) — stats rankings, type distribution, and the type-effectiveness matrix.
- **Reproducible Python environments** — dependencies are pinned in `uv.lock`; Docker images require separate build validation.

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
make logs             # tail logs
make stop             # stop everything
```

`make start` creates `.env.dev` with fresh database, Airflow and administrator
credentials. The host ports bind to loopback. The API is available at
`http://localhost:8000/docs`; Airflow is at `http://localhost:8080`.

For production, create `.env.prod` from `.env.example`, fill every blank secret
with a unique value, set the host ports and Airflow base URL, then run
`make start ENV=prod`. Passwords must have at least 20 URL-safe characters;
the Fernet key must decode to 32 bytes and the JWT secret must have at least
32 characters. Production never generates
credentials implicitly. The supplied host ports bind to loopback; configure
an authenticated TLS reverse proxy if remote access is required.

Services:

| Service   | Local URL                     |
|-----------|-------------------------|
| REST API  | http://localhost:8000   |
| Airflow   | http://localhost:8080   |
| Streamlit | http://localhost:8501 (prod only) |

> PostgreSQL initializes the schema on a new volume. `app-migrate` applies
> versioned application migrations on every startup before app and Airflow tasks.
> Airflow migrates its separate metadata database during `airflow-init`.

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
A reachable PostgreSQL is required. Set `DATABASE_URL` explicitly or export all
of `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB` (plus optional
`POSTGRES_HOST`/`POSTGRES_PORT`). Compose uses its own service-network URLs;
local Python does not infer credentials from `.env.dev`.

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
> faster. Raw responses are cached as readable JSON in environment-specific
> `cache/` directories; scheduled runs refresh source data under the mirror's
> freshness policy. The `pokeapi_mirror` Airflow DAG runs weekly (one task per
> resource, dependency-ordered). Query the tail with JSONB, e.g.
> `SELECT data->>'flavor_text' FROM api_resource WHERE resource_type='berry-flavor'`.

### REST API

| Method & path                              | Description                              |
|--------------------------------------------|------------------------------------------|
| `GET /`                                    | Welcome message                          |
| `GET /health/ready`                        | Database-backed readiness                |
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
| `upgrade`       | Re-resolve and sync all extras; export locked Airflow requirements |
| `airflow-pins`  | Check the Airflow image against `uv.lock`              |
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

Compose uses separate `.env.dev` and `.env.prod` files. Development bootstrap
creates `.env.dev` automatically. Production configuration is explicit:

```bash
cp .env.example .env.prod
# Fill POSTGRES_PASSWORD, APP_READER_PASSWORD, APP_WRITER_PASSWORD,
# AIRFLOW_DB_PASSWORD, AIRFLOW_FERNET_KEY, AIRFLOW_JWT_SECRET,
# AIRFLOW_ADMIN_PASSWORD with unique secrets before `make start ENV=prod`.
```

| Variable | Default | Purpose |
|---|---|---|
| `APP_PORT` / `AIRFLOW_PORT` / `STREAMLIT_PORT` | `8000` / `8080` / `8501` | Host ports (change to avoid conflicts) |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `postgres` / required / `pokemon_data` | Migration owner; never used by public readers |
| `APP_READER_PASSWORD` / `APP_WRITER_PASSWORD` | required | Separate read and ingestion roles |
| `AIRFLOW_DB_PASSWORD` | required | Role for separate Airflow metadata database |
| `API_BASE_URL` / `API_RATE_LIMIT` / `API_CONCURRENCY` / `LOG_LEVEL` | PokéAPI / `20` / `8` / `INFO` | Ingestion (rate + concurrent fetch) + app |
| `AIRFLOW_FERNET_KEY` / `AIRFLOW_JWT_SECRET` | generated for dev; required for prod | Airflow encryption + API auth |
| `AIRFLOW_ADMIN_USERNAME` / `AIRFLOW_ADMIN_PASSWORD` / `AIRFLOW_ADMIN_EMAIL` | `admin` / required / … | Airflow admin user |
| `MIRROR_POOL_SLOTS` | `1` | Concurrent Airflow mirror tasks |
| `DATABASE_URL` | unset for local Python | Full local connection URL; optional if all POSTGRES_* values are exported |

Passwords used in Compose connection URLs must contain at least 20 URL-safe
characters (`A-Z`, `a-z`, `0-9`, `.`, `_`, `~`, `-`). `make start` validates this
before Docker runs. Values in the environment may override the file during
Compose interpolation; review your shell environment when troubleshooting.

`API_RATE_LIMIT` is enforced by each ingestion process. The default
`MIRROR_POOL_SLOTS=1` keeps the scheduled mirror within that request-per-minute
budget. Raising pool slots can multiply the total request rate; divide
`API_RATE_LIMIT` across concurrent tasks if you increase the pool size.

The repository ignores both env files and excludes them from Docker build
contexts. For a production Fernet key, use
`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
For other secrets, `python -c "import secrets; print(secrets.token_urlsafe(36))"`
produces a suitable value. Store secrets in a restricted manager for a real
deployment; Compose environment variables are visible to operators with Docker
access.

Dev and prod have different Compose project names, PostgreSQL/log volumes and
cache paths. Changing `ENV` does not migrate data between them. Before upgrades,
back up both the application database and Airflow metadata with `pg_dump`, then
verify restore into a disposable volume. Keep the previous image/lockfile for
rollback, apply application migrations with `app-migrate`, and validate
`/health/ready` plus Airflow's `/api/v2/monitor/health` before reopening ingress.
Do not use `docker compose down -v` on data you intend to keep.

---

## Testing & quality

```bash
make test         # pytest
make cov          # pytest with coverage report
make check        # format-check, lint, typecheck, and tests
```

CI also builds Python distributions and both Docker images. Its application
image check confirms a dummy local `.env` is absent. An opt-in CI job tests
fresh and legacy-schema migrations plus reader/writer grants against a disposable
PostgreSQL 18 service. The application builder and PostgreSQL images use
reviewed digest references; update those deliberately when patching images.
A successful image build does not replace a full Airflow startup and restore test.

The locked Airflow release is 3.3.2, which resolves the advisories recorded in
`PROJECT_AUDIT.md` (AUDIT-DEP-001). Airflow 3.3 caps FastAPI below 0.137, so
the shared lockfile holds FastAPI on the newest 0.136.x release. Airflow
upgrades must move the lockfile, Airflow image and provider pins together and
pass migration, DAG import and role-based smoke tests. On a host with
package-registry access, run `make upgrade`, then
`make check` and the Docker/CI checks. The upgrade target now derives the
Airflow image version and complete hashed requirements from the resolved
lockfile; CI rejects drift between them. Review the resolved packages and image
before deployment.

---

## License

[MIT](LICENSE)
