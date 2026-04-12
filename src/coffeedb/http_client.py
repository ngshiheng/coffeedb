"""Cached HTTP client helpers shared by the live and Wayback scrapers."""

from __future__ import annotations

import os
from pathlib import Path

import httpx
from hishel import BaseFilter, FilterPolicy, Request, Response, SyncSqliteStorage
from hishel.httpx import SyncCacheTransport

from coffeedb.constants import (
    CACHE_DEBUG_ENV_VAR,
    CACHE_DIR_ENV_VAR,
    DEFAULT_CACHE_DIR,
    DEFAULT_HTTP_TIMEOUT_SECONDS,
    DEFAULT_USER_AGENT,
)

DEFAULT_HEADERS = {"User-Agent": DEFAULT_USER_AGENT}

_CACHE_DIR = Path(os.getenv(CACHE_DIR_ENV_VAR, DEFAULT_CACHE_DIR))
_CACHE_DIR.mkdir(parents=True, exist_ok=True)


class _GetMethodFilter(BaseFilter[Request]):
    def needs_body(self) -> bool:
        return False

    def apply(self, item: Request, _body: bytes | None) -> bool:
        return item.method.upper() == "GET"


class _SuccessResponseFilter(BaseFilter[Response]):
    def needs_body(self) -> bool:
        return False

    def apply(self, item: Response, _body: bytes | None) -> bool:
        return 200 <= item.status_code < 300


_CACHE_STORAGE = SyncSqliteStorage(database_path=str(_CACHE_DIR / "hishel_cache.db"))
_CACHE_POLICY = FilterPolicy(
    request_filters=[_GetMethodFilter()],
    response_filters=[_SuccessResponseFilter()],
)


def _cache_debug_enabled() -> bool:
    return os.getenv(CACHE_DEBUG_ENV_VAR, "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _emit_cache_telemetry(resp: httpx.Response, use_cache: bool) -> None:
    if not _cache_debug_enabled():
        return

    if not use_cache:
        cache_state = "bypass"
    else:
        from_cache = resp.extensions.get("hishel_from_cache")
        cache_state = "hit" if from_cache else "miss"

    print(
        f"[coffeedb-cache] {cache_state} status={resp.status_code} "
        f"{resp.request.method} {resp.request.url}"
    )


def _build_client(timeout: float, headers: dict, use_cache: bool) -> httpx.Client:
    if use_cache:
        transport: httpx.BaseTransport = SyncCacheTransport(
            next_transport=httpx.HTTPTransport(),
            storage=_CACHE_STORAGE,
            policy=_CACHE_POLICY,
        )
    else:
        transport = httpx.HTTPTransport()

    return httpx.Client(
        follow_redirects=True,
        headers=headers,
        timeout=timeout,
        transport=transport,
    )


def fetch_text(
    url: str,
    *,
    params: dict | None = None,
    timeout: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
    headers: dict | None = None,
    use_cache: bool = True,
) -> str:
    merged_headers = {**DEFAULT_HEADERS, **(headers or {})}
    with _build_client(
        timeout=timeout, headers=merged_headers, use_cache=use_cache
    ) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        _emit_cache_telemetry(resp, use_cache=use_cache)
        return resp.text


def fetch_json(
    url: str,
    *,
    params: dict | None = None,
    timeout: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
    headers: dict | None = None,
    use_cache: bool = True,
) -> list | dict:
    merged_headers = {**DEFAULT_HEADERS, **(headers or {})}
    with _build_client(
        timeout=timeout, headers=merged_headers, use_cache=use_cache
    ) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        _emit_cache_telemetry(resp, use_cache=use_cache)
        return resp.json()
