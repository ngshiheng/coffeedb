from unittest.mock import MagicMock, patch

from coffeedb import cli


@patch("coffeedb.cli.scraper_module.is_empty_detail", return_value=True)
def test_normalize_detail_fields_returns_none_for_empty_payload(
    mock_is_empty_detail,
) -> None:
    out = cli._normalize_detail_fields_or_none(
        detail={"name": ""},
        fallback_name="Fallback",
        fallback_country="Japan",
        shop_slug="shop-a",
        detail_url="https://example.com/locales/shop-a/",
        snapshot_date="2026-01-01",
    )

    assert out is None
    mock_is_empty_detail.assert_called_once()


@patch("coffeedb.cli.scraper_module.is_empty_detail", return_value=False)
def test_normalize_detail_fields_applies_fallbacks(mock_is_empty_detail) -> None:
    out = cli._normalize_detail_fields_or_none(
        detail={"name": None, "country": None, "image_urls": ["https://img"]},
        fallback_name="Fallback",
        fallback_country="Japan",
        shop_slug="shop-a",
        detail_url="https://example.com/locales/shop-a/",
        snapshot_date="2026-01-01",
    )

    assert out is not None
    assert out["name"] == "Fallback"
    assert out["country"] == "Japan"
    assert out["image_urls"] == '["https://img"]'
    mock_is_empty_detail.assert_called_once()


@patch("coffeedb.cli.database.upsert_shop_detail")
@patch("coffeedb.cli.database.insert_ranking")
@patch("coffeedb.cli.database.get_or_create_shop", return_value=123)
def test_save_shop_snapshot_writes_ranking_and_detail(
    mock_get_or_create_shop,
    mock_insert_ranking,
    mock_upsert_shop_detail,
) -> None:
    conn = MagicMock()
    conn.__enter__.return_value = conn
    conn.__exit__.return_value = False

    shop = {"slug": "shop-a", "rank": 1, "name": "Shop A", "country": "Japan"}
    detail_fields = {"name": "Shop A", "country": "Japan", "image_urls": "[]"}

    cli._save_shop_snapshot(
        conn,
        snapshot_id=10,
        shop=shop,
        ranking_detail_url="https://example.com/locales/shop-a/",
        is_wayback=False,
        detail_fields=detail_fields,
    )

    mock_get_or_create_shop.assert_called_once_with(
        conn, slug="shop-a", auto_commit=False
    )
    mock_insert_ranking.assert_called_once()
    mock_upsert_shop_detail.assert_called_once()


@patch("coffeedb.cli.database.upsert_shop_detail")
@patch("coffeedb.cli.database.insert_ranking")
@patch("coffeedb.cli.database.get_or_create_shop", return_value=123)
def test_save_shop_snapshot_skips_detail_write_when_detail_is_none(
    mock_get_or_create_shop,
    mock_insert_ranking,
    mock_upsert_shop_detail,
) -> None:
    conn = MagicMock()
    conn.__enter__.return_value = conn
    conn.__exit__.return_value = False

    shop = {"slug": "shop-a", "rank": 1, "name": "Shop A", "country": "Japan"}

    cli._save_shop_snapshot(
        conn,
        snapshot_id=10,
        shop=shop,
        ranking_detail_url="https://example.com/locales/shop-a/",
        is_wayback=True,
        detail_fields=None,
    )

    mock_get_or_create_shop.assert_called_once_with(
        conn, slug="shop-a", auto_commit=False
    )
    mock_insert_ranking.assert_called_once()
    mock_upsert_shop_detail.assert_not_called()
