"""Type effectiveness analyzer module."""

import logging

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.models.base import SessionLocal

logger = logging.getLogger(__name__)


class TypeAnalyzer:
    """Analyzes Pokémon type data to generate insights."""

    def __init__(self, db_session: Session | None = None):
        """
        Initialize the type analyzer.

        Args:
            db_session: SQLAlchemy database session. If None, a new one will be created.
        """
        self._owns_session = db_session is None
        self.db = db_session if db_session is not None else SessionLocal()
        logger.info("Initialized TypeAnalyzer")

    def close(self) -> None:
        """Close a session created by this analyzer; leave injected sessions to their owner."""
        if self._owns_session:
            self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc_value, _traceback):
        self.close()

    def get_effectiveness_matrix(self) -> pd.DataFrame:
        """
        Generate a matrix of type effectiveness.

        Returns:
            DataFrame with attacking types as rows and defending types as columns.
        """
        query = """
        SELECT
            at.name as attacking_type,
            dt.name as defending_type,
            te.effectiveness
        FROM type_effectiveness te
        JOIN types at ON te.attack_type_id = at.id
        JOIN types dt ON te.defense_type_id = dt.id
        """

        type_names = [
            row[0]
            for row in self.db.execute(
                text("""
                SELECT t.name FROM types t
                WHERE NOT EXISTS (
                    SELECT 1 FROM api_resource ar
                    WHERE ar.resource_type = 'type' AND ar.id = t.id AND ar.is_present = false
                )
                ORDER BY t.name
            """)
            )
        ]
        matrix = pd.DataFrame(1.0, index=type_names, columns=type_names)
        for attack, defense, effectiveness in self.db.execute(text(query)):
            if attack in matrix.index and defense in matrix.columns:
                matrix.loc[attack, defense] = float(effectiveness)

        logger.info("Generated type effectiveness matrix")
        return matrix

    def find_best_attacking_types(self, matrix: pd.DataFrame | None = None) -> pd.DataFrame:
        """
        Find the best attacking types based on overall effectiveness.

        Returns:
            DataFrame with types ranked by offensive potential.
        """
        if matrix is None:
            matrix = self.get_effectiveness_matrix()

        # Calculate average effectiveness and super effective count
        results = []
        for attack_type in matrix.index:
            effectiveness_values = matrix.loc[attack_type].values
            avg_effectiveness = np.mean(effectiveness_values)
            super_effective_count = np.sum(effectiveness_values > 1.0)
            no_effect_count = np.sum(effectiveness_values == 0.0)

            results.append(
                {
                    "type": attack_type,
                    "avg_effectiveness": round(float(avg_effectiveness), 2),
                    "super_effective_count": int(super_effective_count),
                    "no_effect_count": int(no_effect_count),
                }
            )

        df = pd.DataFrame(
            results,
            columns=["type", "avg_effectiveness", "super_effective_count", "no_effect_count"],
        )
        df = df.sort_values(by=["super_effective_count", "avg_effectiveness"], ascending=False)

        logger.info("Ranked attacking types by effectiveness")
        return df

    def find_best_defensive_types(self, matrix: pd.DataFrame | None = None) -> pd.DataFrame:
        """
        Find the best defensive types based on resistances.

        Returns:
            DataFrame with types ranked by defensive potential.
        """
        if matrix is None:
            matrix = self.get_effectiveness_matrix()

        # Calculate for each defending type
        results = []
        for defense_type in matrix.columns:
            effectiveness_against = matrix[defense_type].values
            avg_effectiveness = np.mean(effectiveness_against)
            weaknesses_count = np.sum(effectiveness_against > 1.0)
            resistances_count = np.sum(effectiveness_against < 1.0)
            immunities_count = np.sum(effectiveness_against == 0.0)

            results.append(
                {
                    "type": defense_type,
                    "avg_effectiveness_against": round(float(avg_effectiveness), 2),
                    "weaknesses_count": int(weaknesses_count),
                    "resistances_count": int(resistances_count),
                    "immunities_count": int(immunities_count),
                }
            )

        df = pd.DataFrame(
            results,
            columns=[
                "type",
                "avg_effectiveness_against",
                "weaknesses_count",
                "resistances_count",
                "immunities_count",
            ],
        )
        # Lower avg_effectiveness_against is better for defense
        df = df.sort_values(
            by=["immunities_count", "resistances_count", "avg_effectiveness_against"],
            ascending=[False, False, True],
        )

        logger.info("Ranked defensive types by resistances")
        return df

    def get_pokemon_weakness_profile(
        self, pokemon_id: int, matrix: pd.DataFrame | None = None
    ) -> pd.DataFrame:
        """
        Generate a weakness/resistance profile for a specific Pokémon.

        Args:
            pokemon_id: The ID of the Pokémon to analyze.

        Returns:
            DataFrame with effectiveness of each type against the Pokémon.
        """
        # First get the Pokémon's types
        type_query = """
        SELECT t.name
        FROM pokemon_types pt
        JOIN pokemon p ON pt.pokemon_id = p.id
        JOIN types t ON pt.type_id = t.id
        WHERE pt.pokemon_id = :pokemon_id
          AND NOT EXISTS (
              SELECT 1 FROM api_resource ar
              WHERE ar.resource_type = 'pokemon' AND ar.id = p.id AND ar.is_present = false
          )
          AND NOT EXISTS (
              SELECT 1 FROM api_resource ar
              WHERE ar.resource_type = 'type' AND ar.id = t.id AND ar.is_present = false
          )
        ORDER BY pt.slot
        """

        type_result = self.db.execute(text(type_query), {"pokemon_id": pokemon_id})
        pokemon_types = [row[0] for row in type_result.fetchall()]

        if not pokemon_types:
            logger.warning(f"No types found for Pokémon ID {pokemon_id}")
            return pd.DataFrame(columns=["attacking_type", "effectiveness"])

        # Get the full effectiveness matrix
        if matrix is None:
            matrix = self.get_effectiveness_matrix()

        # Calculate the combined effectiveness against this Pokémon
        effectiveness_against = {}
        for attack_type in matrix.index:
            # Multiply effectiveness against each of the Pokémon's types
            combined_effectiveness = 1.0
            for defense_type in pokemon_types:
                if defense_type in matrix.columns:
                    combined_effectiveness *= matrix.loc[attack_type, defense_type]

            effectiveness_against[attack_type] = combined_effectiveness

        # Create a DataFrame with the results
        df = pd.DataFrame(
            [{"attacking_type": t, "effectiveness": e} for t, e in effectiveness_against.items()]
        )

        df = df.sort_values(by="effectiveness", ascending=False)

        logger.info("Generated weakness profile for Pokémon ID %s", pokemon_id)
        return df

    def recommend_counter_types(
        self,
        pokemon_id: int,
        top_n: int = 5,
        weakness_profile: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        """
        Recommend the best types to counter a specific Pokémon.

        Args:
            pokemon_id: The ID of the Pokémon to counter.
            top_n: Number of counter types to recommend.

        Returns:
            DataFrame with recommended counter types.
        """
        if top_n < 1:
            raise ValueError("top_n must be positive")
        if weakness_profile is None:
            weakness_profile = self.get_pokemon_weakness_profile(pokemon_id)

        if weakness_profile.empty:
            return pd.DataFrame(columns=["attacking_type", "effectiveness", "description"])

        # Get only super effective types (effectiveness > 1.0)
        counters = weakness_profile[weakness_profile["effectiveness"] > 1.0].copy()
        counters = counters.sort_values(by="effectiveness", ascending=False)

        # Limit to top_n results
        if len(counters) > top_n:
            counters = counters.head(top_n)

        # Add description of the effectiveness
        def get_effectiveness_label(value):
            if value >= 4.0:
                return "4× (extremely effective)"
            elif value >= 2.0:
                return "2× (super effective)"
            else:
                return f"{value}× (effective)"

        counters["description"] = counters["effectiveness"].apply(get_effectiveness_label)

        logger.info("Recommended %s counter types for Pokémon ID %s", len(counters), pokemon_id)
        return counters
