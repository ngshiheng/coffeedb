from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlencode

import httpx

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

_CACHE_DIR = Path(os.getenv("COFFEEDB_CACHE_DIR", ".cache/coffeedb/http"))


def _stable_query(params: dict | None) -> str:
    if not params:
        return ""
    return urlencode(sorted((str(k), str(v)) for k, v in params.items()), doseq=True)


def _cache_path(url: str, params: dict | None, suffix: str) -> Path:
    key_src = f"GET|{url}|{_stable_query(params)}"
    key = hashlib.sha256(key_src.encode("utf-8")).hexdigest()
    return _CACHE_DIR / f"{key}.{suffix}"


def _read_cache(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def _write_cache(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data, encoding="utf-8")


def fetch_text(
    url: str,
    *,
    params: dict | None = None,
    timeout: float = 30.0,
    headers: dict | None = None,
    use_cache: bool = True,
) -> str:
    cache_file = _cache_path(url, params, "txt")
    if use_cache:
        cached = _read_cache(cache_file)
        if cached is not None:
            return cached

    merged_headers = {**DEFAULT_HEADERS, **(headers or {})}
    with httpx.Client(
        follow_redirects=True, headers=merged_headers, timeout=timeout
    ) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        text = resp.text

    if use_cache:
        _write_cache(cache_file, text)
    return text


def fetch_json(
    url: str,
    *,
    params: dict | None = None,
    timeout: float = 30.0,
    headers: dict | None = None,
    use_cache: bool = True,
) -> list | dict:
    cache_file = _cache_path(url, params, "json")
    if use_cache:
        cached = _read_cache(cache_file)
        if cached is not None:
            return json.loads(cached)

    merged_headers = {**DEFAULT_HEADERS, **(headers or {})}
    with httpx.Client(
        follow_redirects=True, headers=merged_headers, timeout=timeout
    ) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        payload = resp.json()

    if use_cache:
        _write_cache(cache_file, json.dumps(payload))
    return payload
