"""Wayback Machine helpers for snapshot discovery and archived page fetches."""

import time

import backoff
import httpx

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
CDX_MAX_RETRIES = 3
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
) -> tuple[str, bool]:
    with build_client(timeout=timeout, headers=headers, use_cache=use_cache) as client:
        resp = client.get(url)
        resp.raise_for_status()
        from_cache = bool(resp.extensions.get("hishel_from_cache", False))
        return resp.text, from_cache


def _snapshot_date_from_timestamp(timestamp: str) -> str:
    """Convert a Wayback timestamp into a YYYY-MM-DD snapshot date."""
    return f"{timestamp[:4]}-{timestamp[4:6]}-{timestamp[6:8]}"


class _EmptyCDXResponse(Exception):
    """Raised when the CDX API returns a valid but empty response, to trigger a retry."""


@backoff.on_exception(
    backoff.expo,
    (httpx.HTTPError, _EmptyCDXResponse),
    max_tries=CDX_MAX_RETRIES,
    jitter=backoff.full_jitter,
)
def _fetch_cdx(params: dict[str, str], use_cache: bool) -> list:
    data = _fetch_json(
        WAYBACK_CDX_API_URL,
        params=params,
        timeout=WAYBACK_HTTP_TIMEOUT_SECONDS,
        headers=_WAYBACK_HEADERS,
        use_cache=use_cache,
    )
    if not isinstance(data, list) or len(data) <= CDX_HEADER_ROWS:
        raise _EmptyCDXResponse
    return data


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
        data = _fetch_cdx(params, use_cache)
    except _EmptyCDXResponse:
        return []
    except httpx.HTTPError as exc:
        raise RuntimeError(
            f"Wayback CDX API request failed after {CDX_MAX_RETRIES} attempts: {exc}"
        ) from exc
    except ValueError as exc:
        raise RuntimeError(
            f"Wayback CDX API returned unexpected response: {exc}"
        ) from exc

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
) -> tuple[str | None, bool]:
    """Fetch a Wayback Machine archived page and return its HTML and cache status.

    Returns (html, from_cache). html is None if the request fails. Always sleeps
    a small fixed delay after the request to respect Wayback Machine rate limits.
    """
    url = build_wayback_url(timestamp, target_url)
    from_cache = False
    try:
        html, from_cache = _fetch_text(
            url,
            timeout=WAYBACK_HTTP_TIMEOUT_SECONDS,
            headers=_WAYBACK_HEADERS,
            use_cache=use_cache,
        )
    except httpx.HTTPError:
        html = None
    finally:
        time.sleep(DEFAULT_WAYBACK_DELAY_SECONDS)
    return html, from_cache
