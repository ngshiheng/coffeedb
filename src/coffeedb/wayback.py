"""Wayback Machine helpers for snapshot discovery and archived page fetches."""

import time

from coffeedb.client import build_client
from coffeedb.constants import (
    DEFAULT_WAYBACK_DELAY_SECONDS,
    WAYBACK_CDX_API_URL,
    WAYBACK_HTTP_TIMEOUT_SECONDS,
    build_wayback_url,
)

CDX_FIELDS = "timestamp,statuscode"
CDX_OUTPUT_FORMAT = "json"
CDX_STATUS_FILTER = "statuscode:200"
CDX_COLLAPSE_BY_DAY = "timestamp:8"
CDX_HEADER_ROWS = 1
WAYBACK_USER_AGENT = "coffeedb-scraper/1.0 (historical research)"

_WAYBACK_HEADERS = {"User-Agent": WAYBACK_USER_AGENT}


def _fetch_json(
    url: str,
    *,
    params: dict[str, str],
    timeout: float,
    headers: dict[str, str],
    use_cache: bool,
) -> list | dict:
    with build_client(timeout=timeout, headers=headers, use_cache=use_cache) as client:
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
    with build_client(timeout=timeout, headers=headers, use_cache=use_cache) as client:
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
