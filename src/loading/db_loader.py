"""Database loader for Pokémon data."""

import logging
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from src.models.base import get_db
from src.models.pokemon import Pokemon, PokemonStat
from src.models.type import Type, PokemonType, TypeEffectiveness
from src.models.ability import Ability, PokemonAbility
from src.models.move import Move, PokemonMove

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseLoader:
    """Loads transformed Pokémon data into the database."""
    
    def __init__(self, db_session: Optional[Session] = None):
        """
        Initialize the DatabaseLoader.
        
        Args:
            db_session: SQLAlchemy database session. If None, a new one will be created.
        """
        self.db = db_session if db_session else next(get_db())
        logger.info("Initialized DatabaseLoader")
    
    def load_pokemon(self, pokemon_data: Dict[str, Any]) -> Pokemon:
        """
        Load a Pokémon into the database.
        
        Args:
            pokemon_data: Transformed Pokémon data.
            
        Returns:
            The Pokémon object that was loaded.
        """
        try:
            # Check if the Pokémon already exists
            existing_pokemon = self.db.query(Pokemon).filter(Pokemon.id == pokemon_data['id']).first()
            
            if existing_pokemon:
                logger.info(f"Pokémon {pokemon_data['name']} (ID: {pokemon_data['id']}) already exists, updating")
                
                # Update existing Pokémon
                for key, value in pokemon_data.items():
                    setattr(existing_pokemon, key, value)
                
                pokemon = existing_pokemon
            else:
                # Create new Pokémon
                pokemon = Pokemon(**pokemon_data)
                self.db.add(pokemon)
                
            self.db.commit()
            logger.info(f"Loaded Pokémon {pokemon_data['name']} (ID: {pokemon_data['id']})")
            return pokemon
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error loading Pokémon {pokemon_data.get('name')}: {e}")
            raise
    
    def load_pokemon_stats(self, stats_data: List[Dict[str, Any]]) -> List[PokemonStat]:
        """
        Load Pokémon stats into the database.
        
        Args:
            stats_data: List of transformed stat data.
            
        Returns:
            The list of PokemonStat objects that were loaded.
        """
        stats = []
        
        try:
            for stat_data in stats_data:
                # Check if the stat already exists
                existing_stat = self.db.query(PokemonStat).filter(
                    PokemonStat.pokemon_id == stat_data['pokemon_id'],
                    PokemonStat.stat_name == stat_data['stat_name']
                ).first()
                
                if existing_stat:
                    # Update existing stat
                    existing_stat.base_value = stat_data['base_value']
                    stats.append(existing_stat)
                else:
                    # Create new stat
                    stat = PokemonStat(**stat_data)
                    self.db.add(stat)
                    stats.append(stat)
            
            self.db.commit()
            logger.info(f"Loaded {len(stats)} Pokémon stats")
            return stats
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error loading Pokémon stats: {e}")
            raise
    
    def load_types(self, types_data: List[Dict[str, Any]]) -> List[Type]:
        """
        Load types into the database.
        
        Args:
            types_data: List of transformed type data.
            
        Returns:
            The list of Type objects that were loaded.
        """
        types = []
        
        try:
            for type_data in types_data:
                # Check if the type already exists
                existing_type = self.db.query(Type).filter(Type.id == type_data['id']).first()
                
                if existing_type:
                    # Update existing type
                    existing_type.name = type_data['name']
                    types.append(existing_type)
                else:
                    # Create new type
                    type_obj = Type(**type_data)
                    self.db.add(type_obj)
                    types.append(type_obj)
            
            self.db.commit()
            logger.info(f"Loaded {len(types)} types")
            return types
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error loading types: {e}")
            raise
    
    def load_type_effectiveness(self, effectiveness_data: List[Dict[str, Any]]) -> List[TypeEffectiveness]:
        """
        Load type effectiveness data into the database.
        
        Args:
            effectiveness_data: List of transformed effectiveness data.
            
        Returns:
            The list of TypeEffectiveness objects that were loaded.
        """
        effectiveness_entries = []
        
        try:
            for effectiveness in effectiveness_data:
                # Check if the effectiveness entry already exists
                existing_entry = self.db.query(TypeEffectiveness).filter(
                    TypeEffectiveness.attack_type_id == effectiveness['attack_type_id'],
                    TypeEffectiveness.defense_type_id == effectiveness['defense_type_id']
                ).first()
                
                if existing_entry:
                    # Update existing entry
                    existing_entry.effectiveness = effectiveness['effectiveness']
                    effectiveness_entries.append(existing_entry)
                else:
                    # Create new entry
                    entry = TypeEffectiveness(**effectiveness)
                    self.db.add(entry)
                    effectiveness_entries.append(entry)
            
            self.db.commit()
            logger.info(f"Loaded {len(effectiveness_entries)} type effectiveness entries")
            return effectiveness_entries
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error loading type effectiveness: {e}")
            raise
    
    def load_pokemon_types(self, pokemon_types_data: List[Dict[str, Any]]) -> List[PokemonType]:
        """
        Load Pokémon type associations into the database.
        
        Args:
            pokemon_types_data: List of transformed Pokémon type data.
            
        Returns:
            The list of PokemonType objects that were loaded.
        """
        pokemon_types = []
        
        try:
            for pokemon_type in pokemon_types_data:
                # Check if the Pokémon-type association already exists
                existing_association = self.db.query(PokemonType).filter(
                    PokemonType.pokemon_id == pokemon_type['pokemon_id'],
                    PokemonType.type_id == pokemon_type['type_id']
                ).first()
                
                if existing_association:
                    # Update existing association
                    existing_association.slot = pokemon_type['slot']
                    pokemon_types.append(existing_association)
                else:
                    # Create new association
                    association = PokemonType(**pokemon_type)
                    self.db.add(association)
                    pokemon_types.append(association)
            
            self.db.commit()
            logger.info(f"Loaded {len(pokemon_types)} Pokémon-type associations")
            return pokemon_types
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error loading Pokémon-type associations: {e}")
            raise
    
    def load_all_pokemon_data(self, transformed_data: Dict[str, List[Dict[str, Any]]]):
        """
        Load all transformed Pokémon data into the database.
        
        Args:
            transformed_data: Dictionary containing all transformed data.
        """
        try:
            # Load Pokémon
            for pokemon_data in transformed_data.get('pokemon', []):
                self.load_pokemon(pokemon_data)
            
            # Load stats
            self.load_pokemon_stats(transformed_data.get('stats', []))
            
            # Load types associations
            self.load_pokemon_types(transformed_data.get('types', []))
            
            # Load abilities
            if 'abilities' in transformed_data:
                for ability_data in transformed_data['abilities']:
                    self._load_pokemon_ability(ability_data)
            
            # Load moves
            if 'moves' in transformed_data:
                for move_data in transformed_data['moves']:
                    self._load_pokemon_move(move_data)
            
            logger.info("Successfully loaded all Pokémon data")
            
        except Exception as e:
            logger.error(f"Error loading all Pokémon data: {e}")
            raise
    
    def load_all_type_data(self, transformed_data: Dict[str, List[Dict[str, Any]]]):
        """
        Load all transformed type data into the database.
        
        Args:
            transformed_data: Dictionary containing all transformed data.
        """
        try:
            # Load types
            self.load_types(transformed_data.get('types', []))
            
            # Load type effectiveness
            self.load_type_effectiveness(transformed_data.get('effectiveness', []))
            
            logger.info("Successfully loaded all type data")
            
        except Exception as e:
            logger.error(f"Error loading all type data: {e}")
            raise

    def load_all_ability_data(self, transformed_data: List[Dict[str, Any]]):
        """Load all transformed ability data into the database."""
        try:
            for ability_data in transformed_data:
                # Check if ability already exists
                existing_ability = self.db.query(Ability).filter(
                    Ability.id == ability_data['id']
                ).first()
                
                if existing_ability:
                    # Update existing ability
                    for key, value in ability_data.items():
                        setattr(existing_ability, key, value)
                else:
                    # Create new ability
                    ability = Ability(**ability_data)
                    self.db.add(ability)
            
            self.db.commit()
            logger.info("Successfully loaded all ability data")
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error loading ability data: {e}")
            raise
    
    def _load_pokemon_ability(self, ability_data: Dict[str, Any]) -> PokemonAbility:
        """Load a single Pokémon-ability association."""
        try:
            # Check if the association already exists
            existing_association = self.db.query(PokemonAbility).filter(
                PokemonAbility.pokemon_id == ability_data['pokemon_id'],
                PokemonAbility.ability_id == ability_data['ability_id']
            ).first()
            
            if existing_association:
                # Update existing association
                existing_association.is_hidden = ability_data['is_hidden']
                existing_association.slot = ability_data['slot']
                association = existing_association
            else:
                # Create new association
                association = PokemonAbility(**ability_data)
                self.db.add(association)
            
            self.db.commit()
            return association
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error loading Pokémon-ability association: {e}")
            raise
    
    def _load_pokemon_move(self, move_data: Dict[str, Any]) -> PokemonMove:
        """Load a single Pokémon-move association."""
        try:
            # Check if the association already exists
            existing_association = self.db.query(PokemonMove).filter(
                PokemonMove.pokemon_id == move_data['pokemon_id'],
                PokemonMove.move_id == move_data['move_id'],
                PokemonMove.learn_method == move_data['learn_method']
            ).first()
            
            if existing_association:
                # Update existing association
                existing_association.level_learned_at = move_data['level_learned_at']
                association = existing_association
            else:
                # Create new association
                association = PokemonMove(**move_data)
                self.db.add(association)
            
            self.db.commit()
            return association
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error loading Pokémon-move association: {e}")
            raise