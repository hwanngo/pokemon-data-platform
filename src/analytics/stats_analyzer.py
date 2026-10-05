"""Pokémon stats analyzer module."""

import logging
from collections import Counter, defaultdict

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.models.base import SessionLocal

logger = logging.getLogger(__name__)


class StatsAnalyzer:
    """Analyzes Pokémon stats to generate insights."""

    def __init__(self, db_session: Session | None = None):
        """
        Initialize the stats analyzer.

        Args:
            db_session: SQLAlchemy database session. If None, a new one will be created.
        """
        self._owns_session = db_session is None
        self.db = db_session if db_session is not None else SessionLocal()
        logger.info("Initialized StatsAnalyzer")

    def close(self) -> None:
        """Close a session created by this analyzer; leave injected sessions to their owner."""
        if self._owns_session:
            self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc_value, _traceback):
        self.close()

    def get_top_pokemon_by_total_base_stats(self, limit: int = 10) -> pd.DataFrame:
        """
        Get the top Pokémon by total base stats.

        Args:
            limit: Maximum number of Pokémon to return.

        Returns:
            DataFrame with the top Pokémon by total base stats.
        """
        query = """
        SELECT p.id, p.name, SUM(ps.base_value) as total_base_stats
        FROM pokemon p
        JOIN pokemon_stats ps ON p.id = ps.pokemon_id
        WHERE NOT EXISTS (
            SELECT 1 FROM api_resource ar
            WHERE ar.resource_type = 'pokemon' AND ar.id = p.id AND ar.is_present = false
        )
        GROUP BY p.id, p.name
        ORDER BY total_base_stats DESC, p.id ASC
        LIMIT :limit
        """

        result = self.db.execute(text(query), {"limit": limit})
        df = pd.DataFrame(result.fetchall(), columns=["id", "name", "total_base_stats"])

        logger.info(f"Retrieved top {limit} Pokémon by total base stats")
        return df

    def get_type_distribution(self) -> pd.DataFrame:
        """
        Get the distribution of Pokémon types.

        Returns:
            DataFrame with the count of Pokémon for each type.
        """
        query = """
        SELECT t.name as type_name, COUNT(pt.pokemon_id) as pokemon_count
        FROM types t
        JOIN pokemon_types pt ON t.id = pt.type_id
        WHERE NOT EXISTS (
            SELECT 1 FROM api_resource ar
            WHERE ar.resource_type = 'type' AND ar.id = t.id AND ar.is_present = false
        )
          AND NOT EXISTS (
            SELECT 1 FROM api_resource ar
            WHERE ar.resource_type = 'pokemon' AND ar.id = pt.pokemon_id AND ar.is_present = false
        )
        GROUP BY t.name
        ORDER BY pokemon_count DESC
        """

        result = self.db.execute(text(query))
        df = pd.DataFrame(result.fetchall(), columns=["type_name", "pokemon_count"])

        logger.info("Retrieved type distribution analysis")
        return df

    def get_dual_type_combinations(self) -> pd.DataFrame:
        """
        Get the distribution of dual-type combinations among Pokémon.

        Returns:
            DataFrame with counts of each type combination.
        """
        rows = self.db.execute(
            text("""
            SELECT p.id, t.name
            FROM pokemon p
            JOIN pokemon_types pt ON p.id = pt.pokemon_id
            JOIN types t ON pt.type_id = t.id
            WHERE NOT EXISTS (
                SELECT 1 FROM api_resource ar
                WHERE ar.resource_type = 'pokemon' AND ar.id = p.id AND ar.is_present = false
            )
              AND NOT EXISTS (
                SELECT 1 FROM api_resource ar
                WHERE ar.resource_type = 'type' AND ar.id = t.id AND ar.is_present = false
            )
            ORDER BY p.id, pt.slot
        """)
        )
        types_by_pokemon: dict[int, list[str]] = defaultdict(list)
        for pokemon_id, type_name in rows:
            types_by_pokemon[pokemon_id].append(type_name)
        counts = Counter("/".join(names) for names in types_by_pokemon.values() if len(names) == 2)
        df = pd.DataFrame(
            sorted(counts.items(), key=lambda item: (-item[1], item[0])),
            columns=["type_combination", "pokemon_count"],
        )

        logger.info("Retrieved dual-type combination analysis")
        return df

    def get_pokemon_with_best_type_coverage(
        self, limit: int = 10, version_group_id: int | None = None
    ) -> pd.DataFrame:
        """
        Find Pokémon with the best move type coverage.

        Args:
            limit: Maximum number of Pokémon to return.
            version_group_id: Restrict moves to one game version group. If omitted,
                report the union across all known and legacy unscoped versions.

        Returns:
            DataFrame with Pokémon ranked by move type diversity.
        """
        query = """
        WITH move_types AS (
            SELECT
                pm.pokemon_id,
                p.name as pokemon_name,
                COUNT(DISTINCT m.type_id) as unique_move_types,
                COUNT(DISTINCT m.id) as total_moves
            FROM pokemon_moves pm
            JOIN pokemon p ON pm.pokemon_id = p.id
            JOIN moves m ON pm.move_id = m.id
            WHERE (:version_group_id IS NULL OR pm.version_group_id = :version_group_id)
              AND NOT EXISTS (
                  SELECT 1 FROM api_resource ar
                  WHERE ar.resource_type = 'pokemon' AND ar.id = p.id AND ar.is_present = false
              )
              AND NOT EXISTS (
                  SELECT 1 FROM api_resource ar
                  WHERE ar.resource_type = 'move' AND ar.id = m.id AND ar.is_present = false
              )
              AND NOT EXISTS (
                  SELECT 1 FROM api_resource ar
                  WHERE ar.resource_type = 'type' AND ar.id = m.type_id AND ar.is_present = false
              )
            GROUP BY pm.pokemon_id, p.name
        )
        SELECT
            pokemon_id,
            pokemon_name,
            unique_move_types,
            total_moves,
            ROUND(1.0 * unique_move_types /
                  NULLIF((
                      SELECT COUNT(*) FROM types t
                      WHERE NOT EXISTS (
                          SELECT 1 FROM api_resource ar
                          WHERE ar.resource_type = 'type' AND ar.id = t.id
                            AND ar.is_present = false
                      )
                  ), 0), 4) as type_coverage_ratio
        FROM move_types
        ORDER BY unique_move_types DESC, total_moves DESC, pokemon_id ASC
        LIMIT :limit
        """

        result = self.db.execute(
            text(query), {"limit": limit, "version_group_id": version_group_id}
        )
        df = pd.DataFrame(
            result.fetchall(),
            columns=[
                "pokemon_id",
                "pokemon_name",
                "unique_move_types",
                "total_moves",
                "type_coverage_ratio",
            ],
        )

        logger.info(f"Retrieved top {limit} Pokémon with best move type coverage")
        return df
