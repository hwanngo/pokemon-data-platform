"""Regression cases for freshness, completeness, and snapshot reconciliation."""

import os
import time

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import src.models  # noqa: F401
from src.ingestion.api_client import PokemonApiClient
from src.ingestion.mirror import IncompleteMirrorError, run_mirror
from src.ingestion.resource_fetcher import ResourceFetcher
from src.loading.resource_loader import ResourceLoader
from src.models.api_resource import ApiResource
from src.models.base import Base
from src.models.mirror import Nature
from src.models.mirror_run import MirrorResourceRun
from src.models.type import TypeEffectiveness
from src.transformation.core_transformers import transform_pokemon

BASE = "https://pokeapi.co/api/v2"


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def test_cache_is_origin_scoped_and_expires(httpx_mock, tmp_path):
    a = PokemonApiClient(
        base_url=BASE, rate_limit=6000, cache_dir=str(tmp_path), cache_ttl_seconds=1
    )
    b = PokemonApiClient(
        base_url="https://mirror.example/api/v2", rate_limit=6000, cache_dir=str(tmp_path)
    )
    try:
        httpx_mock.add_response(url=f"{BASE}/pokemon/1", json={"id": 1, "name": "old"})
        httpx_mock.add_response(url=f"{BASE}/pokemon/1", json={"id": 1, "name": "new"})
        httpx_mock.add_response(
            url="https://mirror.example/api/v2/pokemon/1", json={"id": 1, "name": "other"}
        )
        assert a.get("pokemon/1")["name"] == "old"
        assert a.get("pokemon/1")["name"] == "old"
        assert b.get("pokemon/1")["name"] == "other"
        stale = time.time() - 30
        os.utime(a._get_cache_path("pokemon/1"), (stale, stale))
        assert a.get("pokemon/1")["name"] == "new"
        assert a._get_cache_path("pokemon/1") != b._get_cache_path("pokemon/1")
    finally:
        a.close()
        b.close()


def test_transient_retries_are_each_rate_limited_and_404_is_permanent(
    httpx_mock, tmp_path, monkeypatch
):
    client = PokemonApiClient(base_url=BASE, rate_limit=6000, cache_dir=str(tmp_path))
    slots = []
    monkeypatch.setattr(client, "_rate_limit_wait", lambda: slots.append(1))
    monkeypatch.setattr("src.ingestion.api_client.time.sleep", lambda _: None)
    try:
        httpx_mock.add_response(url=f"{BASE}/pokemon/1", status_code=503)
        httpx_mock.add_response(url=f"{BASE}/pokemon/1", json={"id": 1})
        assert client.get("pokemon/1", use_cache=False)["id"] == 1
        assert len(slots) == 2
        httpx_mock.add_response(url=f"{BASE}/pokemon/2", status_code=404)
        with pytest.raises(httpx.HTTPStatusError):
            client.get("pokemon/2", use_cache=False)
        assert len(slots) == 3
    finally:
        client.close()


def test_pagination_verifies_count_and_follows_next(httpx_mock, tmp_path):
    client = PokemonApiClient(base_url=BASE, rate_limit=6000, cache_dir=str(tmp_path))
    try:
        httpx_mock.add_response(
            url=f"{BASE}/nature?limit=100000",
            json={
                "count": 2,
                "next": f"{BASE}/nature?offset=1",
                "results": [{"url": f"{BASE}/nature/1/"}],
            },
        )
        httpx_mock.add_response(
            url=f"{BASE}/nature?offset=1",
            json={"count": 2, "next": None, "results": [{"url": f"{BASE}/nature/2/"}]},
        )
        assert len(ResourceFetcher(client).fetch_list("nature")) == 2
    finally:
        client.close()


def test_retry_after_is_bounded(httpx_mock, tmp_path, monkeypatch):
    client = PokemonApiClient(base_url=BASE, rate_limit=6000, cache_dir=str(tmp_path))
    sleeps = []
    monkeypatch.setattr("src.ingestion.api_client.time.sleep", sleeps.append)
    monkeypatch.setattr(client, "_rate_limit_wait", lambda: None)
    try:
        httpx_mock.add_response(
            url=f"{BASE}/pokemon/1", status_code=429, headers={"Retry-After": "999999999"}
        )
        httpx_mock.add_response(url=f"{BASE}/pokemon/1", json={"id": 1})
        assert client.get("pokemon/1", use_cache=False)["id"] == 1
        assert sleeps == [120.0]
    finally:
        client.close()


def test_type_edge_removal_and_failed_snapshot_rollback(session):
    def raw(targets):
        return {
            "id": 1,
            "name": "normal",
            "damage_relations": {
                "no_damage_to": [{"url": f"{BASE}/type/{i}/"} for i in targets],
                "half_damage_to": [],
                "double_damage_to": [],
            },
        }

    class Fetcher:
        def __init__(self, records):
            self.records = records

        def fetch_all(self, name):
            return iter(self.records)

    loader = ResourceLoader(session)
    target = raw([])
    target["id"] = 2
    target["name"] = "ghost"
    run_mirror(only=["type"], fetcher=Fetcher([raw([2]), target]), loader=loader, expand_deps=False)
    assert session.query(TypeEffectiveness).count() == 1
    with pytest.raises(IncompleteMirrorError):
        run_mirror(
            only=["type"],
            fetcher=Fetcher([raw([]), {"id": 2, "name": "broken"}]),
            loader=loader,
            expand_deps=False,
        )
    assert session.query(TypeEffectiveness).count() == 1
    run_mirror(only=["type"], fetcher=Fetcher([raw([]), target]), loader=loader, expand_deps=False)
    assert session.query(TypeEffectiveness).count() == 0
    assert [
        r.status for r in session.query(MirrorResourceRun).order_by(MirrorResourceRun.started_at)
    ] == ["success", "failed", "success"]


def test_move_transform_preserves_version_and_all_levels():
    raw = {
        "id": 1,
        "name": "x",
        "height": 1,
        "weight": 1,
        "is_default": True,
        "moves": [
            {
                "move": {"url": f"{BASE}/move/10/"},
                "version_group_details": [
                    {
                        "version_group": {"url": f"{BASE}/version-group/{vg}/"},
                        "move_learn_method": {"name": "level-up"},
                        "level_learned_at": level,
                    }
                    for vg, level in [(1, 5), (1, 10), (2, 20)]
                ],
            }
        ],
    }
    rows = transform_pokemon(raw)["pokemon_moves"]
    assert {(r["version_group_id"], r["level_learned_at"]) for r in rows} == {
        (1, 5),
        (1, 10),
        (2, 20),
    }


def test_removed_id_tombstones_only_after_complete_snapshot(session):
    class Fetcher:
        def __init__(self, records, failed_ids=()):
            self.records = records
            self.failed_ids = list(failed_ids)
            self.listed_ids = {r["id"] for r in records} | set(failed_ids)
            self.attempted = len(self.listed_ids)

        def fetch_all(self, name):
            return iter(self.records)

    loader = ResourceLoader(session)
    run_mirror(
        only=["berry-flavor"],
        fetcher=Fetcher([{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]),
        loader=loader,
        expand_deps=False,
    )
    with pytest.raises(IncompleteMirrorError):
        run_mirror(
            only=["berry-flavor"],
            fetcher=Fetcher([{"id": 1, "name": "a"}], [2]),
            loader=loader,
            expand_deps=False,
        )
    assert session.get(ApiResource, {"resource_type": "berry-flavor", "id": 2}).is_present
    run_mirror(
        only=["berry-flavor"],
        fetcher=Fetcher([{"id": 1, "name": "a"}]),
        loader=loader,
        expand_deps=False,
    )
    assert not session.get(ApiResource, {"resource_type": "berry-flavor", "id": 2}).is_present


def test_loader_splits_large_insert_into_bounded_statements(session):
    loader = ResourceLoader(session)
    statements = []
    from sqlalchemy import event

    def count_inserts(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO natures"):
            statements.append(statement)

    event.listen(session.get_bind(), "before_cursor_execute", count_inserts)
    try:
        loader.load_relational(Nature, [{"id": i, "name": f"nature-{i}"} for i in range(650)])
    finally:
        event.remove(session.get_bind(), "before_cursor_execute", count_inserts)
    assert len(statements) == 3
    assert session.query(Nature).count() == 650
