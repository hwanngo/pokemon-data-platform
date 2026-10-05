"""Dashboard generation, run-status, and failure-boundary regressions."""

from contextlib import contextmanager
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from streamlit.testing.v1 import AppTest

import src.models  # noqa: F401 - registers mapped tables
from src.analytics import dashboard
from src.models import base
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


def test_form_uses_species_debut_generation(db):
    db.execute(text("INSERT INTO generations (id, name) VALUES (3, 'generation-iii')"))
    db.execute(
        text("""
        INSERT INTO pokemon_species (id, name, generation_id) VALUES (386, 'deoxys', 3)
    """)
    )
    db.execute(
        text("""
        INSERT INTO pokemon (id, name, height, weight, is_default, species_id)
        VALUES (10001, 'deoxys-attack', 10, 10, 0, 386)
    """)
    )
    options = dashboard.get_pokemon_options(db)
    assert options.loc[0, "generation_id"] == 3
    assert dashboard._generation_label(options.loc[0, "generation_name"]) == "Generation III"
    db.execute(
        text("""
        INSERT INTO api_resource (resource_type, id, name, data, is_present)
        VALUES ('pokemon', 10001, 'deoxys-attack', '{}', 0)
    """)
    )
    assert dashboard.get_pokemon_options(db).empty


def test_mirror_status_keeps_last_success_separate_from_failed_attempt(db):
    db.execute(
        text("""
        INSERT INTO mirror_resource_runs
          (run_id, resource_type, started_at, completed_at, status, attempted, succeeded, failed, failed_ids)
        VALUES
          ('one', 'pokemon', '2026-01-01', '2026-01-01', 'success', 1, 1, 0, '[]'),
          ('two', 'pokemon', '2026-01-02', '2026-01-02', 'failed', 1, 0, 1, '[1]')
    """)
    )
    status = dashboard.get_mirror_status(db)[0]
    assert status["latest_status"] == "failed"
    assert str(status["last_success"]).startswith("2026-01-01")
    assert status["latest_failed"] == 1


def test_dashboard_session_closes_after_render(monkeypatch):
    closed = []

    class FakeSession:
        def close(self):
            closed.append(True)

    @contextmanager
    def scope():
        db = FakeSession()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setattr(dashboard, "session_scope", scope)
    monkeypatch.setattr(dashboard, "_mirror_status", lambda db: None)
    monkeypatch.setattr(dashboard, "_stats_page", lambda stats: None)
    monkeypatch.setattr(dashboard.st, "selectbox", lambda *args, **kwargs: "Top Pokémon Stats")
    dashboard.main()
    assert closed == [True]


def test_dashboard_database_error_shows_retry_without_technical_traceback(monkeypatch):
    @contextmanager
    def broken_scope():
        raise OperationalError("private DSN", {}, Exception("credential"))
        yield  # pragma: no cover - makes this a context manager

    messages = []
    monkeypatch.setattr(dashboard, "session_scope", broken_scope)
    monkeypatch.setattr(dashboard.st, "selectbox", lambda *args, **kwargs: "Top Pokémon Stats")
    monkeypatch.setattr(dashboard.st, "error", messages.append)
    monkeypatch.setattr(dashboard.st, "button", lambda label: False)
    dashboard.main()
    assert len(messages) == 1
    assert "Retry" not in messages[0]
    assert "private DSN" not in messages[0]
    assert "temporarily unavailable" in messages[0]


def test_empty_dashboard_runs_across_views_without_exception(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    monkeypatch.setattr(base, "SessionLocal", sessionmaker(bind=engine))
    app = AppTest.from_file(str(Path(dashboard.__file__)), default_timeout=10).run()
    assert not app.exception
    assert any("No Pokémon stats yet" in item.value for item in app.info)
    app.selectbox[0].set_value("Type Effectiveness").run()
    assert not app.exception
    assert any("No types yet" in item.value for item in app.info)
    engine.dispose()


def test_effectiveness_view_has_complete_table_and_single_type_alternative(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            text("""
            INSERT INTO types (id, name) VALUES (1, 'normal'), (2, 'ghost'), (3, 'stellar')
        """)
        )
        connection.execute(
            text("""
            INSERT INTO type_effectiveness (attack_type_id, defense_type_id, effectiveness)
            VALUES (1, 2, 0)
        """)
        )
    monkeypatch.setattr(base, "SessionLocal", sessionmaker(bind=engine))
    app = AppTest.from_file(str(Path(dashboard.__file__)), default_timeout=10).run()
    app.selectbox[0].set_value("Type Effectiveness").run()
    assert not app.exception
    assert any(item.label == "Attacking type" for item in app.selectbox)
    assert any(frame.value.shape == (3, 4) for frame in app.dataframe)
    engine.dispose()


def test_analyzer_filter_places_high_id_form_with_its_species(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            text("""
            INSERT INTO generations (id, name)
            VALUES (3, 'generation-iii'), (9, 'generation-ix')
        """)
        )
        connection.execute(
            text("""
            INSERT INTO pokemon_species (id, name, generation_id)
            VALUES (386, 'deoxys', 3), (1000, 'newmon', 9)
        """)
        )
        connection.execute(
            text("""
            INSERT INTO pokemon (id, name, height, weight, is_default, species_id)
            VALUES (1000, 'newmon', 1, 1, 1, 1000),
                   (10001, 'deoxys-attack', 1, 1, 0, 386)
        """)
        )
    monkeypatch.setattr(base, "SessionLocal", sessionmaker(bind=engine))
    app = AppTest.from_file(str(Path(dashboard.__file__)), default_timeout=10).run()
    app.selectbox[0].set_value("Pokémon Analyzer").run()
    app.selectbox[1].set_value("Generation III").run()
    assert not app.exception
    assert app.selectbox[2].options == ["#10001 - deoxys-attack"]
    engine.dispose()
