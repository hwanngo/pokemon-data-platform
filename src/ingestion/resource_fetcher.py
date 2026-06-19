"""Generic PokéAPI resource fetcher for the mirror engine."""

import itertools
import logging
import os
from collections.abc import Iterator
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from typing import Any

from src.ingestion.api_client import PokemonApiClient
from src.transformation.utils import extract_id_from_url

logger = logging.getLogger(__name__)


class ResourceFetcher:
    """Fetches any PokéAPI resource list and its detail records.

    Detail records are fetched concurrently with a thread pool (the work is
    network-I/O bound, so threads overlap latency); the shared client's
    thread-safe rate limiter still caps the global request rate. IDs are
    addressed via the list result URLs, so it works for every resource —
    including non-contiguous IDs and name-less ones (machines).
    """

    def __init__(self, api_client: PokemonApiClient | None = None, concurrency: int | None = None):
        self.api_client = api_client or PokemonApiClient()
        self.concurrency = max(
            1, concurrency if concurrency is not None else int(os.getenv("API_CONCURRENCY") or 8)
        )

    def fetch_list(self, name: str) -> list[dict[str, Any]]:
        """Fetch the full (name, url) list for a resource in one page."""
        response = self.api_client.get(f"{name}?limit=100000")
        results = response.get("results", [])
        logger.info(f"Fetched list of {len(results)} {name}")
        return results

    def fetch_detail(self, name: str, identifier: str | int) -> dict[str, Any]:
        return self.api_client.get(f"{name}/{identifier}")

    def fetch_all(self, name: str) -> Iterator[dict[str, Any]]:
        """Yield every detail record for a resource (fetched concurrently).

        Per-item failures are skipped (best-effort), but a non-zero failure count
        is logged at WARNING so a silently-partial mirror is visible.
        """
        ids = [extract_id_from_url(item["url"]) for item in self.fetch_list(name)]
        failures = 0

        if self.concurrency <= 1:
            for ident in ids:
                try:
                    yield self.fetch_detail(name, ident)
                except Exception as e:
                    failures += 1
                    logger.error(f"Error fetching {name}/{ident}: {e}")
        else:
            # Keep only ~2*concurrency requests in flight: top the window up as
            # each completes instead of submitting all ids up front (bounded memory
            # / queue regardless of how slowly the caller consumes the generator).
            ids_iter = iter(ids)
            window = self.concurrency * 2
            with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
                inflight: dict[Future, int] = {
                    pool.submit(self.fetch_detail, name, i): i
                    for i in itertools.islice(ids_iter, window)
                }
                while inflight:
                    done, _ = wait(set(inflight), return_when=FIRST_COMPLETED)
                    for future in done:
                        ident = inflight.pop(future)
                        nxt = next(ids_iter, None)
                        if nxt is not None:
                            inflight[pool.submit(self.fetch_detail, name, nxt)] = nxt
                        try:
                            yield future.result()
                        except Exception as e:
                            failures += 1
                            logger.error(f"Error fetching {name}/{ident}: {e}")

        if failures:
            logger.warning(f"{name}: {failures}/{len(ids)} detail fetches failed (partial mirror)")
