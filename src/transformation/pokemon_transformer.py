"""Pokémon data transformer."""

import logging
from typing import Dict, Any, List

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PokemonTransformer:
    """Transforms raw Pokémon data from the API into a structured format for the database."""
    
    def transform_pokemon(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform raw Pokémon data from the API.
        
        Args:
            raw_data: Raw Pokémon data from the API.
            
        Returns:
            Transformed Pokémon data ready for database insertion.
        """
        species_details = raw_data.get('species_details', {})
        
        # Basic Pokémon data
        pokemon = {
            'id': raw_data['id'],
            'name': raw_data['name'],
            'height': raw_data['height'],
            'weight': raw_data['weight'],
            'base_experience': raw_data.get('base_experience'),
            'is_default': raw_data['is_default'],
            'order_num': raw_data.get('order')
        }
        
        # Stats
        stats = []
        for stat_data in raw_data.get('stats', []):
            stat = {
                'pokemon_id': raw_data['id'],
                'stat_name': stat_data['stat']['name'],
                'base_value': stat_data['base_stat']
            }
            stats.append(stat)
        
        # Types
        types = []
        for type_data in raw_data.get('types', []):
            type_entry = {
                'pokemon_id': raw_data['id'],
                'type_id': self._extract_id_from_url(type_data['type']['url']),
                'slot': type_data['slot']
            }
            types.append(type_entry)
        
        # Abilities
        abilities = []
        for ability_data in raw_data.get('abilities', []):
            ability = {
                'pokemon_id': raw_data['id'],
                'ability_id': self._extract_id_from_url(ability_data['ability']['url']),
                'is_hidden': ability_data['is_hidden'],
                'slot': ability_data['slot']
            }
            abilities.append(ability)
        
        # Moves
        moves = []
        for move_entry in raw_data.get('moves', []):
            move_id = self._extract_id_from_url(move_entry['move']['url'])
            
            for version_group_detail in move_entry.get('version_group_details', []):
                # Only include move data from the most recent games
                if version_group_detail['version_group']['name'] in ['sword-shield', 'sun-moon', 'x-y']:
                    move = {
                        'pokemon_id': raw_data['id'],
                        'move_id': move_id,
                        'level_learned_at': version_group_detail['level_learned_at'],
                        'learn_method': version_group_detail['move_learn_method']['name']
                    }
                    moves.append(move)
                    break  # Only add the move once for the most recent version
        
        transformed_data = {
            'pokemon': pokemon,
            'stats': stats,
            'types': types,
            'abilities': abilities,
            'moves': moves
        }
        
        logger.info(f"Transformed data for Pokémon: {pokemon['name']} (ID: {pokemon['id']})")
        return transformed_data
    
    def transform_pokemon_batch(self, raw_data_batch: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Transform a batch of raw Pokémon data from the API.
        
        Args:
            raw_data_batch: List of raw Pokémon data from the API.
            
        Returns:
            Dictionary with lists of transformed data ready for database insertion.
        """
        transformed_batch = {
            'pokemon': [],
            'stats': [],
            'types': [],
            'abilities': [],
            'moves': []
        }
        
        for raw_data in raw_data_batch:
            transformed_data = self.transform_pokemon(raw_data)
            
            transformed_batch['pokemon'].append(transformed_data['pokemon'])
            transformed_batch['stats'].extend(transformed_data['stats'])
            transformed_batch['types'].extend(transformed_data['types'])
            transformed_batch['abilities'].extend(transformed_data['abilities'])
            transformed_batch['moves'].extend(transformed_data['moves'])
        
        logger.info(f"Transformed batch of {len(raw_data_batch)} Pokémon")
        
        return transformed_batch
    
    def _extract_id_from_url(self, url: str) -> int:
        """Extract the ID from a PokéAPI URL."""
        parts = url.rstrip('/').split('/')
        return int(parts[-1])