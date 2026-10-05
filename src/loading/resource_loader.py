"""Generic atomic upsert loader for the mirror engine.

Uses INSERT ... ON CONFLICT DO UPDATE so loads are idempotent and safe under
Airflow task retries / overlapping runs (a re-fetch of already-loaded rows just
updates them instead of raising a duplicate-key error).
"""

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from src.models.api_resource import ApiResource
from src.models.base import SessionLocal
from src.models.mirror_run import MirrorResourceRun

logger = logging.getLogger(__name__)


class ResourceLoader:
    """Upserts mirror rows into a relational table or the JSONB tail."""

    def __init__(self, db_session: Session | None = None):
        self._owns_session = db_session is None
        self.db = db_session if db_session is not None else SessionLocal()

    def close(self) -> None:
        if self._owns_session:
            self.db.close()

    def begin_resource(self, name: str, started_at: datetime) -> None:
        """Serialize publication by resource and refuse an out-of-order snapshot."""
        if self.db.get_bind().dialect.name == "postgresql":
            self.db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": name})
        latest = self.db.execute(
            select(MirrorResourceRun.started_at)
            .where(MirrorResourceRun.resource_type == name, MirrorResourceRun.status == "success")
            .order_by(MirrorResourceRun.started_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if latest is not None and latest.replace(tzinfo=latest.tzinfo or UTC) > started_at:
            raise RuntimeError(f"stale mirror run for {name}: newer snapshot is already published")

    def reconcile_children(self, model: type, parent_column: str, parent_id: int) -> None:
        self.db.execute(delete(model).where(getattr(model, parent_column) == parent_id))

    def mark_absent(self, resource_type: str, present_ids: set[int]) -> None:
        """Tombstone removed upstream IDs only after a complete list/detail run."""
        stmt = update(ApiResource).where(ApiResource.resource_type == resource_type)
        if present_ids:
            stmt = stmt.where(ApiResource.id.not_in(present_ids))
        self.db.execute(stmt.values(is_present=False, loaded_at=func.now()))

    def record_run(self, **values: Any) -> None:
        self.db.add(MirrorResourceRun(**values))

    def _insert(self):
        """Dialect-appropriate INSERT construct (Postgres in prod, SQLite in tests)."""
        return pg_insert if self.db.get_bind().dialect.name == "postgresql" else sqlite_insert

    @staticmethod
    def _dedupe(values: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
        """Keep the last row per conflict key (ON CONFLICT can't hit a row twice)."""
        seen: dict[tuple, dict[str, Any]] = {}
        for v in values:
            seen[tuple(v[k] for k in keys)] = v
        return list(seen.values())

    def commit(self) -> None:
        """Commit the current transaction (used to load a fan-out resource atomically)."""
        self.db.commit()

    def load_relational(
        self,
        model: type,
        rows: list[dict[str, Any]],
        conflict_cols: tuple[str, ...] = ("id",),
        commit: bool = True,
    ) -> int:
        """Upsert rows into a relational table.

        Args:
            conflict_cols: the unique columns to ON CONFLICT on (a unique index
                must exist on them). Defaults to the primary key ``id``; junction
                tables pass their composite unique key.
            commit: commit immediately (default). Pass False to stage the write and
                commit later via ``commit()`` — used so all tables of a fan-out
                resource load in one transaction (all-or-nothing). On error the
                whole transaction is rolled back regardless.
        """
        if not rows:
            return 0
        table = model.__table__  # type: ignore[attr-defined]
        try:
            count = 0
            # Bounded statements: Pokémon's move fan-out exceeds 100k rows.
            for offset in range(0, len(rows), 300):
                values = self._dedupe(rows[offset : offset + 300], conflict_cols)
                stmt = self._insert()(table).values(values)
                skip = set(conflict_cols)
                update_cols = {
                    c.name: stmt.excluded[c.name]
                    for c in table.columns
                    if c.name not in skip and not c.primary_key
                }
                if update_cols:
                    stmt = stmt.on_conflict_do_update(
                        index_elements=list(conflict_cols), set_=update_cols
                    )
                else:
                    stmt = stmt.on_conflict_do_nothing(index_elements=list(conflict_cols))
                self.db.execute(stmt)
                count += len(values)
            if commit:
                self.db.commit()
            logger.info("Loaded %d %s", count, table.name)
            return count
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error loading {table.name}: {e}")
            raise

    def load_jsonb(
        self, resource_type: str, rows: list[dict[str, Any]], commit: bool = True
    ) -> int:
        """Upsert raw rows into api_resource keyed by (resource_type, id)."""
        if not rows:
            return 0
        try:
            count = 0
            for offset in range(0, len(rows), 300):
                values = self._dedupe(
                    [
                        {
                            "resource_type": resource_type,
                            "id": r["id"],
                            "name": r.get("name"),
                            "data": r["data"],
                            "source_fetched_at": r.get("source_fetched_at"),
                            "fetched_at": r.get("source_fetched_at") or datetime.now(UTC),
                            "loaded_at": datetime.now(UTC),
                            "is_present": True,
                        }
                        for r in rows[offset : offset + 300]
                    ],
                    ("resource_type", "id"),
                )
                stmt = self._insert()(ApiResource).values(values)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["resource_type", "id"],
                    set_={
                        "name": stmt.excluded.name,
                        "data": stmt.excluded.data,
                        "source_fetched_at": stmt.excluded.source_fetched_at,
                        "fetched_at": stmt.excluded.fetched_at,
                        "loaded_at": func.now(),
                        "is_present": True,
                    },
                )
                self.db.execute(stmt)
                count += len(values)
            if commit:
                self.db.commit()
            logger.info("Loaded %d %s (raw)", count, resource_type)
            return count
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error loading {resource_type}: {e}")
            raise
