"""Pokémon stats analyzer module."""

import logging
import pandas as pd
from typing import List, Dict, Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.models.base import get_db

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class StatsAnalyzer:
    """Analyzes Pokémon stats to generate insights."""
    
    def __init__(self, db_session: Optional[Session] = None):
        """
        Initialize the stats analyzer.
        
        Args:
            db_session: SQLAlchemy database session. If None, a new one will be created.
        """
        self.db = db_session if db_session else next(get_db())
        logger.info("Initialized StatsAnalyzer")
    
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
        GROUP BY p.id, p.name
        ORDER BY total_base_stats DESC
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
        query = """
        WITH pokemon_types_agg AS (
            SELECT 
                p.id,
                p.name,
                STRING_AGG(t.name, '/' ORDER BY pt.slot) as type_combination
            FROM pokemon p
            JOIN pokemon_types pt ON p.id = pt.pokemon_id
            JOIN types t ON pt.type_id = t.id
            GROUP BY p.id, p.name
        )
        SELECT 
            type_combination,
            COUNT(*) as pokemon_count
        FROM pokemon_types_agg
        GROUP BY type_combination
        ORDER BY pokemon_count DESC
        """
        
        result = self.db.execute(text(query))
        df = pd.DataFrame(result.fetchall(), columns=["type_combination", "pokemon_count"])
        
        logger.info("Retrieved dual-type combination analysis")
        return df
    
    def get_pokemon_with_best_type_coverage(self, limit: int = 10) -> pd.DataFrame:
        """
        Find Pokémon with the best move type coverage.
        
        Args:
            limit: Maximum number of Pokémon to return.
            
        Returns:
            DataFrame with Pokémon ranked by move type diversity.
        """
        query = """
        WITH move_types AS (
            SELECT 
                pm.pokemon_id,
                p.name as pokemon_name,
                COUNT(DISTINCT m.type_id) as unique_move_types,
                COUNT(m.id) as total_moves
            FROM pokemon_moves pm
            JOIN pokemon p ON pm.pokemon_id = p.id
            JOIN moves m ON pm.move_id = m.id
            GROUP BY pm.pokemon_id, p.name
        )
        SELECT 
            pokemon_id,
            pokemon_name,
            unique_move_types,
            total_moves,
            ROUND(CAST(unique_move_types AS NUMERIC) / 
                  (SELECT COUNT(*) FROM types), 2) as type_coverage_pct
        FROM move_types
        ORDER BY unique_move_types DESC, total_moves DESC
        LIMIT :limit
        """
        
        result = self.db.execute(text(query), {"limit": limit})
        df = pd.DataFrame(result.fetchall(), 
                         columns=["pokemon_id", "pokemon_name", "unique_move_types", 
                                 "total_moves", "type_coverage_pct"])
        
        logger.info(f"Retrieved top {limit} Pokémon with best move type coverage")
        return df