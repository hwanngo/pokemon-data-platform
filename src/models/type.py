"""Type model definitions."""

from sqlalchemy import Column, Integer, String, ForeignKey, Numeric
from sqlalchemy.orm import relationship

from src.models.base import Base


class Type(Base):
    __tablename__ = "types"

    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False, unique=True)
    
    # Relationships
    pokemon = relationship("PokemonType", back_populates="type")
    moves = relationship("Move", back_populates="type")
    
    # Type effectiveness relationships
    attack_effectiveness = relationship(
        "TypeEffectiveness", 
        foreign_keys="TypeEffectiveness.attack_type_id",
        back_populates="attack_type"
    )
    defense_effectiveness = relationship(
        "TypeEffectiveness", 
        foreign_keys="TypeEffectiveness.defense_type_id",
        back_populates="defense_type"
    )

    def __repr__(self):
        return f"<Type(id={self.id}, name={self.name})>"


class PokemonType(Base):
    __tablename__ = "pokemon_types"

    id = Column(Integer, primary_key=True)
    pokemon_id = Column(Integer, ForeignKey("pokemon.id"), nullable=False)
    type_id = Column(Integer, ForeignKey("types.id"), nullable=False)
    slot = Column(Integer, nullable=False)  # Primary type (1) or secondary type (2)
    
    # Relationships
    pokemon = relationship("Pokemon", back_populates="types")
    type = relationship("Type", back_populates="pokemon")

    def __repr__(self):
        return f"<PokemonType(pokemon_id={self.pokemon_id}, type_id={self.type_id}, slot={self.slot})>"


class TypeEffectiveness(Base):
    __tablename__ = "type_effectiveness"

    id = Column(Integer, primary_key=True)
    attack_type_id = Column(Integer, ForeignKey("types.id"), nullable=False)
    defense_type_id = Column(Integer, ForeignKey("types.id"), nullable=False)
    effectiveness = Column(Numeric(3, 2), nullable=False)  # 0.0, 0.5, 1.0, 2.0
    
    # Relationships
    attack_type = relationship("Type", foreign_keys=[attack_type_id], back_populates="attack_effectiveness")
    defense_type = relationship("Type", foreign_keys=[defense_type_id], back_populates="defense_effectiveness")

    def __repr__(self):
        return f"<TypeEffectiveness(attack={self.attack_type_id}, defense={self.defense_type_id}, effectiveness={self.effectiveness})>"