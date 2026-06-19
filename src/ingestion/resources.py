"""Registry of PokéAPI resources for the generic mirror engine.

Each ResourceSpec declares an endpoint, its storage mode (a relational table or
the JSONB tail), and load-order dependencies. Add a resource by adding an entry
here (plus a model + transform for relational ones).
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from src.models import mirror as m
from src.models.ability import Ability, PokemonAbility
from src.models.move import Move, PokemonMove
from src.models.pokemon import Pokemon, PokemonStat
from src.models.type import PokemonType, Type, TypeEffectiveness
from src.transformation import core_transformers as ct
from src.transformation import mirror_transformers as t


@dataclass(frozen=True)
class TableSpec:
    """One output table of a (possibly fan-out) relational resource."""

    key: str  # key in the transform's output dict
    model: type  # SQLAlchemy model
    conflict: tuple[str, ...] = ("id",)  # ON CONFLICT target (a unique index)


@dataclass(frozen=True)
class ResourceSpec:
    name: str  # PokéAPI endpoint slug, e.g. "version-group"
    mode: str = "jsonb"  # "jsonb" | "relational"
    model: type | None = None  # single-table relational
    transform: Callable[[dict[str, Any]], Any] | None = None  # raw -> row | {table: [rows]}
    tables: tuple[TableSpec, ...] = field(default_factory=tuple)  # fan-out (multi-table)
    depends_on: tuple[str, ...] = field(default_factory=tuple)


def _rel(name, model, transform, depends_on=()):
    """Single-table relational resource (transform returns one row dict)."""
    return ResourceSpec(
        name, "relational", model=model, transform=transform, depends_on=tuple(depends_on)
    )


def _fanout(name, tables, transform, depends_on=()):
    """Multi-table relational resource (transform returns {table: [rows]})."""
    return ResourceSpec(
        name, "relational", transform=transform, tables=tuple(tables), depends_on=tuple(depends_on)
    )


def _json(name):
    return ResourceSpec(name, "jsonb")


# --- Core entities (fan-out: one API response -> several tables) ------------
_CORE = [
    _fanout("ability", [TableSpec("abilities", Ability)], ct.transform_ability),
    _fanout(
        "type",
        [
            TableSpec("types", Type),
            TableSpec(
                "type_effectiveness", TypeEffectiveness, ("attack_type_id", "defense_type_id")
            ),
        ],
        ct.transform_type,
    ),
    _fanout("move", [TableSpec("moves", Move)], ct.transform_move, ["type"]),
    _fanout(
        "pokemon",
        [
            TableSpec("pokemon", Pokemon),
            TableSpec("pokemon_stats", PokemonStat, ("pokemon_id", "stat_name")),
            TableSpec("pokemon_types", PokemonType, ("pokemon_id", "slot")),
            TableSpec("pokemon_abilities", PokemonAbility, ("pokemon_id", "ability_id")),
            TableSpec("pokemon_moves", PokemonMove, ("pokemon_id", "move_id", "learn_method")),
        ],
        ct.transform_pokemon,
        ["type", "ability", "move"],
    ),
]


# --- Relational core --------------------------------------------------------
_RELATIONAL = [
    _rel("region", m.Region, t.transform_region),
    _rel("generation", m.Generation, t.transform_generation),
    _rel("version-group", m.VersionGroup, t.transform_version_group, ["generation"]),
    _rel("version", m.Version, t.transform_version, ["version-group"]),
    _rel("pokedex", m.Pokedex, t.transform_pokedex, ["region"]),
    _rel("item-category", m.ItemCategory, t.transform_item_category),
    _rel("item", m.Item, t.transform_item, ["item-category"]),
    _rel("berry", m.Berry, t.transform_berry, ["item"]),
    _rel("machine", m.Machine, t.transform_machine, ["item", "version-group"]),
    _rel("location", m.Location, t.transform_location, ["region"]),
    _rel("location-area", m.LocationArea, t.transform_location_area, ["location"]),
    _rel("pokemon-species", m.PokemonSpecies, t.transform_pokemon_species, ["generation"]),
    _rel("egg-group", m.EggGroup, t.transform_egg_group),
    _rel("nature", m.Nature, t.transform_nature),
    _rel("contest-type", m.ContestType, t.transform_contest_type),
]

# --- JSONB tail (everything else across the 8 categories + utility) ---------
_JSONB_NAMES = [
    # Berries / Contests / Encounters / Evolution
    "berry-firmness",
    "berry-flavor",
    "contest-effect",
    "super-contest-effect",
    "encounter-method",
    "encounter-condition",
    "encounter-condition-value",
    "evolution-chain",
    "evolution-trigger",
    # Items
    "item-attribute",
    "item-fling-effect",
    "item-pocket",
    # Locations
    "pal-park-area",
    # Moves (lookups; the `move` resource itself is a core fan-out resource above)
    "move-ailment",
    "move-battle-style",
    "move-category",
    "move-damage-class",
    "move-learn-method",
    "move-target",
    # Pokémon (lookups; pokemon/types/abilities are core fan-out resources above)
    "characteristic",
    "gender",
    "growth-rate",
    "pokeathlon-stat",
    "pokemon-color",
    "pokemon-form",
    "pokemon-habitat",
    "pokemon-shape",
    "stat",
    # Utility
    "language",
]

RESOURCES: list[ResourceSpec] = _CORE + _RELATIONAL + [_json(n) for n in _JSONB_NAMES]

_BY_NAME = {s.name: s for s in RESOURCES}


def get_resource(name: str) -> ResourceSpec:
    return _BY_NAME[name]


def ordered_resources(
    only: list[str] | None = None, expand_deps: bool = True
) -> list[ResourceSpec]:
    """Return specs in dependency order (parents before children).

    Args:
        only: resource names to include (None = all).
        expand_deps: if True (the CLI default), the selection is expanded to
            include transitive dependencies so relational FKs resolve. The DAG
            sets this False — it wires task dependencies itself.
    """
    if only is None:
        selected = set(_BY_NAME)
    elif expand_deps:
        selected = set()
        stack = list(only)
        while stack:
            name = stack.pop()
            if name in selected:
                continue
            if name not in _BY_NAME:
                raise KeyError(f"Unknown resource: {name}")
            selected.add(name)
            stack.extend(_BY_NAME[name].depends_on)
    else:
        for name in only:
            if name not in _BY_NAME:
                raise KeyError(f"Unknown resource: {name}")
        selected = set(only)

    # Topological sort (Kahn) over the selected sub-graph; deps outside the
    # selection are ignored for ordering (the caller guarantees they exist).
    ordered: list[ResourceSpec] = []
    done: set[str] = set()
    remaining = set(selected)
    while remaining:
        ready = sorted(
            n for n in remaining if all(d in done for d in _BY_NAME[n].depends_on if d in selected)
        )
        if not ready:  # cycle (shouldn't happen — circular refs are bare ids)
            raise ValueError(f"Dependency cycle among: {sorted(remaining)}")
        for n in ready:
            ordered.append(_BY_NAME[n])
            done.add(n)
            remaining.discard(n)
    return ordered
