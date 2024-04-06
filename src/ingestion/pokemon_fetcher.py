"""Pokémon data collector from PokéAPI."""

import logging
from typing import List, Dict, Any, Optional

from src.ingestion.api_client import PokemonApiClient

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PokemonFetcher:
    """Fetches Pokémon data from the PokéAPI."""
    
    def __init__(self, api_client: Optional[PokemonApiClient] = None):
        """
        Initialize the Pokémon fetcher.
        
        Args:
            api_client: The PokéAPI client to use, or create a new one if None.
        """
        self.api_client = api_client or PokemonApiClient()
        logger.info("Initialized PokemonFetcher")
    
    def fetch_pokemon_list(self, limit: int = 151, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Fetch a list of Pokémon with basic information.
        
        Args:
            limit: Maximum number of Pokémon to fetch.
            offset: Starting index for pagination.
            
        Returns:
            List of Pokémon with basic information.
        """
        endpoint = f"pokemon?limit={limit}&offset={offset}"
        response = self.api_client.get(endpoint)
        
        logger.info(f"Fetched list of {len(response['results'])} Pokémon")
        return response['results']
    
    def fetch_pokemon_detail(self, identifier: str) -> Dict[str, Any]:
        """
        Fetch detailed information about a specific Pokémon.
        
        Args:
            identifier: The name or ID of the Pokémon.
            
        Returns:
            Detailed information about the Pokémon.
        """
        endpoint = f"pokemon/{identifier}"
        pokemon_data = self.api_client.get(endpoint)
        
        # Fetch additional species data
        species_url = pokemon_data['species']['url']
        species_endpoint = species_url.split('/api/v2/')[1]
        species_data = self.api_client.get(species_endpoint)
        
        # Combine the data
        pokemon_data['species_details'] = species_data
        
        logger.info(f"Fetched detailed data for Pokémon: {pokemon_data['name']} (ID: {pokemon_data['id']})")
        return pokemon_data
    
    def fetch_pokemon_batch(self, start_id: int = 1, end_id: int = 151) -> List[Dict[str, Any]]:
        """
        Fetch detailed information for a batch of Pokémon by ID range.
        
        Args:
            start_id: The ID of the first Pokémon to fetch.
            end_id: The ID of the last Pokémon to fetch.
            
        Returns:
            List of detailed Pokémon data.
        """
        pokemon_data = []
        
        for pokemon_id in range(start_id, end_id + 1):
            try:
                pokemon = self.fetch_pokemon_detail(str(pokemon_id))
                pokemon_data.append(pokemon)
            except Exception as e:
                logger.error(f"Error fetching Pokémon ID {pokemon_id}: {e}")
        
        logger.info(f"Fetched data for {len(pokemon_data)} Pokémon (IDs {start_id}-{end_id})")
        return pokemon_data

    def fetch_all_pokemon(self) -> List[Dict[str, Any]]:
        """
        Fetch detailed information for all available Pokémon.
        
        This method first gets the count of all Pokémon from the API,
        then fetches all Pokémon in batches to avoid memory issues.
        
        Returns:
            List of detailed Pokémon data.
        """
        # First, get count of all Pokémon from the API
        endpoint = "pokemon"
        response = self.api_client.get(endpoint)
        total_pokemon = response.get('count', 0)
        
        logger.info(f"Found {total_pokemon} total Pokémon in the API")
        
        # Fetch all Pokémon in batches to avoid memory issues
        all_pokemon_data = []
        batch_size = 100  # Process in batches of 100 Pokémon
        
        for offset in range(0, total_pokemon, batch_size):
            # Get batch of Pokémon basic info
            batch_limit = min(batch_size, total_pokemon - offset)
            pokemon_list = self.fetch_pokemon_list(limit=batch_limit, offset=offset)
            
            logger.info(f"Processing batch of {len(pokemon_list)} Pokémon (offset: {offset})")
            
            # Fetch detailed data for each Pokémon in the batch
            for pokemon in pokemon_list:
                try:
                    # Extract the name from the basic info
                    name = pokemon['name']
                    detailed_data = self.fetch_pokemon_detail(name)
                    all_pokemon_data.append(detailed_data)
                except Exception as e:
                    logger.error(f"Error fetching Pokémon {pokemon.get('name', 'unknown')}: {e}")
        
        logger.info(f"Fetched data for {len(all_pokemon_data)} out of {total_pokemon} total Pokémon")
        return all_pokemon_data