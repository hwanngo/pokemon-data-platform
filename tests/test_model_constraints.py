"""Model-level constraints must match schema.sql so create_all-based tests have
the same integrity guarantees as production."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.models.ability  # noqa: F401
import src.models.move  # noqa: F401
import src.models.pokemon  # noqa: F401
import src.models.type  # noqa: F401
from src.models.ability import PokemonAbility
from src.models.base import Base
from src.models.move import PokemonMove
from src.models.pokemon import Pokemon
from src.models.type import PokemonType, Type


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    try:
        yield db
    finally:
        db.close()


def _seed(session):
    session.add(Pokemon(id=1, name="bulbasaur", height=7, weight=69, is_default=True))
    session.add(Type(id=1, name="grass"))
    session.commit()


def test_pokemon_types_unique_on_pokemon_and_slot(session):
    _seed(session)
    session.add(PokemonType(pokemon_id=1, type_id=1, slot=1))
    session.commit()
    session.add(PokemonType(pokemon_id=1, type_id=1, slot=1))  # duplicate (pokemon_id, slot)
    with pytest.raises(IntegrityError):
        session.commit()


def test_pokemon_stats_unique_on_pokemon_and_stat_name(session):
    from src.models.pokemon import PokemonStat

    _seed(session)
    session.add(PokemonStat(pokemon_id=1, stat_name="hp", base_value=45))
    session.commit()
    session.add(PokemonStat(pokemon_id=1, stat_name="hp", base_value=50))  # dup
    with pytest.raises(IntegrityError):
        session.commit()


def test_pokemon_abilities_unique_on_pokemon_and_ability(session):
    from src.models.ability import Ability

    _seed(session)
    session.add(Ability(id=1, name="overgrow"))
    session.commit()
    session.add(PokemonAbility(pokemon_id=1, ability_id=1, is_hidden=False, slot=1))
    session.commit()
    session.add(PokemonAbility(pokemon_id=1, ability_id=1, is_hidden=True, slot=2))  # dup
    with pytest.raises(IntegrityError):
        session.commit()


def test_pokemon_moves_unique_on_pokemon_move_and_method(session):
    from src.models.move import Move

    _seed(session)
    session.add(Move(id=1, name="tackle"))
    session.commit()
    session.add(PokemonMove(pokemon_id=1, move_id=1, level_learned_at=1, learn_method="level-up"))
    session.commit()
    session.add(PokemonMove(pokemon_id=1, move_id=1, level_learned_at=5, learn_method="level-up"))
    with pytest.raises(IntegrityError):
        session.commit()
