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


_CACHE_POLICY = FilterPolicy(
    request_filters=[GetMethodFilter()],
    response_filters=[SuccessResponseFilter()],
)

# Lazily initialized on first use so importing this module has no filesystem side effects.
_cache_storage: SyncSqliteStorage | None = None


def _get_cache_storage() -> SyncSqliteStorage:
    global _cache_storage
    if _cache_storage is None:
        cache_dir = Path(os.getenv(CACHE_DIR_ENV_VAR, DEFAULT_CACHE_DIR))
        cache_dir.mkdir(parents=True, exist_ok=True)
        _cache_storage = SyncSqliteStorage(
            database_path=str(cache_dir / "hishel_cache.db")
        )
    return _cache_storage


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
            storage=_get_cache_storage(),
            policy=_CACHE_POLICY,
            follow_redirects=True,
            headers=merged_headers,
            timeout=timeout,
        )

    return httpx.Client(
        follow_redirects=True,
        headers=merged_headers,
        timeout=timeout,
    )
