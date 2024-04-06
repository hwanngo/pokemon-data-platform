"""Ability model definitions."""

from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship

from src.models.base import Base


class Ability(Base):
    __tablename__ = "abilities"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    effect_text = Column(Text)
    short_effect = Column(Text)
    
    # Relationships
    pokemon = relationship("PokemonAbility", back_populates="ability")

    def __repr__(self):
        return f"<Ability(id={self.id}, name={self.name})>"


class PokemonAbility(Base):
    __tablename__ = "pokemon_abilities"

    id = Column(Integer, primary_key=True)
    pokemon_id = Column(Integer, ForeignKey("pokemon.id"), nullable=False)
    ability_id = Column(Integer, ForeignKey("abilities.id"), nullable=False)
    is_hidden = Column(Boolean, nullable=False)
    slot = Column(Integer, nullable=False)
    
    # Relationships
    pokemon = relationship("Pokemon", back_populates="abilities")
    ability = relationship("Ability", back_populates="pokemon")

    def __repr__(self):
        return f"<PokemonAbility(pokemon_id={self.pokemon_id}, ability_id={self.ability_id}, is_hidden={self.is_hidden})>"