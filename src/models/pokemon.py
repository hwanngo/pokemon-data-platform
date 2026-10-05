"""Pokémon model definition."""

from sqlalchemy import Boolean, Column, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from src.models.base import Base


class Pokemon(Base):
    __tablename__ = "pokemon"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    height = Column(Integer, nullable=False)
    weight = Column(Integer, nullable=False)
    base_experience = Column(Integer)
    is_default = Column(Boolean, nullable=False)
    order_num = Column(Integer)
    species_id = Column(Integer, ForeignKey("pokemon_species.id"))
    __table_args__ = (Index("idx_pokemon_species", "species_id"),)

    # Relationships
    stats = relationship("PokemonStat", back_populates="pokemon")
    types = relationship("PokemonType", back_populates="pokemon")
    abilities = relationship("PokemonAbility", back_populates="pokemon")
    moves = relationship("PokemonMove", back_populates="pokemon")

    def __repr__(self):
        return f"<Pokémon(id={self.id}, name={self.name})>"


class PokemonStat(Base):
    __tablename__ = "pokemon_stats"
    __table_args__ = (
        UniqueConstraint("pokemon_id", "stat_name"),
        Index("idx_pokemon_stats_pokemon_id", "pokemon_id"),
    )

    id = Column(Integer, primary_key=True)
    pokemon_id = Column(Integer, ForeignKey("pokemon.id"), nullable=False)
    stat_name = Column(String(50), nullable=False)
    base_value = Column(Integer, nullable=False)

    # Relationship
    pokemon = relationship("Pokemon", back_populates="stats")

    def __repr__(self):
        return f"<PokemonStat(pokemon_id={self.pokemon_id}, stat={self.stat_name}, value={self.base_value})>"
