"""Main entry point for the Pokémon Data Analytics Platform."""

import argparse
import logging
import os
import sys
from typing import Dict, Any, List
from contextlib import contextmanager

from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.orm import Session

from src.ingestion.pokemon_fetcher import PokemonFetcher
from src.ingestion.type_fetcher import TypeFetcher
from src.transformation.pokemon_transformer import PokemonTransformer
from src.transformation.type_transformer import TypeTransformer
from src.loading.db_loader import DatabaseLoader
from src.analytics.stats_analyzer import StatsAnalyzer
from src.analytics.type_analyzer import TypeAnalyzer
from src.models.base import get_db, SessionLocal

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Pokémon Data Analytics API",
    description="API for accessing Pokémon data and analytics",
    version="1.0.0"
)

# Dependency to get database session
def get_db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/")
def read_root():
    """Root endpoint."""
    return {"message": "Welcome to the Pokémon Data Analytics API"}

@app.get("/pokemon")
def get_pokemon_list(skip: int = 0, limit: int = 10, db: Session = Depends(get_db_session)):
    """Get a list of Pokémon."""
    pokemon_list = list(db.execute("""
        SELECT p.id, p.name, p.height, p.weight, 
               array_agg(DISTINCT t.name) as types
        FROM pokemon p
        LEFT JOIN pokemon_types pt ON p.id = pt.pokemon_id
        LEFT JOIN types t ON pt.type_id = t.id
        GROUP BY p.id, p.name, p.height, p.weight
        ORDER BY p.id
        LIMIT :limit OFFSET :skip
    """, {"skip": skip, "limit": limit}))
    
    return [
        {
            "id": p[0],
            "name": p[1],
            "height": p[2],
            "weight": p[3],
            "types": p[4]
        }
        for p in pokemon_list
    ]

@app.get("/pokemon/{pokemon_id}")
def get_pokemon(pokemon_id: int, db: Session = Depends(get_db_session)):
    """Get detailed information about a specific Pokémon."""
    # Get basic Pokémon data
    pokemon = db.execute("""
        SELECT p.id, p.name, p.height, p.weight, p.base_experience
        FROM pokemon p
        WHERE p.id = :pokemon_id
    """, {"pokemon_id": pokemon_id}).first()
    
    if not pokemon:
        raise HTTPException(status_code=404, detail="Pokémon not found")
    
    # Get stats
    stats = db.execute("""
        SELECT stat_name, base_value
        FROM pokemon_stats
        WHERE pokemon_id = :pokemon_id
    """, {"pokemon_id": pokemon_id}).fetchall()
    
    # Get types
    types = db.execute("""
        SELECT t.name
        FROM pokemon_types pt
        JOIN types t ON pt.type_id = t.id
        WHERE pt.pokemon_id = :pokemon_id
        ORDER BY pt.slot
    """, {"pokemon_id": pokemon_id}).fetchall()
    
    return {
        "id": pokemon[0],
        "name": pokemon[1],
        "height": pokemon[2],
        "weight": pokemon[3],
        "base_experience": pokemon[4],
        "stats": {s[0]: s[1] for s in stats},
        "types": [t[0] for t in types]
    }

@app.get("/analytics/top-pokemon")
def get_top_pokemon(limit: int = 10, db: Session = Depends(get_db_session)):
    """Get top Pokémon by total base stats."""
    analyzer = StatsAnalyzer(db_session=db)
    return analyzer.get_top_pokemon_by_total_base_stats(limit=limit).to_dict(orient="records")

@app.get("/analytics/type-distribution")
def get_type_distribution(db: Session = Depends(get_db_session)):
    """Get the distribution of Pokémon types."""
    analyzer = StatsAnalyzer(db_session=db)
    return analyzer.get_type_distribution().to_dict(orient="records")

@app.get("/analytics/pokemon/{pokemon_id}/counters")
def get_pokemon_counters(pokemon_id: int, top_n: int = 5, db: Session = Depends(get_db_session)):
    """Get recommended counter types for a specific Pokémon."""
    analyzer = TypeAnalyzer(db_session=db)
    return analyzer.recommend_counter_types(pokemon_id, top_n=top_n).to_dict(orient="records")

# CLI command functions (existing code)
def fetch_and_load_pokemon_data(pokemon_range: tuple = None) -> None:
    """Fetch and load Pokémon data into the database.
    
    Args:
        pokemon_range: Optional tuple of (start_id, end_id) to limit the range of Pokémon.
            If None, will fetch all available Pokémon from the API.
    """
    # Initialize components
    pokemon_fetcher = PokemonFetcher()
    pokemon_transformer = PokemonTransformer()
    db_loader = DatabaseLoader()
    
    if pokemon_range:
        start_id, end_id = pokemon_range
        logger.info(f"Starting Pokémon data ingestion (IDs {start_id}-{end_id})")
        
        # Fetch specific range of Pokémon
        raw_pokemon_data = pokemon_fetcher.fetch_pokemon_batch(
            start_id=start_id, 
            end_id=end_id
        )
    else:
        logger.info("Starting Pokémon data ingestion for all available Pokémon")
        
        # Fetch all available Pokémon
        raw_pokemon_data = pokemon_fetcher.fetch_all_pokemon()
    
    # Transform Pokémon data
    transformed_pokemon_data = pokemon_transformer.transform_pokemon_batch(raw_pokemon_data)
    
    # Load Pokémon data into database
    db_loader.load_all_pokemon_data(transformed_pokemon_data)
    
    logger.info(f"Pokémon data ingestion completed successfully for {len(raw_pokemon_data)} Pokémon")

def fetch_and_load_type_data() -> None:
    """Fetch and load Type data into the database."""
    logger.info("Starting Type data ingestion")
    
    # Initialize components
    type_fetcher = TypeFetcher()
    type_transformer = TypeTransformer()
    db_loader = DatabaseLoader()
    
    # Fetch Type data
    raw_type_data = type_fetcher.fetch_all_types_with_effectiveness()
    
    # Transform Type data
    transformed_type_data = type_transformer.transform_type_batch(raw_type_data)
    
    # Load Type data into database
    db_loader.load_all_type_data(transformed_type_data)
    
    logger.info("Type data ingestion completed successfully")

def run_analytics(analytics_type: str = 'all') -> None:
    """Run analytics on the Pokémon data."""
    logger.info(f"Running analytics: {analytics_type}")
    
    stats_analyzer = StatsAnalyzer()
    type_analyzer = TypeAnalyzer()
    
    if analytics_type in ['stats', 'all']:
        logger.info("Running stats analytics")
        top_pokemon = stats_analyzer.get_top_pokemon_by_total_base_stats()
        print("\nTop 10 Pokémon by Total Base Stats:")
        print(top_pokemon)
        
        type_dist = stats_analyzer.get_type_distribution()
        print("\nType Distribution:")
        print(type_dist)
    
    if analytics_type in ['types', 'all']:
        logger.info("Running type analytics")
        best_attacking = type_analyzer.find_best_attacking_types()
        print("\nBest Attacking Types:")
        print(best_attacking.head())
        
        best_defensive = type_analyzer.find_best_defensive_types()
        print("\nBest Defensive Types:")
        print(best_defensive.head())
    
    logger.info("Analytics completed successfully")

def main() -> None:
    """Main entry point for the application."""
    parser = argparse.ArgumentParser(description='Pokémon Data Analytics Platform')
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Fetch data
    fetch_parser = subparsers.add_parser('fetch', help='Fetch data from the PokéAPI')
    fetch_parser.add_argument('--pokemon', action='store_true', help='Fetch Pokémon data')
    fetch_parser.add_argument('--types', action='store_true', help='Fetch Type data')
    fetch_parser.add_argument('--all', action='store_true', help='Fetch all data')
    fetch_parser.add_argument('--start-id', type=int, default=1, help='Starting Pokémon ID')
    fetch_parser.add_argument('--end-id', type=int, default=151, help='Ending Pokémon ID')
    fetch_parser.add_argument('--all-pokemon', action='store_true', help='Fetch all available Pokémon (ignores start-id and end-id)')
    
    # Analytics
    analytics_parser = subparsers.add_parser('analytics', help='Run analytics on the data')
    analytics_parser.add_argument('--type', choices=['stats', 'types', 'all'], default='all',
                                help='Type of analytics to run')
    
    # Parse arguments
    args = parser.parse_args()
    
    if args.command == 'fetch':
        if args.all or (args.pokemon and args.types):
            fetch_and_load_type_data()
            if args.all_pokemon:
                fetch_and_load_pokemon_data()
            else:
                fetch_and_load_pokemon_data((args.start_id, args.end_id))
        elif args.pokemon:
            if args.all_pokemon:
                fetch_and_load_pokemon_data()
            else:
                fetch_and_load_pokemon_data((args.start_id, args.end_id))
        elif args.types:
            fetch_and_load_type_data()
        else:
            fetch_parser.print_help()
    
    elif args.command == 'analytics':
        run_analytics(args.type)
    
    else:
        parser.print_help()

if __name__ == '__main__':
    if "uvicorn" in sys.argv[0]:
        # Running as web app
        pass
    else:
        # Running as CLI
        main()