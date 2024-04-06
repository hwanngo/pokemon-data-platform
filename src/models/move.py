"""Move model definitions."""

from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship

from src.models.base import Base


class Move(Base):
    __tablename__ = "moves"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    power = Column(Integer)
    pp = Column(Integer)
    accuracy = Column(Integer)
    type_id = Column(Integer, ForeignKey("types.id"))
    damage_class = Column(String(50))
    
    # Relationships
    type = relationship("Type", back_populates="moves")
    pokemon = relationship("PokemonMove", back_populates="move")

    def __repr__(self):
        return f"<Move(id={self.id}, name={self.name})>"


class PokemonMove(Base):
    __tablename__ = "pokemon_moves"

    id = Column(Integer, primary_key=True)
    pokemon_id = Column(Integer, ForeignKey("pokemon.id"), nullable=False)
    move_id = Column(Integer, ForeignKey("moves.id"), nullable=False)
    level_learned_at = Column(Integer)
    learn_method = Column(String(50))
    
    # Relationships
    pokemon = relationship("Pokemon", back_populates="moves")
    move = relationship("Move", back_populates="pokemon")

    def __repr__(self):
        return f"<PokemonMove(pokemon_id={self.pokemon_id}, move_id={self.move_id}, level={self.level_learned_at})>"