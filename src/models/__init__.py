"""SQLAlchemy models.

Importing this package registers every model on ``Base.metadata``, so a single
``import src.models`` (or ``from src.models import ...``) is enough before any
``Base.metadata.create_all`` — callers don't have to import each module by hand.
"""

from src.models.ability import Ability, PokemonAbility
from src.models.api_resource import ApiResource
from src.models.base import Base, SessionLocal, get_db, session_scope
from src.models.mirror import (
    Berry,
    ContestType,
    EggGroup,
    Generation,
    Item,
    ItemCategory,
    Location,
    LocationArea,
    Machine,
    Nature,
    Pokedex,
    PokemonSpecies,
    Region,
    Version,
    VersionGroup,
)
from src.models.move import Move, PokemonMove
from src.models.pokemon import Pokemon, PokemonStat
from src.models.type import PokemonType, Type, TypeEffectiveness

__all__ = [
    "Base",
    "SessionLocal",
    "get_db",
    "session_scope",
    "Ability",
    "PokemonAbility",
    "ApiResource",
    "Berry",
    "ContestType",
    "EggGroup",
    "Generation",
    "Item",
    "ItemCategory",
    "Location",
    "LocationArea",
    "Machine",
    "Nature",
    "Pokedex",
    "PokemonSpecies",
    "Region",
    "Version",
    "VersionGroup",
    "Move",
    "PokemonMove",
    "Pokemon",
    "PokemonStat",
    "PokemonType",
    "Type",
    "TypeEffectiveness",
]
