"""HTTP contracts for bounded analytics, missing entities, and readiness."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import src.models  # noqa: F401 - registers all mapped tables
from src.main import app
from src.models.base import Base, get_db


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)

    def session_override():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = session_override
    with TestClient(app) as test_client:
        yield test_client, engine
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.mark.parametrize(
    "path",
    [
        "/analytics/top-pokemon?limit=0",
        "/analytics/top-pokemon?limit=101",
        "/analytics/pokemon/1/counters?top_n=0",
        "/analytics/pokemon/1/counters?top_n=101",
        "/analytics/pokemon/0/counters",
        "/pokemon/0",
    ],
)
def test_invalid_analytics_bounds_return_422(client, path):
    http, _ = client
    assert http.get(path).status_code == 422


def test_missing_pokemon_counters_return_404_and_existing_without_types_is_empty(client):
    http, engine = client
    assert http.get("/analytics/pokemon/9/counters").status_code == 404
    with engine.begin() as connection:
        connection.execute(
            text("""
            INSERT INTO pokemon (id, name, height, weight, is_default)
            VALUES (9, 'typeless', 1, 1, 1)
        """)
        )
    response = http.get("/analytics/pokemon/9/counters")
    assert response.status_code == 200
    assert response.json() == []


def test_readiness_checks_database_and_hides_error_details(client):
    http, _ = client
    assert http.get("/health/ready").json() == {"status": "ready"}

    class BrokenSession:
        def execute(self, _statement):
            raise OperationalError("private DSN", {}, Exception("credential"))

    def broken_session():
        yield BrokenSession()

    app.dependency_overrides[get_db] = broken_session
    response = http.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}


def test_analytics_responses_have_declared_shape(client):
    http, engine = client
    with engine.begin() as connection:
        connection.execute(
            text("""
            INSERT INTO pokemon (id, name, height, weight, is_default)
            VALUES (1, 'testmon', 2, 3, 1)
        """)
        )
        connection.execute(
            text("""
            INSERT INTO pokemon_stats (pokemon_id, stat_name, base_value)
            VALUES (1, 'hp', 50)
        """)
        )
        connection.execute(
            text("""
            INSERT INTO types (id, name) VALUES (1, 'grass'), (2, 'fire')
        """)
        )
        connection.execute(
            text("""
            INSERT INTO pokemon_types (pokemon_id, type_id, slot) VALUES (1, 1, 1)
        """)
        )
        connection.execute(
            text("""
            INSERT INTO type_effectiveness (attack_type_id, defense_type_id, effectiveness)
            VALUES (2, 1, 2)
        """)
        )
    assert http.get("/analytics/top-pokemon?limit=1").json() == [
        {"id": 1, "name": "testmon", "total_base_stats": 50}
    ]
    assert http.get("/analytics/pokemon/1/counters?top_n=1").json() == [
        {
            "attacking_type": "fire",
            "effectiveness": 2.0,
            "description": "2× (super effective)",
        }
    ]


def test_tombstoned_pokemon_is_hidden_but_legacy_row_remains_visible(client):
    http, engine = client
    with engine.begin() as connection:
        connection.execute(
            text("""
            INSERT INTO pokemon (id, name, height, weight, is_default)
            VALUES (1, 'legacy', 1, 1, 1), (2, 'removed', 1, 1, 1)
        """)
        )
        connection.execute(
            text("""
            INSERT INTO pokemon_stats (pokemon_id, stat_name, base_value)
            VALUES (1, 'hp', 20), (2, 'hp', 100)
        """)
        )
        connection.execute(
            text("""
            INSERT INTO api_resource (resource_type, id, name, data, is_present)
            VALUES ('pokemon', 2, 'removed', '{}', 0)
        """)
        )
    assert [row["id"] for row in http.get("/pokemon").json()] == [1]
    assert http.get("/pokemon/2").status_code == 404
    assert http.get("/analytics/pokemon/2/counters").status_code == 404
    assert [row["id"] for row in http.get("/analytics/top-pokemon").json()] == [1]
