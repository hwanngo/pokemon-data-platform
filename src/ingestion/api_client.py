"""PokéAPI client with rate limiting and caching."""

import contextlib
import json
import logging
import os
import re
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class PokemonApiClient:
    """Client for the PokéAPI with rate limiting and on-disk caching."""

    def __init__(
        self,
        base_url: str | None = None,
        rate_limit: int | None = None,
        cache_dir: str = "cache",
        timeout: float = 30.0,
    ):
        """
        Initialize the PokéAPI client.

        Args:
            base_url: The base URL for the PokéAPI. Defaults to the API_BASE_URL
                env var, then the public PokéAPI.
            rate_limit: Max requests per minute. Defaults to the API_RATE_LIMIT
                env var, then 20.
            cache_dir: Directory to store cached responses.
            timeout: Per-request timeout in seconds.
        """
        self.base_url = base_url or os.getenv("API_BASE_URL") or "https://pokeapi.co/api/v2"
        self.rate_limit = (
            rate_limit if rate_limit is not None else int(os.getenv("API_RATE_LIMIT") or 20)
        )
        self.request_interval = 60.0 / self.rate_limit  # seconds between requests
        # Thread-safe request scheduling so concurrent fetches still respect the rate.
        self._rate_lock = threading.Lock()
        self._next_slot = 0.0
        self._client = httpx.Client(timeout=timeout)

        # Set up cache directory
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True, parents=True)

        logger.info(
            f"Initialized PokéAPI client with rate limit of {self.rate_limit} requests per minute"
        )

    def _rate_limit_wait(self) -> None:
        """Reserve the next request slot (thread-safe) and sleep until it's due.

        Spacing request *start times* under a lock — while the HTTP call itself
        happens outside it — lets concurrent fetchers overlap network latency yet
        still cap the global request rate at ``rate_limit`` per minute.
        """
        with self._rate_lock:
            start_at = max(time.monotonic(), self._next_slot)
            self._next_slot = start_at + self.request_interval
        delay = start_at - time.monotonic()
        if delay > 0:
            time.sleep(delay)

    def _get_cache_path(self, endpoint: str) -> Path:
        """Human-readable, filesystem-safe cache path for an endpoint.

        e.g. "pokemon/1" -> pokemon__1.json, "move?limit=100000" -> move_limit_100000.json.
        Path separators are encoded (so it can't escape cache_dir) and the name is
        bounded in length.
        """
        slug = endpoint.strip("/").replace("/", "__")
        slug = re.sub(r"[^A-Za-z0-9._-]+", "_", slug)  # query chars (?,=,&) -> _
        slug = re.sub(r"\.\.+", "_", slug).strip("._") or "root"  # no '..', no leading dots
        return self.cache_dir / f"{slug[:120]}.json"

    def _get_from_cache(self, endpoint: str) -> dict[str, Any] | None:
        """Get data from cache if available; a corrupt file is treated as a miss."""
        cache_path = self._get_cache_path(endpoint)

        if cache_path.exists():
            try:
                with open(cache_path) as f:
                    data = json.load(f)
                logger.debug(f"Cache hit for {endpoint}")
                return data
            except (json.JSONDecodeError, OSError) as e:
                # e.g. a truncated file from a crashed/concurrent write.
                logger.warning(f"Ignoring corrupt cache for {endpoint}: {e}")
                return None

        logger.debug(f"Cache miss for {endpoint}")
        return None

    def _save_to_cache(self, endpoint: str, data: dict[str, Any]) -> None:
        """Atomically write the cache file (temp + os.replace).

        The atomic rename means a concurrent reader never sees a half-written
        file — important since the cache dir is shared across processes/containers.
        """
        cache_path = self._get_cache_path(endpoint)
        fd, tmp = tempfile.mkstemp(dir=self.cache_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f)
            os.replace(tmp, cache_path)  # atomic on the same filesystem
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise

        logger.debug(f"Cached data for {endpoint}")

    @retry(
        retry=retry_if_exception_type(httpx.HTTPError),
        wait=wait_exponential(multiplier=1, max=30),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def _request(self, url: str) -> dict[str, Any]:
        """Perform a single GET request with exponential-backoff retries."""
        response = self._client.get(url)
        response.raise_for_status()
        return response.json()

    def get(self, endpoint: str, use_cache: bool = True) -> dict[str, Any]:
        """
        Make a GET request to the PokéAPI.

        Args:
            endpoint: The API endpoint (without the base URL).
            use_cache: Whether to use the cache.

        Returns:
            The JSON response as a dictionary.

        Raises:
            httpx.HTTPError: If the request fails after retries.
        """
        # Check cache first if enabled
        if use_cache:
            cached_data = self._get_from_cache(endpoint)
            if cached_data is not None:
                return cached_data

        # Apply rate limiting
        self._rate_limit_wait()

        # Make the request
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        logger.info(f"Requesting {url}")
        data = self._request(url)

        # Save to cache
        if use_cache:
            self._save_to_cache(endpoint, data)

        return data
