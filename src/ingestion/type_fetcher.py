"""Type data collector from PokéAPI."""

import logging
from typing import List, Dict, Any, Optional

from src.ingestion.api_client import PokemonApiClient

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TypeFetcher:
    """Fetches type data from the PokéAPI."""
    
    def __init__(self, api_client: Optional[PokemonApiClient] = None):
        """
        Initialize the type fetcher.
        
        Args:
            api_client: The PokéAPI client to use, or create a new one if None.
        """
        self.api_client = api_client or PokemonApiClient()
        logger.info("Initialized TypeFetcher")
    
    def fetch_type_list(self) -> List[Dict[str, Any]]:
        """
        Fetch a list of all Pokémon types.
        
        Returns:
            List of types with basic information.
        """
        endpoint = "type"
        response = self.api_client.get(endpoint)
        
        logger.info(f"Fetched list of {len(response['results'])} types")
        return response['results']
    
    def fetch_type_detail(self, identifier: str) -> Dict[str, Any]:
        """
        Fetch detailed information about a specific type, including effectiveness.
        
        Args:
            identifier: The name or ID of the type.
            
        Returns:
            Detailed information about the type.
        """
        endpoint = f"type/{identifier}"
        type_data = self.api_client.get(endpoint)
        
        logger.info(f"Fetched detailed data for type: {type_data['name']} (ID: {type_data['id']})")
        return type_data
    
    def fetch_all_types_with_effectiveness(self) -> List[Dict[str, Any]]:
        """
        Fetch all types with their damage relations.
        
        Returns:
            List of all types with effectiveness data.
        """
        types_list = self.fetch_type_list()
        types_data = []
        
        for type_info in types_list:
            try:
                type_name = type_info['name']
                type_data = self.fetch_type_detail(type_name)
                types_data.append(type_data)
            except Exception as e:
                logger.error(f"Error fetching type {type_info['name']}: {e}")
        
        logger.info(f"Fetched effectiveness data for {len(types_data)} types")
        return types_data
    
    def build_effectiveness_matrix(self) -> Dict[str, Dict[str, float]]:
        """
        Build a matrix of type effectiveness.
        
        Returns:
            Dictionary mapping attacking types to defending types with effectiveness values.
        """
        types_data = self.fetch_all_types_with_effectiveness()
        effectiveness_matrix = {}
        
        for attacking_type in types_data:
            attack_name = attacking_type['name']
            effectiveness_matrix[attack_name] = {}
            
            # Set default effectiveness (1.0)
            for defending_type in types_data:
                defense_name = defending_type['name']
                effectiveness_matrix[attack_name][defense_name] = 1.0
            
            # Set no effect (0.0)
            for no_effect in attacking_type['damage_relations']['no_damage_to']:
                effectiveness_matrix[attack_name][no_effect['name']] = 0.0
            
            # Set not very effective (0.5)
            for not_effective in attacking_type['damage_relations']['half_damage_to']:
                effectiveness_matrix[attack_name][not_effective['name']] = 0.5
            
            # Set super effective (2.0)
            for super_effective in attacking_type['damage_relations']['double_damage_to']:
                effectiveness_matrix[attack_name][super_effective['name']] = 2.0
        
        logger.info("Built type effectiveness matrix")
        return effectiveness_matrix