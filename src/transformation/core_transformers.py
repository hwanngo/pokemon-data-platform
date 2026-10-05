"""Transforms for the core entities (pokemon, type, ability, move) on the mirror
engine. Each returns a table-keyed ``dict[str, list[dict]]`` so a single API
response can fan out to several tables (e.g. pokemon -> 5 tables)."""

from typing import Any

from src.transformation.utils import extract_id_from_url


def transform_ability(raw: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    effect_entries = raw.get("effect_entries", [])
    english: dict[str, Any] = next((e for e in effect_entries if e["language"]["name"] == "en"), {})
    names = raw.get("names", [])
    name = next((e["name"] for e in names if e["language"]["name"] == "en"), raw["name"])
    return {
        "abilities": [
            {
                "id": raw["id"],
                "name": name,
                "effect_text": english.get("effect", ""),
                "short_effect": english.get("short_effect", ""),
            }
        ]
    }


def transform_move(raw: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    type_info = raw.get("type") or {}
    damage_class = raw.get("damage_class") or {}
    return {
        "moves": [
            {
                "id": raw["id"],
                "name": raw["name"],
                "power": raw.get("power"),
                "pp": raw.get("pp"),
                "accuracy": raw.get("accuracy"),
                "type_id": extract_id_from_url(type_info["url"]) if type_info.get("url") else None,
                "damage_class": damage_class.get("name"),
            }
        ]
    }


def transform_type(raw: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    dr = raw["damage_relations"]
    effectiveness = []
    for multiplier, key in (
        (0.0, "no_damage_to"),
        (0.5, "half_damage_to"),
        (2.0, "double_damage_to"),
    ):
        for target in dr[key]:
            effectiveness.append(
                {
                    "attack_type_id": raw["id"],
                    "defense_type_id": extract_id_from_url(target["url"]),
                    "effectiveness": multiplier,
                }
            )
    return {
        "types": [{"id": raw["id"], "name": raw["name"]}],
        "type_effectiveness": effectiveness,
    }


def transform_pokemon(raw: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    pid = raw["id"]
    pokemon = {
        "id": pid,
        "name": raw["name"],
        "height": raw["height"],
        "weight": raw["weight"],
        "base_experience": raw.get("base_experience"),
        "is_default": raw["is_default"],
        "order_num": raw.get("order"),
        "species_id": extract_id_from_url(raw["species"]["url"])
        if (raw.get("species") or {}).get("url")
        else None,
    }
    stats = [
        {"pokemon_id": pid, "stat_name": s["stat"]["name"], "base_value": s["base_stat"]}
        for s in raw.get("stats", [])
    ]
    types = [
        {"pokemon_id": pid, "type_id": extract_id_from_url(t["type"]["url"]), "slot": t["slot"]}
        for t in raw.get("types", [])
    ]
    abilities = [
        {
            "pokemon_id": pid,
            "ability_id": extract_id_from_url(a["ability"]["url"]),
            "is_hidden": a["is_hidden"],
            "slot": a["slot"],
        }
        for a in raw.get("abilities", [])
    ]

    # Keep source version and level provenance; consumers select a game explicitly.
    moves = []
    seen_moves: set[tuple[int, int | None, str, int]] = set()
    for move_entry in raw.get("moves", []):
        move_id = extract_id_from_url(move_entry["move"]["url"])
        for d in move_entry.get("version_group_details", []):
            method = d["move_learn_method"]["name"]
            vg_url = d["version_group"].get("url")
            if not vg_url:
                raise ValueError("move version group URL is required for provenance")
            vg_id = extract_id_from_url(vg_url)
            level = d["level_learned_at"]
            key = (move_id, vg_id, method, level)
            if key in seen_moves:
                continue
            seen_moves.add(key)
            moves.append(
                {
                    "pokemon_id": pid,
                    "move_id": move_id,
                    "version_group_id": vg_id,
                    "level_learned_at": level,
                    "learn_method": method,
                }
            )

    return {
        "pokemon": [pokemon],
        "pokemon_stats": stats,
        "pokemon_types": types,
        "pokemon_abilities": abilities,
        "pokemon_moves": moves,
    }
