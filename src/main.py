"""Main entry point for the Pokémon Data Analytics Platform."""

import argparse
import logging

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.analytics.stats_analyzer import StatsAnalyzer
from src.analytics.type_analyzer import TypeAnalyzer
from src.ingestion.mirror import run_mirror
from src.models.base import get_db, session_scope

# Core analytics entities, ingested via the mirror engine (deps auto-included).
CORE_RESOURCES = ["type", "ability", "move", "pokemon"]

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Pokémon Data Analytics API",
    description="API for accessing Pokémon data and analytics",
    version="1.0.0",
)


@app.get("/")
def read_root():
    """Root endpoint."""
    return {"message": "Welcome to the Pokémon Data Analytics API"}


@app.get("/pokemon")
def get_pokemon_list(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Get a list of Pokémon."""
    pokemon_list = list(
        db.execute(
            text("""
        SELECT p.id, p.name, p.height, p.weight,
               array_remove(array_agg(DISTINCT t.name), NULL) as types
        FROM pokemon p
        LEFT JOIN pokemon_types pt ON p.id = pt.pokemon_id
        LEFT JOIN types t ON pt.type_id = t.id
        GROUP BY p.id, p.name, p.height, p.weight
        ORDER BY p.id
        LIMIT :limit OFFSET :skip
    """),
            {"skip": skip, "limit": limit},
        )
    )

    return [
        {"id": p[0], "name": p[1], "height": p[2], "weight": p[3], "types": p[4]}
        for p in pokemon_list
    ]


@app.get("/pokemon/{pokemon_id}")
def get_pokemon(pokemon_id: int, db: Session = Depends(get_db)):
    """Get detailed information about a specific Pokémon."""
    # Get basic Pokémon data
    pokemon = db.execute(
        text("""
        SELECT p.id, p.name, p.height, p.weight, p.base_experience
        FROM pokemon p
        WHERE p.id = :pokemon_id
    """),
        {"pokemon_id": pokemon_id},
    ).first()

    if not pokemon:
        raise HTTPException(status_code=404, detail="Pokémon not found")

    # Get stats
    stats = db.execute(
        text("""
        SELECT stat_name, base_value
        FROM pokemon_stats
        WHERE pokemon_id = :pokemon_id
    """),
        {"pokemon_id": pokemon_id},
    ).fetchall()

    # Get types
    types = db.execute(
        text("""
        SELECT t.name
        FROM pokemon_types pt
        JOIN types t ON pt.type_id = t.id
        WHERE pt.pokemon_id = :pokemon_id
        ORDER BY pt.slot
    """),
        {"pokemon_id": pokemon_id},
    ).fetchall()

    return {
        "id": pokemon[0],
        "name": pokemon[1],
        "height": pokemon[2],
        "weight": pokemon[3],
        "base_experience": pokemon[4],
        "stats": {s[0]: s[1] for s in stats},
        "types": [t[0] for t in types],
    }


@app.get("/analytics/top-pokemon")
def get_top_pokemon(limit: int = 10, db: Session = Depends(get_db)):
    """Get top Pokémon by total base stats."""
    analyzer = StatsAnalyzer(db_session=db)
    return analyzer.get_top_pokemon_by_total_base_stats(limit=limit).to_dict(orient="records")


@app.get("/analytics/type-distribution")
def get_type_distribution(db: Session = Depends(get_db)):
    """Get the distribution of Pokémon types."""
    analyzer = StatsAnalyzer(db_session=db)
    return analyzer.get_type_distribution().to_dict(orient="records")


@app.get("/analytics/pokemon/{pokemon_id}/counters")
def get_pokemon_counters(pokemon_id: int, top_n: int = 5, db: Session = Depends(get_db)):
    """Get recommended counter types for a specific Pokémon."""
    analyzer = TypeAnalyzer(db_session=db)
    return analyzer.recommend_counter_types(pokemon_id, top_n=top_n).to_dict(orient="records")


def run_analytics(analytics_type: str = "all") -> None:
    """Run analytics on the Pokémon data."""
    logger.info(f"Running analytics: {analytics_type}")

    # One scoped session for the whole run, always closed (no connection leak).
    with session_scope() as db:
        stats_analyzer = StatsAnalyzer(db_session=db)
        type_analyzer = TypeAnalyzer(db_session=db)

        if analytics_type in ["stats", "all"]:
            logger.info("Running stats analytics")
            top_pokemon = stats_analyzer.get_top_pokemon_by_total_base_stats()
            print("\nTop 10 Pokémon by Total Base Stats:")
            print(top_pokemon)

            type_dist = stats_analyzer.get_type_distribution()
            print("\nType Distribution:")
            print(type_dist)

        if analytics_type in ["types", "all"]:
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
    parser = argparse.ArgumentParser(description="Pokémon Data Analytics Platform")

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Fetch — load the core analytics entities via the mirror engine.
    fetch_parser = subparsers.add_parser(
        "fetch", help="Load core entities (type/ability/move/pokemon) via the mirror engine"
    )
    fetch_parser.add_argument("--pokemon", action="store_true", help="Load Pokémon (+ FK deps)")
    fetch_parser.add_argument("--types", action="store_true", help="Load types")
    fetch_parser.add_argument("--abilities", action="store_true", help="Load abilities")
    fetch_parser.add_argument("--moves", action="store_true", help="Load moves")
    fetch_parser.add_argument("--all", action="store_true", help="Load all core entities (default)")

    # Analytics
    analytics_parser = subparsers.add_parser("analytics", help="Run analytics on the data")
    analytics_parser.add_argument(
        "--type", choices=["stats", "types", "all"], default="all", help="Type of analytics to run"
    )

    # Mirror — full PokéAPI mirror via the generic engine
    mirror_parser = subparsers.add_parser("mirror", help="Mirror PokéAPI resources locally")
    mirror_parser.add_argument("--all", action="store_true", help="Mirror the whole registry")
    mirror_parser.add_argument(
        "--only",
        type=str,
        default=None,
        help="Comma-separated resources to mirror (deps auto-included), e.g. --only nature,berry",
    )

    # Parse arguments
    args = parser.parse_args()

    if args.command == "fetch":
        if args.all:
            selected = CORE_RESOURCES
        else:
            selected = [
                r
                for flag, r in (
                    (args.types, "type"),
                    (args.abilities, "ability"),
                    (args.moves, "move"),
                    (args.pokemon, "pokemon"),
                )
                if flag
            ] or CORE_RESOURCES
        # run_mirror loads in topological order and auto-includes FK parents.
        run_mirror(only=selected)

    elif args.command == "analytics":
        run_analytics(args.type)

    elif args.command == "mirror":
        if args.only:
            run_mirror(only=[r.strip() for r in args.only.split(",") if r.strip()])
        elif args.all:
            run_mirror()
        else:
            mirror_parser.print_help()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
