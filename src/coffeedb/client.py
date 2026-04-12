"""Shared HTTP client and caching utilities for web scraping."""

import os
from pathlib import Path

import httpx
from hishel import BaseFilter, FilterPolicy, Request, Response, SyncSqliteStorage
from hishel.httpx import SyncCacheClient

from coffeedb.constants import (
    CACHE_DIR_ENV_VAR,
    DEFAULT_CACHE_DIR,
    DEFAULT_USER_AGENT,
)


class GetMethodFilter(BaseFilter[Request]):
    """Filter that only allows GET requests to be cached."""

    def needs_body(self) -> bool:
        return False

    def apply(self, item: Request, body: bytes | None) -> bool:
        return item.method.upper() == "GET"


class SuccessResponseFilter(BaseFilter[Response]):
    """Filter that only caches successful responses (2xx status codes).

    We use FilterPolicy instead of SpecificationPolicy because responses may lack
    proper Cache-Control headers or have no-cache directives. FilterPolicy ignores
    cache headers and caches all 200 responses for consistent behavior.
    """

    def needs_body(self) -> bool:
        return False

    def apply(self, item: Response, body: bytes | None) -> bool:
        return 200 <= item.status_code < 300


# Initialize cache storage and policy
_CACHE_DIR = Path(os.getenv(CACHE_DIR_ENV_VAR, DEFAULT_CACHE_DIR))
_CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_STORAGE = SyncSqliteStorage(database_path=str(_CACHE_DIR / "hishel_cache.db"))
CACHE_POLICY = FilterPolicy(
    request_filters=[GetMethodFilter()],
    response_filters=[SuccessResponseFilter()],
)


def build_client(
    *,
    timeout: float,
    headers: dict[str, str] | None = None,
    use_cache: bool = True,
) -> httpx.Client:
    """Build an HTTP client with optional caching.

    Args:
        timeout: Request timeout in seconds.
        headers: Additional headers to include. DEFAULT_USER_AGENT is always added.
        use_cache: Whether to enable response caching.

    Returns:
        A configured httpx.Client (cached or regular).
    """
    merged_headers = {"User-Agent": DEFAULT_USER_AGENT}
    if headers:
        merged_headers.update(headers)

    if use_cache:
        return SyncCacheClient(
            storage=CACHE_STORAGE,
            policy=CACHE_POLICY,
            follow_redirects=True,
            headers=merged_headers,
            timeout=timeout,
        )

    return httpx.Client(
        follow_redirects=True,
        headers=merged_headers,
        timeout=timeout,
    )
