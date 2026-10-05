"""Main entry point for the Pokémon Data Analytics Platform."""

import argparse
import logging
import os

from fastapi import Depends, FastAPI, HTTPException, Path, Query
from pydantic import BaseModel
from sqlalchemy import bindparam, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.analytics.stats_analyzer import StatsAnalyzer
from src.analytics.type_analyzer import TypeAnalyzer
from src.ingestion.mirror import run_mirror
from src.models.base import get_db, session_scope

# Core analytics entities, ingested via the mirror engine (deps auto-included).
CORE_RESOURCES = ["type", "ability", "move", "pokemon"]

# Configure logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
if LOG_LEVEL not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
    raise ValueError(f"Invalid LOG_LEVEL: {LOG_LEVEL}")
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Pokémon Data Analytics API",
    description="API for accessing Pokémon data and analytics",
    version="1.0.0",
)


class PokemonSummary(BaseModel):
    id: int
    name: str
    height: int
    weight: int
    types: list[str]


class PokemonDetail(PokemonSummary):
    base_experience: int | None
    stats: dict[str, int]


class TopPokemon(BaseModel):
    id: int
    name: str
    total_base_stats: int


class TypeDistribution(BaseModel):
    type_name: str
    pokemon_count: int


class CounterType(BaseModel):
    attacking_type: str
    effectiveness: float
    description: str


@app.get("/")
def read_root():
    """Root endpoint."""
    return {"message": "Welcome to the Pokémon Data Analytics API"}


@app.get("/health/ready")
def read_ready(db: Session = Depends(get_db)):
    """Check whether the database can answer reads."""
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.exception("Database readiness check failed")
        raise HTTPException(status_code=503, detail="Database unavailable") from None
    return {"status": "ready"}


@app.get("/pokemon", response_model=list[PokemonSummary])
def get_pokemon_list(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Get a list of Pokémon."""
    pokemon_list = db.execute(
        text("""
            SELECT p.id, p.name, p.height, p.weight
            FROM pokemon p
            WHERE NOT EXISTS (
                SELECT 1 FROM api_resource ar
                WHERE ar.resource_type = 'pokemon' AND ar.id = p.id AND ar.is_present = false
            )
            ORDER BY p.id
            LIMIT :limit OFFSET :skip
        """),
        {"skip": skip, "limit": limit},
    ).all()
    if not pokemon_list:
        return []
    ids = [row.id for row in pokemon_list]
    type_rows = db.execute(
        text("""
            SELECT pt.pokemon_id, t.name
            FROM pokemon_types pt
            JOIN types t ON pt.type_id = t.id
            WHERE pt.pokemon_id IN :ids
              AND NOT EXISTS (
                  SELECT 1 FROM api_resource ar
                  WHERE ar.resource_type = 'type' AND ar.id = t.id AND ar.is_present = false
              )
            ORDER BY pt.pokemon_id, pt.slot
        """).bindparams(bindparam("ids", expanding=True)),
        {"ids": ids},
    )
    types_by_id: dict[int, list[str]] = {pokemon_id: [] for pokemon_id in ids}
    for pokemon_id, type_name in type_rows:
        types_by_id[pokemon_id].append(type_name)
    return [
        {
            "id": row.id,
            "name": row.name,
            "height": row.height,
            "weight": row.weight,
            "types": types_by_id[row.id],
        }
        for row in pokemon_list
    ]


@app.get("/pokemon/{pokemon_id}", response_model=PokemonDetail)
def get_pokemon(pokemon_id: int = Path(ge=1), db: Session = Depends(get_db)):
    """Get detailed information about a specific Pokémon."""
    # Get basic Pokémon data
    pokemon = db.execute(
        text("""
        SELECT p.id, p.name, p.height, p.weight, p.base_experience
        FROM pokemon p
        WHERE p.id = :pokemon_id
          AND NOT EXISTS (
              SELECT 1 FROM api_resource ar
              WHERE ar.resource_type = 'pokemon' AND ar.id = p.id AND ar.is_present = false
          )
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
          AND NOT EXISTS (
              SELECT 1 FROM api_resource ar
              WHERE ar.resource_type = 'type' AND ar.id = t.id AND ar.is_present = false
          )
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


@app.get("/analytics/top-pokemon", response_model=list[TopPokemon])
def get_top_pokemon(limit: int = Query(10, ge=1, le=100), db: Session = Depends(get_db)):
    """Get top Pokémon by total base stats."""
    analyzer = StatsAnalyzer(db_session=db)
    return analyzer.get_top_pokemon_by_total_base_stats(limit=limit).to_dict(orient="records")


@app.get("/analytics/type-distribution", response_model=list[TypeDistribution])
def get_type_distribution(db: Session = Depends(get_db)):
    """Get the distribution of Pokémon types."""
    analyzer = StatsAnalyzer(db_session=db)
    return analyzer.get_type_distribution().to_dict(orient="records")


@app.get("/analytics/pokemon/{pokemon_id}/counters", response_model=list[CounterType])
def get_pokemon_counters(
    pokemon_id: int = Path(ge=1),
    top_n: int = Query(5, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Get recommended counter types for a specific Pokémon."""
    if (
        db.execute(
            text("""
            SELECT 1 FROM pokemon p WHERE p.id = :id
              AND NOT EXISTS (
                  SELECT 1 FROM api_resource ar
                  WHERE ar.resource_type = 'pokemon' AND ar.id = p.id AND ar.is_present = false
              )
        """),
            {"id": pokemon_id},
        ).first()
        is None
    ):
        raise HTTPException(status_code=404, detail="Pokémon not found")
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
