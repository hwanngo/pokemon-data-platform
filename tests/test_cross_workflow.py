"""Checks contracts shared by the mirror, SQL schema, and read API."""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import src.models  # noqa: F401 - register all FK targets
from src.analytics.dashboard import get_pokemon_options
from src.analytics.stats_analyzer import StatsAnalyzer
from src.ingestion.mirror import run_mirror
from src.loading.resource_loader import ResourceLoader
from src.main import app, get_db
from src.models.base import Base
from src.models.mirror import Generation, PokemonSpecies, VersionGroup
from src.models.type import Type, TypeEffectiveness


def test_type_mirror_resolves_forward_references_with_foreign_keys_enabled():
    """PokéAPI can list an attack relation before its target type record."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as session:

        class Fetcher:
            attempted = 2
            failed_ids = []

            def fetch_all(self, _name):
                return iter(
                    [
                        {
                            "id": 1,
                            "name": "normal",
                            "damage_relations": {
                                "no_damage_to": [{"url": "https://pokeapi.co/api/v2/type/2/"}],
                                "half_damage_to": [],
                                "double_damage_to": [],
                            },
                        },
                        {
                            "id": 2,
                            "name": "ghost",
                            "damage_relations": {
                                "no_damage_to": [],
                                "half_damage_to": [],
                                "double_damage_to": [],
                            },
                        },
                    ]
                )

        result = run_mirror(
            only=["type"], fetcher=Fetcher(), loader=ResourceLoader(session), expand_deps=False
        )
        assert result == {"type": 2}
        assert session.query(Type).count() == 2
        edge = session.query(TypeEffectiveness).one()
        assert (edge.attack_type_id, edge.defense_type_id, edge.effectiveness) == (1, 2, 0)
    engine.dispose()


def test_mirrored_core_data_reaches_api_and_species_generation_filter():
    """Exercise a complete small mirror through the read API with real foreign keys."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    base_url = "https://pokeapi.co/api/v2"
    details = {
        "type": [
            {
                "id": 1,
                "name": "grass",
                "damage_relations": {
                    "no_damage_to": [],
                    "half_damage_to": [],
                    "double_damage_to": [],
                },
            },
            {
                "id": 2,
                "name": "fire",
                "damage_relations": {
                    "no_damage_to": [],
                    "half_damage_to": [],
                    "double_damage_to": [{"url": f"{base_url}/type/1/"}],
                },
            },
        ],
        "ability": [{"id": 3, "name": "overgrow", "effect_entries": [], "names": []}],
        "move": [
            {
                "id": 4,
                "name": "ember",
                "type": {"url": f"{base_url}/type/2/"},
                "damage_class": {"name": "special"},
            }
        ],
        "pokemon": [
            {
                "id": 10001,
                "name": "bulbasaur-alternate",
                "height": 7,
                "weight": 69,
                "base_experience": 64,
                "is_default": False,
                "species": {"url": f"{base_url}/pokemon-species/1/"},
                "stats": [{"stat": {"name": "hp"}, "base_stat": 45}],
                "types": [{"slot": 1, "type": {"url": f"{base_url}/type/1/"}}],
                "abilities": [
                    {"is_hidden": False, "slot": 1, "ability": {"url": f"{base_url}/ability/3/"}}
                ],
                "moves": [
                    {
                        "move": {"url": f"{base_url}/move/4/"},
                        "version_group_details": [
                            {
                                "version_group": {
                                    "name": "red-blue",
                                    "url": f"{base_url}/version-group/1/",
                                },
                                "level_learned_at": 3,
                                "move_learn_method": {"name": "level-up"},
                            }
                        ],
                    }
                ],
            }
        ],
    }

    class Fetcher:
        attempted = 0
        failed_ids = []

        def fetch_all(self, name):
            rows = details[name]
            self.attempted = len(rows)
            self.failed_ids = []
            return iter(rows)

    try:
        with Session(engine) as session:
            session.add_all(
                [
                    Generation(id=1, name="generation-i"),
                    PokemonSpecies(id=1, name="bulbasaur", generation_id=1),
                    VersionGroup(id=1, name="red-blue", generation_id=1),
                ]
            )
            session.commit()
            fetcher = Fetcher()
            loader = ResourceLoader(session)
            for name in ("type", "ability", "move", "pokemon"):
                assert run_mirror(
                    only=[name], fetcher=fetcher, loader=loader, expand_deps=False
                ) == {name: len(details[name])}

            app.dependency_overrides[get_db] = lambda: session
            try:
                with TestClient(app) as client:
                    detail = client.get("/pokemon/10001")
                    assert detail.status_code == 200
                    assert detail.json()["stats"] == {"hp": 45}
                    assert detail.json()["types"] == ["grass"]
                    counters = client.get("/analytics/pokemon/10001/counters")
                    assert counters.status_code == 200
                    assert counters.json()[0]["attacking_type"] == "fire"
                    assert counters.json()[0]["effectiveness"] == 2.0
                    top = client.get("/analytics/top-pokemon")
                    assert top.status_code == 200
                    assert top.json()[0]["total_base_stats"] == 45
            finally:
                app.dependency_overrides.clear()

            options = get_pokemon_options(session)
            form = options.loc[options["id"] == 10001].iloc[0]
            assert form["generation_id"] == 1
            coverage = StatsAnalyzer(session).get_pokemon_with_best_type_coverage(
                version_group_id=1
            )
            assert coverage.iloc[0]["total_moves"] == 1
            assert coverage.iloc[0]["type_coverage_ratio"] == 0.5
    finally:
        engine.dispose()
