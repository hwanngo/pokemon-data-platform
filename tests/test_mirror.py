"""Tests for the generic PokéAPI mirror engine."""

import tempfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Register every model so Base.metadata.create_all builds all tables.
import src.models.ability  # noqa: F401
import src.models.mirror as mm  # noqa: F401
import src.models.move  # noqa: F401
import src.models.pokemon  # noqa: F401
import src.models.type  # noqa: F401
from src.ingestion.api_client import PokemonApiClient
from src.ingestion.mirror import run_mirror
from src.ingestion.resource_fetcher import ResourceFetcher
from src.ingestion.resources import ordered_resources
from src.loading.resource_loader import ResourceLoader
from src.models.api_resource import ApiResource
from src.models.base import Base
from src.transformation.mirror_transformers import transform_version_group

BASE = "https://pokeapi.co/api/v2"


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


def test_ordered_resources_loads_parents_first():
    order = [s.name for s in ordered_resources()]
    assert order.index("generation") < order.index("version-group") < order.index("version")
    assert order.index("item-category") < order.index("item") < order.index("berry")
    assert order.index("region") < order.index("location") < order.index("location-area")


def test_only_expands_transitive_deps():
    names = [s.name for s in ordered_resources(only=["berry"])]
    assert set(names) == {"item-category", "item", "berry"}
    assert names.index("item-category") < names.index("item") < names.index("berry")


def test_only_without_expand_is_exact():
    assert [s.name for s in ordered_resources(only=["berry"], expand_deps=False)] == ["berry"]


def test_unknown_resource_raises():
    with pytest.raises(KeyError):
        ordered_resources(only=["does-not-exist"])


def test_relational_transform_reduces_refs_to_ids():
    raw = {
        "id": 1,
        "name": "red-blue",
        "order": 1,
        "generation": {"name": "generation-i", "url": f"{BASE}/generation/1/"},
    }
    assert transform_version_group(raw) == {
        "id": 1,
        "name": "red-blue",
        "order_num": 1,
        "generation_id": 1,
    }


def test_fetcher_paginates_and_follows_urls(httpx_mock):
    with tempfile.TemporaryDirectory() as cache:
        client = PokemonApiClient(base_url=BASE, rate_limit=6000, cache_dir=cache)
        httpx_mock.add_response(
            url=f"{BASE}/nature?limit=100000",
            json={"results": [{"name": "hardy", "url": f"{BASE}/nature/1/"}]},
        )
        httpx_mock.add_response(url=f"{BASE}/nature/1", json={"id": 1, "name": "hardy"})
        fetcher = ResourceFetcher(client, concurrency=1)
        assert list(fetcher.fetch_all("nature")) == [{"id": 1, "name": "hardy"}]


def test_fetch_all_concurrent_yields_all_and_skips_failures():
    # Completeness + best-effort guard across the bounded-window submission path
    # (more ids than the 2*concurrency window; one id fails and is skipped).
    class FakeClient:
        def get(self, path):
            if "?" in path:  # list endpoint
                return {
                    "results": [{"name": str(i), "url": f"{BASE}/thing/{i}/"} for i in range(1, 11)]
                }
            ident = int(path.rsplit("/", 1)[-1])
            if ident == 5:
                raise RuntimeError("boom")
            return {"id": ident, "name": f"thing-{ident}"}

    fetcher = ResourceFetcher(FakeClient(), concurrency=3)
    got = {r["id"] for r in fetcher.fetch_all("thing")}
    assert got == set(range(1, 11)) - {5}


def test_loader_jsonb_and_relational_upsert(session):
    loader = ResourceLoader(db_session=session)

    loader.load_jsonb(
        "berry-flavor", [{"id": 1, "name": "spicy", "data": {"id": 1, "name": "spicy", "x": 1}}]
    )
    row = session.get(ApiResource, {"resource_type": "berry-flavor", "id": 1})
    assert row.name == "spicy" and row.data["x"] == 1

    loader.load_relational(mm.Nature, [{"id": 1, "name": "hardy"}])
    assert session.get(mm.Nature, 1).name == "hardy"
    # upsert (not duplicate)
    loader.load_relational(mm.Nature, [{"id": 1, "name": "hardy-2"}])
    assert session.query(mm.Nature).count() == 1
    assert session.get(mm.Nature, 1).name == "hardy-2"


def test_load_relational_upserts_on_custom_conflict(session):
    from src.models.pokemon import Pokemon, PokemonStat

    session.add(Pokemon(id=1, name="x", height=1, weight=1, is_default=True))
    session.commit()
    loader = ResourceLoader(db_session=session)
    conflict = ("pokemon_id", "stat_name")
    loader.load_relational(
        PokemonStat,
        [{"pokemon_id": 1, "stat_name": "hp", "base_value": 45}],
        conflict_cols=conflict,
    )
    loader.load_relational(
        PokemonStat,
        [{"pokemon_id": 1, "stat_name": "hp", "base_value": 99}],
        conflict_cols=conflict,
    )

    rows = session.query(PokemonStat).all()
    assert len(rows) == 1 and rows[0].base_value == 99


def test_mirror_type_is_fanout_into_types_and_effectiveness(session):
    from src.models.type import Type, TypeEffectiveness

    raws = {
        "type": [
            {
                "id": 1,
                "name": "normal",
                "damage_relations": {
                    "no_damage_to": [{"url": f"{BASE}/type/2/"}],  # normal -> ghost = 0.0
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
    }

    class FakeFetcher:
        def fetch_all(self, name):
            return iter(raws.get(name, []))

    run_mirror(
        only=["type"],
        fetcher=FakeFetcher(),
        loader=ResourceLoader(db_session=session),
        expand_deps=False,
    )
    assert session.query(Type).count() == 2
    assert session.query(TypeEffectiveness).count() == 1  # the single no-damage relation


def test_abilities_with_same_display_name_both_load(session):
    # PokéAPI display names aren't unique (e.g. two "As One" abilities) — id is the key.
    from src.models.ability import Ability

    ResourceLoader(db_session=session).load_relational(
        Ability,
        [
            {"id": 266, "name": "As One", "effect_text": "", "short_effect": ""},
            {"id": 267, "name": "As One", "effect_text": "", "short_effect": ""},
        ],
    )
    assert session.query(Ability).count() == 2


def test_fanout_resource_load_is_atomic(session):
    # If a later table in a fan-out resource fails, earlier tables must roll back
    # too — no half-loaded Pokémon. Here pokemon_stats.base_value is NULL (NOT NULL
    # violation) so the stats load fails after the pokemon row was staged.
    from src.models.pokemon import Pokemon

    raw = {
        "id": 1,
        "name": "x",
        "height": 1,
        "weight": 1,
        "base_experience": 1,
        "is_default": True,
        "order": 1,
        "stats": [{"stat": {"name": "hp"}, "base_stat": None}],  # -> NULL base_value
        "types": [],
        "abilities": [],
        "moves": [],
    }

    class FakeFetcher:
        def fetch_all(self, name):
            return iter([raw])

    with pytest.raises(IntegrityError):
        run_mirror(
            only=["pokemon"],
            fetcher=FakeFetcher(),
            loader=ResourceLoader(db_session=session),
            expand_deps=False,
        )
    assert session.query(Pokemon).count() == 0  # pokemon rolled back, not left half-loaded


def test_fanout_skips_malformed_record_and_loads_the_rest(session):
    # One bad record (missing damage_relations) must not sink the whole resource.
    from src.models.type import Type

    raws = {
        "type": [
            {
                "id": 1,
                "name": "normal",
                "damage_relations": {
                    "no_damage_to": [],
                    "half_damage_to": [],
                    "double_damage_to": [],
                },
            },
            {"id": 2, "name": "broken"},  # missing damage_relations -> transform raises
        ]
    }

    class FakeFetcher:
        def fetch_all(self, name):
            return iter(raws.get(name, []))

    run_mirror(
        only=["type"],
        fetcher=FakeFetcher(),
        loader=ResourceLoader(db_session=session),
        expand_deps=False,
    )
    assert session.query(Type).count() == 1  # good record loaded, bad one skipped


def test_run_mirror_routes_relational_and_jsonb(session):
    class FakeFetcher:
        _data = {
            "egg-group": [{"id": 1, "name": "monster"}],
            "berry-flavor": [{"id": 1, "name": "spicy", "extra": True}],
        }

        def fetch_all(self, name):
            return iter(self._data.get(name, []))

    totals = run_mirror(
        only=["egg-group", "berry-flavor"],
        fetcher=FakeFetcher(),
        loader=ResourceLoader(db_session=session),
        expand_deps=False,
    )
    assert totals == {"egg-group": 1, "berry-flavor": 1}
    assert session.get(mm.EggGroup, 1).name == "monster"
    stored = session.get(ApiResource, {"resource_type": "berry-flavor", "id": 1})
    assert stored.data["extra"] is True
