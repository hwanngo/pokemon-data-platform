"""Module for fetching ability data from the PokeAPI."""
from typing import List, Dict, Any
from src.ingestion.api_client import PokemonApiClient

class AbilityFetcher:
    """Class for fetching ability data from the PokeAPI."""

    def __init__(self):
        """Initialize the AbilityFetcher with an APIClient instance."""
        self.api_client = PokemonApiClient()

    def fetch_ability(self, ability_id: int) -> Dict[str, Any]:
        """Fetch a single ability by its ID."""
        return self.api_client.get(f"ability/{ability_id}")

    def fetch_all_abilities(self) -> List[Dict[str, Any]]:
        """Fetch all abilities from the API."""
        # First get the total count of abilities
        ability_list = self.api_client.get("ability")
        total_abilities = ability_list["count"]
        
        abilities = []
        for ability_id in range(1, total_abilities + 1):
            try:
                ability_data = self.fetch_ability(ability_id)
                abilities.append(ability_data)
            except Exception as e:
                print(f"Error fetching ability {ability_id}: {e}")
                continue
        
        return abilities