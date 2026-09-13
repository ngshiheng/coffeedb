"""Wayback Machine helpers for snapshot discovery and archived page fetches."""

import logging
import time
from typing import Any, cast

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
WAYBACK_FETCH_MAX_RETRIES = 3
WAYBACK_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
WAYBACK_RETRY_FALLBACK_DELAY_SECONDS = 1.0
WAYBACK_USER_AGENT = "coffeedb-scraper/1.0 (historical research)"

_WAYBACK_HEADERS = {"User-Agent": WAYBACK_USER_AGENT}
logger = logging.getLogger(__name__)


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


def _wayback_status_code(exc: Exception) -> int | None:
    """Return an HTTP status from a status error, when one is available."""
    response = cast(httpx.Response | None, getattr(exc, "response", None))
    return response.status_code if response is not None else None


def _give_up_wayback_error(exc: Exception) -> bool:
    """Stop retrying for permanent statuses or non-transport HTTP errors."""
    status_code = _wayback_status_code(exc)
    if status_code is not None:
        return status_code not in WAYBACK_RETRYABLE_STATUS_CODES
    return not isinstance(exc, httpx.TransportError)


def _wayback_retry_delay(exc: Exception) -> float:
    """Return a server-provided retry delay or a short local fallback."""
    response = cast(httpx.Response | None, getattr(exc, "response", None))
    if response is not None:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return max(float(retry_after), 0.0)
            except ValueError:
                pass
    return WAYBACK_RETRY_FALLBACK_DELAY_SECONDS


def _log_wayback_retry(details: dict[str, Any]) -> None:
    """Log a retry with the error, attempt, delay, and replay URL."""
    exc = details["exception"]
    status_code = _wayback_status_code(exc)
    error = f"status={status_code}" if status_code is not None else f"error={exc}"
    args = details.get("args", ())
    url = args[0] if args else "?"
    logger.warning(
        "Wayback fetch %s; retrying attempt=%s/%s after %.1fs url=%s",
        error,
        details["tries"] + 1,
        WAYBACK_FETCH_MAX_RETRIES,
        details["wait"],
        url,
    )


@backoff.on_exception(
    backoff.runtime,
    (httpx.HTTPStatusError, httpx.TransportError),
    max_tries=WAYBACK_FETCH_MAX_RETRIES,
    giveup=_give_up_wayback_error,
    jitter=None,
    on_backoff=_log_wayback_retry,
    logger=None,
    value=_wayback_retry_delay,
)
def _fetch_archived_text(
    url: str, *, use_cache: bool
) -> tuple[str, bool]:
    """Fetch one replay, retrying only transient Wayback HTTP failures."""
    return _fetch_text(
        url,
        timeout=WAYBACK_HTTP_TIMEOUT_SECONDS,
        headers=_WAYBACK_HEADERS,
        use_cache=use_cache,
    )


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
    html = ""
    try:
        html, from_cache = _fetch_archived_text(url, use_cache=use_cache)
        if not html.strip():
            logger.warning("Wayback fetch returned an empty body url=%s", url)
            html = None
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Wayback fetch failed status=%s url=%s",
            exc.response.status_code,
            url,
        )
        html = None
    except httpx.HTTPError as exc:
        logger.warning("Wayback fetch failed error=%s url=%s", exc, url)
        html = None
    finally:
        time.sleep(DEFAULT_WAYBACK_DELAY_SECONDS)
    return html, from_cache
