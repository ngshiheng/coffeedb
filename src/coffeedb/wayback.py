import time

import httpx

from coffeedb.http_client import fetch_json, fetch_text

CDX_API = "https://web.archive.org/cdx/search/cdx"
WAYBACK_BASE = "https://web.archive.org/web"

_WAYBACK_HEADERS = {"User-Agent": "coffeedb-scraper/1.0 (historical research)"}


def get_snapshots(target_url: str, use_cache: bool = True) -> list[dict]:
    """Query the Wayback CDX API and return available snapshots.

    Returns a list of dicts: {timestamp, snapshot_date}.
    Collapsed to one per day; only HTTP 200 responses.
    """
    params = {
        "url": target_url,
        "output": "json",
        "fl": "timestamp,statuscode",
        "collapse": "timestamp:8",
        "filter": "statuscode:200",
    }
    try:
        data = fetch_json(
            CDX_API,
            params=params,
            timeout=30.0,
            headers=_WAYBACK_HEADERS,
            use_cache=use_cache,
        )
    except (httpx.HTTPError, ValueError):
        return []

    if not data or len(data) < 2:
        # First row is the header; fewer rows means no results
        return []

    snapshots = []
    for row in data[1:]:  # skip the header row
        timestamp = row[0]
        snapshot_date = f"{timestamp[:4]}-{timestamp[4:6]}-{timestamp[6:8]}"
        snapshots.append({"timestamp": timestamp, "snapshot_date": snapshot_date})
    return snapshots


def fetch_archived(
    timestamp: str, target_url: str, delay: float = 1.0, use_cache: bool = True
) -> str | None:
    """Fetch a Wayback Machine archived page and return its HTML.

    Returns None if the request fails. Always sleeps `delay` seconds after
    the request to respect Wayback Machine rate limits.
    """
    url = f"{WAYBACK_BASE}/{timestamp}/{target_url}"
    try:
        html = fetch_text(
            url,
            timeout=30.0,
            headers=_WAYBACK_HEADERS,
            use_cache=use_cache,
        )
    except httpx.HTTPError:
        html = None
    finally:
        time.sleep(delay)
    return html
