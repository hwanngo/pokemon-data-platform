# Audit remediation status

This is the implementation follow-up to [PROJECT_AUDIT.md](PROJECT_AUDIT.md), which remains the evidence-based audit of revision `48444e9502fea96fc01086e64a6a211e63470993`. The audit's severity counts describe that baseline, not the current working tree. Changes are uncommitted and have not been deployed.

IDs in the table omit the shared `AUDIT-` prefix.

## Addressed in the working tree

| Audit IDs | Change |
| --- | --- |
| SEC-001, SEC-002 | Docker build context/source allowlist excludes local secrets; development generates unique credentials and production requires explicit strong credentials. |
| SEC-003 | Separate application reader, mirror writer, and Airflow metadata credentials/databases; Compose wires each service to its required role. |
| DATA-001, REL-002 | Origin-scoped, time-limited cache with refresh by default; retry attempts respect rate limits and permanent HTTP failures are not retried. |
| DATA-002, REL-001 | Successful mirror runs reconcile authoritative child rows and tombstone removed raw resources; incomplete runs roll back and record failure/partial status. Public read paths filter tombstones. |
| DATA-003, DATA-004 | Preserve raw detail for relational resources, source/load timestamps, all move version groups and learning levels. |
| DB-001, DB-002 | Forward schema migration on startup and ORM index parity. Fresh initialization and existing-volume upgrades share the migration runner. |
| LOGIC-001, LOGIC-002, LOGIC-003 | Generation selection uses species, effectiveness includes neutral-only types, and move coverage deduplicates moves with explicit version and ratio semantics. |
| API-001, RES-001, PERF-002 | Bounded API parameters, missing-target 404s, scoped sessions/client cleanup, and selected-view dashboard computation. |
| PERF-001 | Bounded detail fetching and SQL batches, disk-spooled resource staging, and per-resource atomic publication. |
| OPS-001, OPS-002, OPS-003, OPS-004 | Isolated Compose projects/volumes, gated Airflow initialization, corrected health checks, and loopback host access to the API. |
| CFG-001, TEST-001, DOC-001 | Explicit environment validation, cross-layer regression tests, and revised operating/setup documentation. |
| UX-001, UX-002, RESPONSIVE-001, A11Y-001, CODE-001 | Safe empty/error states, retry affordance, single-type and full-table alternatives to the heatmap, and current Streamlit width API. |

`AUDIT-ARCH-001` was informational: the public read-only API and a few bare references are deliberate boundaries, so no architectural rewrite was attempted.

## Remaining work and verification

- **AUDIT-DEP-001 remains open.** `uv lock --upgrade` was retried on 2026-09-29, but terminal DNS still cannot resolve `pypi.org`; a cloned local uv cache also lacks FastAPI registry metadata, so `uv lock --upgrade --offline` cannot solve the dependency graph. `uv.lock` and `pyproject.toml` remain unchanged. `make upgrade` will re-resolve all extras and synchronize the Airflow image tag and complete hashed requirements from the resulting lockfile. A connected resolution, advisory rescan, builds, and runtime checks are still required.
- **AUDIT-OPS-005 is partially addressed.** CI pins actions, verifies the gitleaks download, checks lock/builds, and blocks secret-file inclusion in the application image. The application builder and PostgreSQL images are now pinned by published multi-platform digests ([uv package](https://github.com/astral-sh/uv/pkgs/container/uv/versions), [PostgreSQL image](https://hub.docker.com/layers/library/postgres/18-alpine/images/sha256-b6a16ed0eb96e2c362811f7eeb951eac8b459e7b40be4149ea5444aa7c65569b2)). The Airflow image now installs the full hashed `uv.lock` Airflow resolution rather than re-resolving transitive packages with pip, and CI verifies the export and smoke-imports the DAG. The Airflow base tag is still mutable, and this image change needs a connected CI build before release.
- **Deployment validation remains open locally.** The Docker daemon and PostgreSQL server were unavailable. Compose plans and shell syntax passed. A new CI job is configured to exercise fresh and legacy-schema migrations, idempotence, data preservation, and role grants against an ephemeral PostgreSQL service; it has not run in this workspace. Full Airflow startup, image builds, backup/restore, and health checks still need a disposable full-stack run before release.
- **Visual and assistive-technology validation remains open.** Streamlit AppTest covered empty, populated, generation-filtered, and database-error states after the changes. The local Streamlit server could not bind a loopback socket in this sandbox, and the installed agent-browser command was unavailable, so a graphical mobile/desktop pass remains necessary. Keyboard/screen-reader review of the new effectiveness alternatives also remains necessary. The requested UI Taste Skill was unavailable during the audit, as documented there; no Taste-based validation is claimed here.

## Verification completed

- `python -m pytest -q`: 67 passed, two PostgreSQL integration tests skipped without the explicit CI service, one upstream Starlette deprecation warning.
- `python -m ruff check src tests docker`, `python -m ruff format --check src tests docker`, `python -m mypy src`, and `git diff --check`: passed.
- `uv lock --check --offline` with an isolated cache: passed.
- Development and production `docker compose config -q` with dummy environment values: passed.
- `actionlint .github/workflows/ci.yml`: passed after adding the PostgreSQL integration job.
- `python3 docker/sync_airflow_pins.py --check`: passed against the current lockfile; the Airflow image uses the exported hashes and no untested package versions were written.
- Gitleaks scanned 67 tracked and new repository files in an isolated copy, excluding ignored local secret files: zero findings. The existing ignored `.env` was not part of this scan.
- `uv build --offline` could not run because Hatchling was absent from the isolated cache; Docker image builds could not run because the daemon was unavailable.

The first run with the origin-scoped cache intentionally refetches data; old root-level cache files are left untouched.
