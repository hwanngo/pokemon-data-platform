"""Transforms for the relational-core mirror resources (raw JSON -> column dict).

Keys match the models in src/models/mirror.py. Nested {name, url} references are
reduced to either an integer id (via the URL) or a name string; nested arrays are
dropped (they live in the JSONB tail).
"""

from typing import Any

from src.transformation.utils import extract_id_from_url


def _ref_id(ref: dict[str, Any] | None) -> int | None:
    """Integer id from a {name, url} reference, or None."""
    return extract_id_from_url(ref["url"]) if ref else None


def _ref_name(ref: dict[str, Any] | None) -> str | None:
    """Name from a {name, url} reference, or None."""
    return ref["name"] if ref else None


def transform_region(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": raw["id"],
        "name": raw["name"],
        "main_generation_id": _ref_id(raw.get("main_generation")),
    }


def transform_generation(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": raw["id"],
        "name": raw["name"],
        "main_region_id": _ref_id(raw.get("main_region")),
        "main_region_name": _ref_name(raw.get("main_region")),
    }


def transform_version_group(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": raw["id"],
        "name": raw["name"],
        "order_num": raw.get("order"),
        "generation_id": _ref_id(raw.get("generation")),
    }


def transform_version(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": raw["id"],
        "name": raw["name"],
        "version_group_id": _ref_id(raw.get("version_group")),
    }


def transform_pokedex(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": raw["id"],
        "name": raw["name"],
        "is_main_series": raw["is_main_series"],
        "region_id": _ref_id(raw.get("region")),
    }


def transform_item_category(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": raw["id"],
        "name": raw["name"],
        "pocket_id": _ref_id(raw.get("pocket")),
    }


def transform_item(raw: dict[str, Any]) -> dict[str, Any]:
    sprites = raw.get("sprites") or {}
    return {
        "id": raw["id"],
        "name": raw["name"],
        "cost": raw.get("cost"),
        "fling_power": raw.get("fling_power"),
        "fling_effect_id": _ref_id(raw.get("fling_effect")),
        "category_id": _ref_id(raw.get("category")),
        "sprite_default": sprites.get("default"),
    }


def transform_berry(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": raw["id"],
        "name": raw["name"],
        "growth_time": raw.get("growth_time"),
        "max_harvest": raw.get("max_harvest"),
        "natural_gift_power": raw.get("natural_gift_power"),
        "size": raw.get("size"),
        "smoothness": raw.get("smoothness"),
        "soil_dryness": raw.get("soil_dryness"),
        "firmness": _ref_name(raw.get("firmness")),
        "natural_gift_type": _ref_name(raw.get("natural_gift_type")),
        "item_id": _ref_id(raw.get("item")),
    }


def transform_machine(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": raw["id"],
        "name": _ref_name(raw.get("item")),
        "item_id": _ref_id(raw.get("item")),
        "move_id": _ref_id(raw.get("move")),
        "version_group_id": _ref_id(raw.get("version_group")),
    }


def transform_location(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": raw["id"],
        "name": raw["name"],
        "region_id": _ref_id(raw.get("region")),
    }


def transform_location_area(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": raw["id"],
        "name": raw["name"],
        "game_index": raw.get("game_index"),
        "location_id": _ref_id(raw.get("location")),
    }


def transform_pokemon_species(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": raw["id"],
        "name": raw["name"],
        "order_num": raw.get("order"),
        "gender_rate": raw.get("gender_rate"),
        "capture_rate": raw.get("capture_rate"),
        "base_happiness": raw.get("base_happiness"),
        "hatch_counter": raw.get("hatch_counter"),
        "is_baby": raw.get("is_baby"),
        "is_legendary": raw.get("is_legendary"),
        "is_mythical": raw.get("is_mythical"),
        "has_gender_differences": raw.get("has_gender_differences"),
        "forms_switchable": raw.get("forms_switchable"),
        "generation_id": _ref_id(raw.get("generation")),
        "evolution_chain_id": _ref_id(raw.get("evolution_chain")),
        "evolves_from_species_id": _ref_id(raw.get("evolves_from_species")),
        "growth_rate": _ref_name(raw.get("growth_rate")),
        "color": _ref_name(raw.get("color")),
        "shape": _ref_name(raw.get("shape")),
        "habitat": _ref_name(raw.get("habitat")),
    }


def transform_egg_group(raw: dict[str, Any]) -> dict[str, Any]:
    return {"id": raw["id"], "name": raw["name"]}


def transform_nature(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": raw["id"],
        "name": raw["name"],
        "decreased_stat": _ref_name(raw.get("decreased_stat")),
        "increased_stat": _ref_name(raw.get("increased_stat")),
        "hates_flavor": _ref_name(raw.get("hates_flavor")),
        "likes_flavor": _ref_name(raw.get("likes_flavor")),
    }


def transform_contest_type(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": raw["id"],
        "name": raw["name"],
        "berry_flavor": _ref_name(raw.get("berry_flavor")),
    }
