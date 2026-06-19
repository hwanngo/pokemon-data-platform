"""Generic atomic upsert loader for the mirror engine.

Uses INSERT ... ON CONFLICT DO UPDATE so loads are idempotent and safe under
Airflow task retries / overlapping runs (a re-fetch of already-loaded rows just
updates them instead of raising a duplicate-key error).
"""

import logging
from typing import Any

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from src.models.api_resource import ApiResource
from src.models.base import SessionLocal

logger = logging.getLogger(__name__)


class ResourceLoader:
    """Upserts mirror rows into a relational table or the JSONB tail."""

    def __init__(self, db_session: Session | None = None):
        self.db = db_session if db_session else SessionLocal()

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
            values = self._dedupe(rows, conflict_cols)
            stmt = self._insert()(table).values(values)
            # Update every column except the conflict key and primary key.
            skip = set(conflict_cols)
            update_cols = {
                c.name: stmt.excluded[c.name]
                for c in table.columns
                if c.name not in skip and not c.primary_key
            }
            stmt = stmt.on_conflict_do_update(index_elements=list(conflict_cols), set_=update_cols)
            self.db.execute(stmt)
            if commit:
                self.db.commit()
            logger.info(f"Loaded {len(values)} {table.name}")
            return len(values)
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error loading {table.name}: {e}")
            raise

    def load_jsonb(self, resource_type: str, rows: list[dict[str, Any]]) -> int:
        """Upsert raw rows into api_resource keyed by (resource_type, id)."""
        if not rows:
            return 0
        try:
            values = self._dedupe(
                [
                    {
                        "resource_type": resource_type,
                        "id": r["id"],
                        "name": r["name"],
                        "data": r["data"],
                    }
                    for r in rows
                ],
                ("resource_type", "id"),
            )
            stmt = self._insert()(ApiResource).values(values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["resource_type", "id"],
                set_={
                    "name": stmt.excluded.name,
                    "data": stmt.excluded.data,
                    "fetched_at": func.now(),
                },
            )
            self.db.execute(stmt)
            self.db.commit()
            logger.info(f"Loaded {len(values)} {resource_type} (jsonb)")
            return len(values)
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error loading {resource_type}: {e}")
            raise
