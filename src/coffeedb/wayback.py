"""Wayback Machine helpers for snapshot discovery and archived page fetches."""

import os
import time
from pathlib import Path

import httpx
from hishel import BaseFilter, FilterPolicy, Request, Response, SyncSqliteStorage
from hishel.httpx import SyncCacheClient

from coffeedb.constants import (
    CACHE_DIR_ENV_VAR,
    DEFAULT_CACHE_DIR,
    DEFAULT_USER_AGENT,
    DEFAULT_WAYBACK_DELAY_SECONDS,
    WAYBACK_CDX_API_URL,
    WAYBACK_HTTP_TIMEOUT_SECONDS,
    build_wayback_url,
)


class _GetMethodFilter(BaseFilter[Request]):
    def needs_body(self) -> bool:
        return False

    def apply(self, item: Request, body: bytes | None) -> bool:
        return item.method.upper() == "GET"


class _SuccessResponseFilter(BaseFilter[Response]):
    def needs_body(self) -> bool:
        return False

    def apply(self, item: Response, body: bytes | None) -> bool:
        return 200 <= item.status_code < 300


CDX_FIELDS = "timestamp,statuscode"
CDX_OUTPUT_FORMAT = "json"
CDX_STATUS_FILTER = "statuscode:200"
CDX_COLLAPSE_BY_DAY = "timestamp:8"
CDX_HEADER_ROWS = 1
WAYBACK_USER_AGENT = "coffeedb-scraper/1.0 (historical research)"

_WAYBACK_HEADERS = {"User-Agent": WAYBACK_USER_AGENT}

_CACHE_DIR = Path(os.getenv(CACHE_DIR_ENV_VAR, DEFAULT_CACHE_DIR))
_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_CACHE_STORAGE = SyncSqliteStorage(database_path=str(_CACHE_DIR / "hishel_cache.db"))
_CACHE_POLICY = FilterPolicy(
    request_filters=[_GetMethodFilter()],
    response_filters=[_SuccessResponseFilter()],
)


def _build_client(
    *, timeout: float, headers: dict[str, str], use_cache: bool
) -> httpx.Client:
    merged_headers = {"User-Agent": DEFAULT_USER_AGENT, **headers}

    if use_cache:
        return SyncCacheClient(
            storage=_CACHE_STORAGE,
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


def _fetch_json(
    url: str,
    *,
    params: dict[str, str],
    timeout: float,
    headers: dict[str, str],
    use_cache: bool,
) -> list | dict:
    with _build_client(timeout=timeout, headers=headers, use_cache=use_cache) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


def _fetch_text(
    url: str,
    *,
    timeout: float,
    headers: dict[str, str],
    use_cache: bool,
) -> str:
    with _build_client(timeout=timeout, headers=headers, use_cache=use_cache) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.text


def _snapshot_date_from_timestamp(timestamp: str) -> str:
    """Convert a Wayback timestamp into a YYYY-MM-DD snapshot date."""
    return f"{timestamp[:4]}-{timestamp[4:6]}-{timestamp[6:8]}"


def get_snapshots(target_url: str, use_cache: bool = True) -> list[dict]:
    """Query the Wayback CDX API and return available snapshots.

    Returns a list of dicts: {timestamp, snapshot_date}.
    Collapsed to one per day; only HTTP 200 responses.
    """
    params = {
        "url": target_url,
        "output": CDX_OUTPUT_FORMAT,
        "fl": CDX_FIELDS,
        "collapse": CDX_COLLAPSE_BY_DAY,
        "filter": CDX_STATUS_FILTER,
    }
    try:
        data = _fetch_json(
            WAYBACK_CDX_API_URL,
            params=params,
            timeout=WAYBACK_HTTP_TIMEOUT_SECONDS,
            headers=_WAYBACK_HEADERS,
            use_cache=use_cache,
        )
    except (httpx.HTTPError, ValueError):
        return []

    if not data or len(data) <= CDX_HEADER_ROWS:
        # First row is the header; fewer rows means no results
        return []

    snapshots = []
    for row in data[CDX_HEADER_ROWS:]:
        timestamp = row[0]
        snapshot_date = _snapshot_date_from_timestamp(timestamp)
        snapshots.append({"timestamp": timestamp, "snapshot_date": snapshot_date})
    return snapshots


def fetch_archived(
    timestamp: str,
    target_url: str,
    use_cache: bool = True,
) -> str | None:
    """Fetch a Wayback Machine archived page and return its HTML.

    Returns None if the request fails. Always sleeps a small fixed delay after
    the request to respect Wayback Machine rate limits.
    """
    url = build_wayback_url(timestamp, target_url)
    try:
        html = _fetch_text(
            url,
            timeout=WAYBACK_HTTP_TIMEOUT_SECONDS,
            headers=_WAYBACK_HEADERS,
            use_cache=use_cache,
        )
    except httpx.HTTPError:
        html = None
    finally:
        time.sleep(DEFAULT_WAYBACK_DELAY_SECONDS)
    return html
