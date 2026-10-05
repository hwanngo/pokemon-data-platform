"""Generic PokéAPI resource fetcher for the mirror engine."""

import itertools
import logging
import os
from collections.abc import Iterator
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from typing import Any
from urllib.parse import urlsplit

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

    def __init__(
        self,
        api_client: PokemonApiClient | None = None,
        concurrency: int | None = None,
        refresh: bool = False,
    ):
        self.api_client = api_client or PokemonApiClient()
        self.refresh = refresh
        self.failed_ids: list[int] = []
        self.attempted = 0
        self.listed_ids: set[int] | None = None
        self.concurrency = (
            concurrency if concurrency is not None else int(os.getenv("API_CONCURRENCY") or 8)
        )
        if not 1 <= self.concurrency <= 64:
            raise ValueError("API_CONCURRENCY must be between 1 and 64")

    def fetch_list(self, name: str) -> list[dict[str, Any]]:
        """Follow all list pages and verify the upstream count."""
        endpoint = f"{name}?limit=100000"
        results: list[dict[str, Any]] = []
        seen_pages: set[str] = set()
        expected: int | None = None
        while endpoint:
            if endpoint in seen_pages:
                raise ValueError(f"pagination loop in {name}: {endpoint}")
            seen_pages.add(endpoint)
            response = self.api_client.get(endpoint, use_cache=not self.refresh)
            page = response["results"]
            if not isinstance(page, list):
                raise ValueError(f"invalid list page for {name}")
            expected = response.get("count", expected)
            results.extend(page)
            next_url = response.get("next")
            if next_url:
                parsed = urlsplit(next_url)
                base = urlsplit(self.api_client.base_url)
                if parsed.netloc and (parsed.scheme, parsed.netloc) != (base.scheme, base.netloc):
                    raise ValueError(f"off-origin next page for {name}")
                prefix = base.path.rstrip("/") + "/"
                if not parsed.path.startswith(prefix):
                    raise ValueError(f"invalid next page path for {name}")
                endpoint = parsed.path[len(prefix) :] + (f"?{parsed.query}" if parsed.query else "")
            else:
                endpoint = ""
        if expected is not None and len(results) != expected:
            raise ValueError(f"incomplete {name} list: expected {expected}, got {len(results)}")
        logger.info("Fetched list of %d %s", len(results), name)
        return results

    def fetch_detail(self, name: str, identifier: str | int) -> dict[str, Any]:
        return self.api_client.get(f"{name}/{identifier}", use_cache=not self.refresh)

    def fetch_all(self, name: str) -> Iterator[dict[str, Any]]:
        """Yield every detail record for a resource (fetched concurrently).

        Per-item failures are skipped (best-effort), but a non-zero failure count
        is logged at WARNING so a silently-partial mirror is visible.
        """
        self.attempted = 0
        self.failed_ids = []
        self.listed_ids = None
        ids = [extract_id_from_url(item["url"]) for item in self.fetch_list(name)]
        if len(set(ids)) != len(ids):
            raise ValueError(f"duplicate IDs in {name} list")
        self.listed_ids = set(ids)
        self.attempted = len(ids)
        failures = 0

        if self.concurrency <= 1:
            for ident in ids:
                try:
                    yield self.fetch_detail(name, ident)
                except Exception:
                    failures += 1
                    self.failed_ids.append(ident)
                    logger.exception("Error fetching %s/%s", name, ident)
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
                        except Exception:
                            failures += 1
                            self.failed_ids.append(ident)
                            logger.exception("Error fetching %s/%s", name, ident)

        if failures:
            logger.warning(f"{name}: {failures}/{len(ids)} detail fetches failed (partial mirror)")
