"""Type data transformer."""

import logging
from typing import Dict, Any, List

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TypeTransformer:
    """Transforms raw Type data from the API into a structured format for the database."""
    
    def transform_type(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform raw Type data from the API.
        
        Args:
            raw_data: Raw Type data from the API.
            
        Returns:
            Transformed Type data ready for database insertion.
        """
        # Basic Type data
        type_data = {
            'id': raw_data['id'],
            'name': raw_data['name']
        }
        
        # Type effectiveness data
        effectiveness_entries = []
        
        # No damage to (0.0)
        for target in raw_data['damage_relations']['no_damage_to']:
            entry = {
                'attack_type_id': raw_data['id'],
                'defense_type_id': self._extract_id_from_url(target['url']),
                'effectiveness': 0.0
            }
            effectiveness_entries.append(entry)
        
        # Half damage to (0.5)
        for target in raw_data['damage_relations']['half_damage_to']:
            entry = {
                'attack_type_id': raw_data['id'],
                'defense_type_id': self._extract_id_from_url(target['url']),
                'effectiveness': 0.5
            }
            effectiveness_entries.append(entry)
        
        # Double damage to (2.0)
        for target in raw_data['damage_relations']['double_damage_to']:
            entry = {
                'attack_type_id': raw_data['id'],
                'defense_type_id': self._extract_id_from_url(target['url']),
                'effectiveness': 2.0
            }
            effectiveness_entries.append(entry)
        
        transformed_data = {
            'type': type_data,
            'effectiveness': effectiveness_entries
        }
        
        logger.info(f"Transformed data for Type: {type_data['name']} (ID: {type_data['id']})")
        return transformed_data
    
    def transform_type_batch(self, raw_data_batch: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Transform a batch of raw Type data from the API.
        
        Args:
            raw_data_batch: List of raw Type data from the API.
            
        Returns:
            Dictionary with lists of transformed data ready for database insertion.
        """
        transformed_batch = {
            'types': [],
            'effectiveness': []
        }
        
        for raw_data in raw_data_batch:
            transformed_data = self.transform_type(raw_data)
            
            transformed_batch['types'].append(transformed_data['type'])
            transformed_batch['effectiveness'].extend(transformed_data['effectiveness'])
        
        logger.info(f"Transformed batch of {len(raw_data_batch)} Types")
        
        return transformed_batch
    
    def _extract_id_from_url(self, url: str) -> int:
        """Extract the ID from a PokéAPI URL."""
        parts = url.rstrip('/').split('/')
        return int(parts[-1])