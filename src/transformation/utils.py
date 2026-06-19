"""Shared helpers for transformers."""


def extract_id_from_url(url: str) -> int:
    """Extract the trailing integer ID from a PokéAPI resource URL.

    e.g. "https://pokeapi.co/api/v2/type/4/" -> 4
    """
    return int(url.rstrip("/").split("/")[-1])
