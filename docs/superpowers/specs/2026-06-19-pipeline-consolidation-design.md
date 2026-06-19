# Ingestion Pipeline Consolidation — Design

**Date:** 2026-06-19 · **Status:** Approved (full consolidation; delete pokemon_etl; drop pokemon range)

## Goal
Retire the legacy per-entity pipeline (4 fetchers + 4 transformer classes +
`DatabaseLoader`) and the `pokemon_etl` DAG by making `pokemon/type/ability/move`
first-class resources of the generic mirror engine. One engine, one DAG.

## Engine extension: fan-out (one response → many tables)
- New `TableSpec(key, model, conflict)`. `ResourceSpec` gains `tables: tuple[TableSpec, ...]`.
  - Single-table relational (the existing 15 + ability + move) keep `model` + `transform(raw)->dict`.
  - Fan-out (type, pokemon) declare `tables` (ordered) + `transform(raw)->dict[str, list[dict]]`.
- Orchestrator: for fan-out, aggregate rows across all fetched records, then upsert each
  table in declared order (all parents before junctions — the legacy two-phase load).
- `ResourceLoader.load_relational(model, rows, conflict_cols=("id",))` — parameterize the
  ON CONFLICT target.

## Resource mappings
- `ability` → `[abilities]` (deps: none)
- `move` → `[moves]` (deps: type — moves.type_id)
- `type` → `[types, type_effectiveness(attack_type_id, defense_type_id)]` (deps: none)
- `pokemon` → `[pokemon, pokemon_stats(pokemon_id, stat_name), pokemon_types(pokemon_id, slot),
  pokemon_abilities(pokemon_id, ability_id), pokemon_moves(pokemon_id, move_id, learn_method)]`
  (deps: type, ability, move)

Transform *logic* is reused from the existing transformers, reshaped into table-keyed
functions; nothing about the row contents changes.

## Schema change
Add `UNIQUE (pokemon_id, stat_name)` to `pokemon_stats` (schema.sql + model) — required for
the ON CONFLICT upsert and closes a model↔schema gap.

## CLI / DAG
- `mirror --all` now ingests all 48 resources. `pokeapi_mirror` is the only DAG.
- `fetch` becomes a thin alias for `mirror --only type,ability,move,pokemon` (core analytics
  subset); `fetch_and_load_*` helpers removed.
- **Delete** `pokemon_etl` DAG. Pokémon is fetched in full (no id-range).

## Delete
`src/ingestion/{pokemon,type,ability,move}_fetcher.py`,
`src/transformation/{pokemon,type,ability,move}_transformer.py`, `src/loading/db_loader.py`,
`src/dags/pokemon_etl.py`, and their now-obsolete tests (logic re-tested as functions/engine).

## Verification
TDD for fan-out load, conflict param, core transforms. Parity: new engine yields the same
rows the legacy loader did. ruff/mypy/pytest + DAG parse + live smoke (load core entities,
check counts).
