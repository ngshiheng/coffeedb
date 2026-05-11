from unittest.mock import patch

import httpx
import pytest

from coffeedb import wayback


@patch("coffeedb.wayback._fetch_json", side_effect=httpx.HTTPError("boom"))
def test_get_snapshots_raises_on_http_error(mock_fetch_json) -> None:
    with pytest.raises(RuntimeError, match="Wayback CDX API request failed"):
        wayback.get_snapshots("https://example.com")

    assert mock_fetch_json.call_count == wayback.CDX_MAX_RETRIES


@patch("coffeedb.wayback._fetch_json")
def test_get_snapshots_parses_valid_rows(mock_fetch_json) -> None:
    mock_fetch_json.return_value = [
        ["timestamp", "statuscode"],
        ["20240101101010", "200"],
        ["20240102101010", "200"],
    ]

    snapshots = wayback.get_snapshots("https://example.com")

    assert snapshots == [
        {"timestamp": "20240101101010", "snapshot_date": "2024-01-01"},
        {"timestamp": "20240102101010", "snapshot_date": "2024-01-02"},
    ]


@patch("coffeedb.wayback.time.sleep")
@patch("coffeedb.wayback._fetch_text")
def test_fetch_archived_returns_html_and_cache_flag(
    mock_fetch_text, mock_sleep
) -> None:
    mock_fetch_text.return_value = ("<html></html>", True)

    html, from_cache = wayback.fetch_archived("20240101101010", "https://example.com")

    assert html == "<html></html>"
    assert from_cache is True
    mock_sleep.assert_called_once_with(wayback.DEFAULT_WAYBACK_DELAY_SECONDS)


@patch("coffeedb.wayback.time.sleep")
@patch("coffeedb.wayback._fetch_text", side_effect=httpx.HTTPError("boom"))
def test_fetch_archived_returns_none_on_http_error(mock_fetch_text, mock_sleep) -> None:
    html, from_cache = wayback.fetch_archived("20240101101010", "https://example.com")

    assert html is None
    assert from_cache is False
    mock_fetch_text.assert_called_once()
    mock_sleep.assert_called_once_with(wayback.DEFAULT_WAYBACK_DELAY_SECONDS)
