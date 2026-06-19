"""Parity tests for the core entity transforms (pokemon/type/ability/move) that
moved onto the mirror engine as table-keyed fan-out functions."""

from src.transformation.core_transformers import (
    transform_ability,
    transform_move,
    transform_pokemon,
    transform_type,
)

BASE = "https://pokeapi.co/api/v2"


def test_transform_ability_picks_english_and_keys_table():
    out = transform_ability(
        {
            "id": 1,
            "name": "stench",
            "names": [
                {"language": {"name": "ja"}, "name": "あくしゅう"},
                {"language": {"name": "en"}, "name": "Stench"},
            ],
            "effect_entries": [
                {"language": {"name": "en"}, "effect": "Long.", "short_effect": "Short."}
            ],
        }
    )
    assert out == {
        "abilities": [{"id": 1, "name": "Stench", "effect_text": "Long.", "short_effect": "Short."}]
    }


def test_transform_move_handles_nulls():
    out = transform_move(
        {
            "id": 2,
            "name": "growl",
            "power": None,
            "pp": 40,
            "accuracy": None,
            "type": None,
            "damage_class": None,
        }
    )
    assert out["moves"][0]["power"] is None
    assert out["moves"][0]["type_id"] is None
    assert out["moves"][0]["damage_class"] is None


def test_transform_type_maps_damage_relations():
    out = transform_type(
        {
            "id": 1,
            "name": "normal",
            "damage_relations": {
                "no_damage_to": [{"url": f"{BASE}/type/8/"}],
                "half_damage_to": [{"url": f"{BASE}/type/6/"}],
                "double_damage_to": [],
            },
        }
    )
    assert out["types"] == [{"id": 1, "name": "normal"}]
    eff = {(e["defense_type_id"], e["effectiveness"]) for e in out["type_effectiveness"]}
    assert eff == {(8, 0.0), (6, 0.5)}


def test_transform_pokemon_fans_out_to_five_tables():
    raw = {
        "id": 1,
        "name": "bulbasaur",
        "height": 7,
        "weight": 69,
        "base_experience": 64,
        "is_default": True,
        "order": 1,
        "stats": [{"stat": {"name": "hp"}, "base_stat": 45}],
        "types": [{"slot": 1, "type": {"url": f"{BASE}/type/12/"}}],
        "abilities": [{"is_hidden": False, "slot": 1, "ability": {"url": f"{BASE}/ability/65/"}}],
        "moves": [
            {
                "move": {"url": f"{BASE}/move/33/"},
                "version_group_details": [
                    {
                        "version_group": {"name": "scarlet-violet"},
                        "level_learned_at": 1,
                        "move_learn_method": {"name": "level-up"},
                    },
                    {
                        "version_group": {"name": "scarlet-violet"},
                        "level_learned_at": 0,
                        "move_learn_method": {"name": "machine"},
                    },
                ],
            }
        ],
    }
    out = transform_pokemon(raw)
    assert out["pokemon"][0]["id"] == 1 and out["pokemon"][0]["order_num"] == 1
    assert out["pokemon_stats"] == [{"pokemon_id": 1, "stat_name": "hp", "base_value": 45}]
    assert out["pokemon_types"] == [{"pokemon_id": 1, "type_id": 12, "slot": 1}]
    assert out["pokemon_abilities"][0]["ability_id"] == 65
    # both learn methods kept for the chosen version group
    assert {m["learn_method"] for m in out["pokemon_moves"]} == {"level-up", "machine"}
