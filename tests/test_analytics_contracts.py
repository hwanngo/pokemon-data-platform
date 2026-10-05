"""Regression coverage for sparse analytics and move-coverage semantics."""

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import src.models  # noqa: F401 - registers all mapped tables
from src.analytics.stats_analyzer import StatsAnalyzer
from src.analytics.type_analyzer import TypeAnalyzer
from src.models.base import Base


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_empty_type_rankings_are_typed_and_do_not_raise(db):
    analyzer = TypeAnalyzer(db)
    matrix = analyzer.get_effectiveness_matrix()
    assert matrix.empty
    assert analyzer.find_best_attacking_types(matrix).empty
    assert analyzer.find_best_defensive_types(matrix).empty
    assert analyzer.find_best_attacking_types(matrix).columns.tolist() == [
        "type",
        "avg_effectiveness",
        "super_effective_count",
        "no_effect_count",
    ]


def test_sparse_type_matrix_includes_all_neutral_types(db):
    db.execute(
        text("INSERT INTO types (id, name) VALUES (1, 'normal'), (2, 'ghost'), (3, 'stellar')")
    )
    db.execute(
        text("""
        INSERT INTO type_effectiveness (attack_type_id, defense_type_id, effectiveness)
        VALUES (1, 2, 0)
    """)
    )
    analyzer = TypeAnalyzer(db)
    matrix = analyzer.get_effectiveness_matrix()
    assert matrix.shape == (3, 3)
    assert matrix.loc["normal", "ghost"] == 0
    assert matrix.loc["stellar", "normal"] == 1
    assert "stellar" in analyzer.find_best_attacking_types(matrix)["type"].tolist()
    assert "stellar" in analyzer.find_best_defensive_types(matrix)["type"].tolist()


def test_coverage_counts_distinct_moves_and_can_scope_version_group(db):
    db.execute(text("INSERT INTO types (id, name) VALUES (1, 'normal'), (2, 'fire')"))
    db.execute(text("INSERT INTO generations (id, name) VALUES (1, 'generation-i')"))
    db.execute(
        text("""
        INSERT INTO version_groups (id, name, generation_id)
        VALUES (1, 'red-blue', 1), (2, 'scarlet-violet', 1)
    """)
    )
    db.execute(
        text("""
        INSERT INTO pokemon (id, name, height, weight, is_default)
        VALUES (1, 'testmon', 10, 10, 1)
    """)
    )
    db.execute(
        text("""
        INSERT INTO moves (id, name, type_id) VALUES
        (1, 'tackle', 1), (2, 'ember', 2)
    """)
    )
    db.execute(
        text("""
        INSERT INTO pokemon_moves
            (pokemon_id, move_id, version_group_id, learn_method, level_learned_at)
        VALUES (1, 1, 1, 'level-up', 1),
               (1, 1, 1, 'machine', 0),
               (1, 2, 2, 'level-up', 5)
    """)
    )
    analyzer = StatsAnalyzer(db)
    union = analyzer.get_pokemon_with_best_type_coverage()
    assert union.loc[0, "total_moves"] == 2
    assert float(union.loc[0, "type_coverage_ratio"]) == 1.0
    scoped = analyzer.get_pokemon_with_best_type_coverage(version_group_id=1)
    assert scoped.loc[0, "total_moves"] == 1
    assert float(scoped.loc[0, "type_coverage_ratio"]) == 0.5


def test_analyzers_only_close_sessions_they_create(monkeypatch, db):
    closed = []

    class FakeSession:
        def close(self):
            closed.append(True)

    monkeypatch.setattr("src.analytics.stats_analyzer.SessionLocal", FakeSession)
    with StatsAnalyzer():
        pass
    assert closed == [True]
    with StatsAnalyzer(db):
        pass
    db.execute(text("SELECT 1"))
    assert closed == [True]


def test_tombstoned_types_and_pokemon_do_not_enter_analytics(db):
    db.execute(text("INSERT INTO types (id, name) VALUES (1, 'grass'), (2, 'fire')"))
    db.execute(
        text("""
        INSERT INTO pokemon (id, name, height, weight, is_default)
        VALUES (1, 'legacy', 1, 1, 1), (2, 'removed', 1, 1, 1)
    """)
    )
    db.execute(
        text("""
        INSERT INTO pokemon_types (pokemon_id, type_id, slot)
        VALUES (1, 1, 1), (2, 2, 1)
    """)
    )
    db.execute(
        text("""
        INSERT INTO type_effectiveness (attack_type_id, defense_type_id, effectiveness)
        VALUES (2, 1, 2)
    """)
    )
    db.execute(
        text("""
        INSERT INTO api_resource (resource_type, id, name, data, is_present)
        VALUES ('pokemon', 2, 'removed', '{}', 0),
               ('type', 2, 'fire', '{}', 0)
    """)
    )
    matrix = TypeAnalyzer(db).get_effectiveness_matrix()
    assert matrix.index.tolist() == ["grass"]
    assert matrix.columns.tolist() == ["grass"]
    distribution = StatsAnalyzer(db).get_type_distribution()
    assert distribution.to_dict(orient="records") == [{"type_name": "grass", "pokemon_count": 1}]
    assert StatsAnalyzer(db).get_dual_type_combinations().empty


def test_dual_type_combinations_keep_slot_order(db):
    db.execute(text("INSERT INTO types (id, name) VALUES (1, 'water'), (2, 'flying')"))
    db.execute(
        text("""
        INSERT INTO pokemon (id, name, height, weight, is_default)
        VALUES (1, 'one', 1, 1, 1), (2, 'two', 1, 1, 1)
    """)
    )
    db.execute(
        text("""
        INSERT INTO pokemon_types (pokemon_id, type_id, slot)
        VALUES (1, 1, 1), (1, 2, 2), (2, 1, 1), (2, 2, 2)
    """)
    )
    assert StatsAnalyzer(db).get_dual_type_combinations().to_dict(orient="records") == [
        {"type_combination": "water/flying", "pokemon_count": 2}
    ]
