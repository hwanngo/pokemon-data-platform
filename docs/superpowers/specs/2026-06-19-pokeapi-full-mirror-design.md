# PokéAPI Full Mirror — Design

**Date:** 2026-06-19
**Status:** Approved (owner delegated decisions; proxy-brain authored)

## Goal
Ingest a faithful local mirror of all 8 remaining PokéAPI v2 categories — Berries,
Contests, Encounters, Evolution, Games, Items, Locations, Machines — alongside the
existing Pokémon/Types/Abilities/Moves pipelines. ~40 endpoints.

## Approach: generic, config-driven ingestion engine
Replace per-entity code with one engine driven by a resource **registry**. Adding a
resource = one registry entry (+ a model for relational ones). The existing
`pokemon`/`types`/`abilities`/`moves` pipelines stay untouched (bespoke junction
logic, already tested); the engine is purely additive for the new categories.

### Storage: hybrid (relational core + JSONB tail)
- **`api_resource`** — the JSONB tail; faithful mirror of everything not promoted:
  `(resource_type TEXT, id INT, name TEXT, data JSONB, fetched_at TIMESTAMPTZ,
  PRIMARY KEY (resource_type, id))`, GIN index on `data`, index on `(resource_type, name)`.
- **Relational core (~15 tables)** for heavily-referenced / high-value resources:
  `region, generation, version_group, version, pokedex, item_category, item, berry,
  machine, location, location_area, pokemon_species, egg_group, nature, contest_type`.
  Each gets key scalar columns + FK ids; nested detail stays in JSON (promote later by
  adding a model + flipping the registry entry's `mode`).
- Everything else in the 8 categories → `api_resource` (berry_firmness/flavor,
  item_attribute/pocket/fling_effect, evolution_chain (tree), evolution_trigger,
  encounter_*, contest_effect/super_contest_effect, move_* lookups, growth_rate,
  pokemon_color/shape/habitat, stat, gender, characteristic, pokeathlon_stat, …).

## Components (`src/ingestion/` + `src/loading/`)
- **`ResourceSpec`** — `{name, mode: "relational"|"jsonb", model?, transform?, depends_on: list}`.
- **`resources.py`** — the registry (list of ResourceSpec) + a topological-sort helper.
- **`ResourceFetcher`** — pages any `/{name}?limit=&offset=` list and follows result
  URLs (reuses the non-contiguous-id pattern already used for abilities/moves).
- **Generic transform** — JSONB: `{resource_type, id, name, data}`; relational: the
  spec's `transform(raw) -> column dict`.
- **`ResourceLoader`** — batched upsert into the target (real table for relational,
  `api_resource` for JSONB), reusing the batched-commit pattern.
- **Engine orchestrator** — iterates the registry in topological order.

Circular refs (region↔generation) are stored as bare integer columns (no FK) to keep
load order acyclic. `machine.move_id` is a bare integer (moves live in the other
pipeline), `machine.item_id`/`version_group_id` are FKs (loaded by the mirror).

## Orchestration
- **CLI**: `python -m src.main mirror [--all | --only item,berry]`.
- **DAG**: separate `pokeapi_mirror` (keeps `pokemon_etl` focused); tasks ordered by
  the registry's topological tiers.
- **Runtime**: a full mirror is thousands of requests — slow at 20 req/min. The client
  honors `API_RATE_LIMIT` (set higher for a bulk run); the on-disk cache makes re-runs
  cheap. No async (YAGNI) — keep the rate-limited sync client.

## Testing
- Engine unit tests: fetcher pagination (mocked httpx), JSONB transform, a relational
  transform, loader upserts (sqlite + new models), and topological ordering.
- Live smoke: `mirror --only nature,berry,item-category` against the dev DB; assert rows.

## Out of scope
- Migrating the existing 4 pipelines into the engine (possible later refactor).
- Async/concurrent fetching. Full normalization of the JSONB-tail resources.
