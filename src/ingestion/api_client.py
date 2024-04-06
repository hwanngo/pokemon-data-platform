"""PokéAPI client with rate limiting and caching."""

import os
import json
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional

import requests
import backoff

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PokemonApiClient:
    """Client for the PokéAPI with rate limiting and caching."""
    
    def __init__(self, 
                 base_url: str = "https://pokeapi.co/api/v2", 
                 rate_limit: int = 20,
                 cache_dir: str = "cache"):
        """
        Initialize the PokéAPI client.
        
        Args:
            base_url: The base URL for the PokéAPI.
            rate_limit: Maximum number of requests per minute.
            cache_dir: Directory to store cached responses.
        """
        self.base_url = base_url
        self.rate_limit = rate_limit
        self.request_interval = 60.0 / rate_limit  # seconds between requests
        self.last_request_time = 0
        
        # Set up cache directory
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True, parents=True)
        
        logger.info(f"Initialized PokéAPI client with rate limit of {rate_limit} requests per minute")
    
    def _rate_limit_wait(self):
        """Wait to respect rate limiting."""
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time
        
        if time_since_last_request < self.request_interval:
            wait_time = self.request_interval - time_since_last_request
            logger.debug(f"Rate limiting: waiting {wait_time:.2f} seconds")
            time.sleep(wait_time)
        
        self.last_request_time = time.time()
    
    def _get_cache_path(self, endpoint: str) -> Path:
        """Get the cache file path for an endpoint."""
        # Replace slashes with underscores for the filename
        cache_key = endpoint.replace("/", "_").replace("?", "_")
        return self.cache_dir / f"{cache_key}.json"
    
    def _get_from_cache(self, endpoint: str) -> Optional[Dict[str, Any]]:
        """Get data from cache if available."""
        cache_path = self._get_cache_path(endpoint)
        
        if cache_path.exists():
            logger.debug(f"Cache hit for {endpoint}")
            with open(cache_path, 'r') as f:
                return json.load(f)
        
        logger.debug(f"Cache miss for {endpoint}")
        return None
    
    def _save_to_cache(self, endpoint: str, data: Dict[str, Any]):
        """Save data to cache."""
        cache_path = self._get_cache_path(endpoint)
        
        with open(cache_path, 'w') as f:
            json.dump(data, f)
        
        logger.debug(f"Cached data for {endpoint}")
    
    @backoff.on_exception(
        backoff.expo,
        (requests.exceptions.RequestException, requests.exceptions.HTTPError),
        max_tries=5
    )
    def get(self, endpoint: str, use_cache: bool = True) -> Dict[str, Any]:
        """
        Make a GET request to the PokéAPI.
        
        Args:
            endpoint: The API endpoint (without the base URL).
            use_cache: Whether to use the cache.
            
        Returns:
            The JSON response as a dictionary.
            
        Raises:
            requests.exceptions.RequestException: If the request fails.
        """
        # Check cache first if enabled
        if use_cache:
            cached_data = self._get_from_cache(endpoint)
            if cached_data:
                return cached_data
        
        # Apply rate limiting
        self._rate_limit_wait()
        
        # Make the request
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        logger.info(f"Requesting {url}")
        
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        # Save to cache
        if use_cache:
            self._save_to_cache(endpoint, data)
        
        return data