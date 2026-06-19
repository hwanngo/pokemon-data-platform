"""Tests for the PokéAPI client (fully mocked — no network access)."""

import tempfile
from pathlib import Path

import pytest

from src.ingestion.api_client import PokemonApiClient

BASE_URL = "https://pokeapi.co/api/v2"


@pytest.fixture
def cache_dir():
    with tempfile.TemporaryDirectory() as tmp:
        yield tmp


@pytest.fixture
def client(cache_dir):
    # rate_limit high so the inter-request sleep is negligible in tests
    return PokemonApiClient(base_url=BASE_URL, rate_limit=6000, cache_dir=cache_dir)


def test_get_returns_json(httpx_mock, client):
    httpx_mock.add_response(
        url=f"{BASE_URL}/pokemon/1",
        json={"id": 1, "name": "bulbasaur", "types": [], "stats": []},
    )

    data = client.get("pokemon/1")

    assert data["id"] == 1
    assert data["name"] == "bulbasaur"
    assert "types" in data and "stats" in data


def test_response_is_cached(httpx_mock, client):
    # Register a single response; if the client hit the network twice the mock
    # would raise (no second response registered).
    httpx_mock.add_response(url=f"{BASE_URL}/pokemon/2", json={"id": 2, "name": "ivysaur"})

    first = client.get("pokemon/2")
    second = client.get("pokemon/2")  # served from cache, no second request

    assert first == second
    assert len(httpx_mock.get_requests()) == 1


def test_cache_filename_is_human_readable(httpx_mock, client, cache_dir):
    httpx_mock.add_response(url=f"{BASE_URL}/pokemon/1", json={"id": 1, "name": "bulbasaur"})
    httpx_mock.add_response(url=f"{BASE_URL}/move?limit=100000", json={"results": []})

    client.get("pokemon/1")
    client.get("move?limit=100000")

    names = {p.name for p in Path(cache_dir).glob("*.json")}
    # readable, not a sha256 hash
    assert "pokemon__1.json" in names
    assert "move_limit_100000.json" in names


def test_corrupt_cache_file_is_treated_as_miss(httpx_mock, client):
    # A truncated/corrupt cache file (e.g. from a crashed concurrent write) must
    # not crash the client — it should re-fetch.
    client._get_cache_path("pokemon/1").write_text("{ not valid json")
    httpx_mock.add_response(url=f"{BASE_URL}/pokemon/1", json={"id": 1, "name": "bulbasaur"})

    assert client.get("pokemon/1") == {"id": 1, "name": "bulbasaur"}


def test_distinct_endpoints_do_not_collide(httpx_mock, client):
    httpx_mock.add_response(url=f"{BASE_URL}/ability?limit=1", json={"a": 1})
    httpx_mock.add_response(url=f"{BASE_URL}/ability?limit=2", json={"a": 2})

    assert client.get("ability?limit=1") == {"a": 1}
    assert client.get("ability?limit=2") == {"a": 2}
