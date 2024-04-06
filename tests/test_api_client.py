"""Tests for the PokéAPI client."""

import unittest
import os
import tempfile
from pathlib import Path

from src.ingestion.api_client import PokemonApiClient

class TestPokemonApiClient(unittest.TestCase):
    """Test cases for the PokéAPI client."""
    
    def setUp(self):
        """Set up test case."""
        # Create a temporary directory for cache
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache_dir = self.temp_dir.name
        
        # Initialize the API client with a test rate limit
        self.api_client = PokemonApiClient(
            base_url="https://pokeapi.co/api/v2",
            rate_limit=20,
            cache_dir=self.cache_dir
        )
    
    def tearDown(self):
        """Clean up after test case."""
        self.temp_dir.cleanup()
    
    def test_get_pokemon(self):
        """Test fetching a Pokémon from the API."""
        # Fetch a Pokémon
        data = self.api_client.get("pokemon/1")
        
        # Check that the response contains expected fields
        self.assertEqual(data["id"], 1)
        self.assertEqual(data["name"], "bulbasaur")
        self.assertIn("types", data)
        self.assertIn("stats", data)
    
    def test_get_type(self):
        """Test fetching a type from the API."""
        # Fetch a type
        data = self.api_client.get("type/1")
        
        # Check that the response contains expected fields
        self.assertEqual(data["id"], 1)
        self.assertEqual(data["name"], "normal")
        self.assertIn("damage_relations", data)
    
    def test_caching(self):
        """Test that responses are cached."""
        # Fetch a Pokémon
        self.api_client.get("pokemon/2")
        
        # Check that the cache file exists
        cache_path = Path(self.cache_dir) / "pokemon_2.json"
        self.assertTrue(cache_path.exists())
        
        # Fetch again to use cache
        self.api_client.get("pokemon/2")

if __name__ == "__main__":
    unittest.main()