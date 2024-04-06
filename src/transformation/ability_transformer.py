"""Module for transforming ability data into database format."""
from typing import List, Dict, Any

class AbilityTransformer:
    """Class for transforming ability data into database format."""

    def transform_ability(self, raw_ability: Dict[str, Any]) -> Dict[str, Any]:
        """Transform a single ability entry."""
        # Get English description
        effect_entries = raw_ability.get("effect_entries", [])
        effect = next((entry["effect"] for entry in effect_entries 
                      if entry["language"]["name"] == "en"), "")
        
        # Get English flavor text
        flavor_entries = raw_ability.get("flavor_text_entries", [])
        flavor_text = next((entry["flavor_text"] for entry in flavor_entries 
                          if entry["language"]["name"] == "en"), "")

        # Get English name
        names = raw_ability.get("names", [])
        name = next((entry["name"] for entry in names 
                    if entry["language"]["name"] == "en"), raw_ability["name"])

        return {
            "id": raw_ability["id"],
            "name": name,
            "effect": effect,
            "flavor_text": flavor_text,
            "is_main_series": raw_ability["is_main_series"]
        }

    def transform_ability_batch(self, raw_abilities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Transform a batch of ability data."""
        return [self.transform_ability(ability) for ability in raw_abilities]