"""Tests for the Pokémon data transformer."""

import unittest
from src.transformation.pokemon_transformer import PokemonTransformer

class TestPokemonTransformer(unittest.TestCase):
    """Test cases for the Pokémon data transformer."""
    
    def setUp(self):
        """Set up test case."""
        self.transformer = PokemonTransformer()
        
        # Sample raw Pokémon data to transform
        self.sample_pokemon = {
            "id": 25,
            "name": "pikachu",
            "height": 4,
            "weight": 60,
            "base_experience": 112,
            "is_default": True,
            "order": 35,
            "stats": [
                {
                    "base_stat": 35,
                    "effort": 0,
                    "stat": {
                        "name": "hp",
                        "url": "https://pokeapi.co/api/v2/stat/1/"
                    }
                },
                {
                    "base_stat": 55,
                    "effort": 0,
                    "stat": {
                        "name": "attack",
                        "url": "https://pokeapi.co/api/v2/stat/2/"
                    }
                }
            ],
            "types": [
                {
                    "slot": 1,
                    "type": {
                        "name": "electric",
                        "url": "https://pokeapi.co/api/v2/type/13/"
                    }
                }
            ],
            "abilities": [
                {
                    "ability": {
                        "name": "static",
                        "url": "https://pokeapi.co/api/v2/ability/9/"
                    },
                    "is_hidden": False,
                    "slot": 1
                },
                {
                    "ability": {
                        "name": "lightning-rod",
                        "url": "https://pokeapi.co/api/v2/ability/31/"
                    },
                    "is_hidden": True,
                    "slot": 3
                }
            ],
            "moves": [
                {
                    "move": {
                        "name": "thunderbolt",
                        "url": "https://pokeapi.co/api/v2/move/85/"
                    },
                    "version_group_details": [
                        {
                            "level_learned_at": 0,
                            "move_learn_method": {
                                "name": "machine",
                                "url": "https://pokeapi.co/api/v2/move-learn-method/4/"
                            },
                            "version_group": {
                                "name": "sword-shield",
                                "url": "https://pokeapi.co/api/v2/version-group/20/"
                            }
                        }
                    ]
                }
            ],
            "species_details": {
                "id": 25,
                "name": "pikachu",
                "order": 36
            }
        }
    
    def test_transform_pokemon(self):
        """Test transforming a Pokémon."""
        # Transform the sample Pokémon
        transformed = self.transformer.transform_pokemon(self.sample_pokemon)
        
        # Check basic Pokémon data
        self.assertEqual(transformed["pokemon"]["id"], 25)
        self.assertEqual(transformed["pokemon"]["name"], "pikachu")
        self.assertEqual(transformed["pokemon"]["height"], 4)
        self.assertEqual(transformed["pokemon"]["weight"], 60)
        
        # Check stats
        self.assertEqual(len(transformed["stats"]), 2)
        self.assertEqual(transformed["stats"][0]["stat_name"], "hp")
        self.assertEqual(transformed["stats"][0]["base_value"], 35)
        
        # Check types
        self.assertEqual(len(transformed["types"]), 1)
        self.assertEqual(transformed["types"][0]["type_id"], 13)  # electric type
        
        # Check abilities
        self.assertEqual(len(transformed["abilities"]), 2)
        self.assertEqual(transformed["abilities"][0]["ability_id"], 9)  # static ability
        self.assertFalse(transformed["abilities"][0]["is_hidden"])
        self.assertEqual(transformed["abilities"][1]["ability_id"], 31)  # lightning-rod ability
        self.assertTrue(transformed["abilities"][1]["is_hidden"])
        
        # Check moves
        self.assertEqual(len(transformed["moves"]), 1)
        self.assertEqual(transformed["moves"][0]["move_id"], 85)  # thunderbolt move
        self.assertEqual(transformed["moves"][0]["learn_method"], "machine")
    
    def test_transform_pokemon_batch(self):
        """Test transforming a batch of Pokémon."""
        # Create a batch with just one Pokémon for simplicity
        batch = [self.sample_pokemon]
        
        # Transform the batch
        transformed_batch = self.transformer.transform_pokemon_batch(batch)
        
        # Check that the batch has the expected structure
        self.assertIn("pokemon", transformed_batch)
        self.assertIn("stats", transformed_batch)
        self.assertIn("types", transformed_batch)
        self.assertIn("abilities", transformed_batch)
        self.assertIn("moves", transformed_batch)
        
        # Check counts
        self.assertEqual(len(transformed_batch["pokemon"]), 1)
        self.assertEqual(len(transformed_batch["stats"]), 2)
        self.assertEqual(len(transformed_batch["types"]), 1)
        self.assertEqual(len(transformed_batch["abilities"]), 2)
        self.assertEqual(len(transformed_batch["moves"]), 1)

if __name__ == "__main__":
    unittest.main()