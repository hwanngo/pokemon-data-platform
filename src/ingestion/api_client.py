"""PokéAPI client with rate limiting and caching."""

import contextlib
import hashlib
import json
import logging
import math
import os
import re
import tempfile
import threading
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class PokemonApiClient:
    """Client for the PokéAPI with rate limiting and on-disk caching."""

    def __init__(
        self,
        base_url: str | None = None,
        rate_limit: int | None = None,
        cache_dir: str = "cache",
        timeout: float = 30.0,
        cache_ttl_seconds: int = 86400,
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
        self.base_url = (
            base_url or os.getenv("API_BASE_URL") or "https://pokeapi.co/api/v2"
        ).rstrip("/")
        self.cache_ttl_seconds = cache_ttl_seconds
        self.rate_limit = (
            rate_limit if rate_limit is not None else int(os.getenv("API_RATE_LIMIT") or 20)
        )
        if self.rate_limit <= 0:
            raise ValueError("API_RATE_LIMIT must be positive")
        self.request_interval = 60.0 / self.rate_limit  # seconds between requests
        # Thread-safe request scheduling so concurrent fetches still respect the rate.
        self._rate_lock = threading.Lock()
        self._next_slot = 0.0
        self._client = httpx.Client(timeout=timeout)

        # Set up cache directory
        origin = hashlib.sha256(self.base_url.encode()).hexdigest()[:16]
        self.cache_dir = Path(cache_dir) / origin
        self.cache_dir.mkdir(exist_ok=True, parents=True)
        self._cache_locks: dict[str, threading.Lock] = {}
        self._cache_locks_guard = threading.Lock()

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

        if (
            cache_path.exists()
            and time.time() - cache_path.stat().st_mtime <= self.cache_ttl_seconds
        ):
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

    def _request(self, url: str) -> dict[str, Any]:
        """Rate-limit every attempt; retry only transport and transient status errors."""
        for attempt in range(5):
            self._rate_limit_wait()
            try:
                response = self._client.get(url)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status not in (408, 429) and not 500 <= status <= 599:
                    raise
                if attempt == 4:
                    raise
                retry_after = exc.response.headers.get("Retry-After")
                delay = min(30.0, 2**attempt)
                if retry_after:
                    try:
                        seconds = float(retry_after)
                        if math.isfinite(seconds):
                            delay = max(delay, seconds)
                    except ValueError:
                        with contextlib.suppress(TypeError, OverflowError):
                            delay = max(
                                delay,
                                (
                                    parsedate_to_datetime(retry_after) - datetime.now(UTC)
                                ).total_seconds(),
                            )
                time.sleep(min(120.0, max(0.0, delay)))
            except httpx.TransportError:
                if attempt == 4:
                    raise
                time.sleep(min(30.0, 2**attempt))
        raise AssertionError("unreachable")

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
        with self._cache_locks_guard:
            lock = self._cache_locks.setdefault(endpoint, threading.Lock())
        with lock:
            if use_cache:
                cached_data = self._get_from_cache(endpoint)
                if cached_data is not None:
                    return cached_data
            url = f"{self.base_url}/{endpoint.lstrip('/')}"
            logger.info("Requesting %s", url)
            data = self._request(url)
            self._save_to_cache(endpoint, data)
            return data

    def close(self) -> None:
        self._client.close()
