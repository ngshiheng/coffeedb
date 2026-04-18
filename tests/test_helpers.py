from datetime import datetime

from hypothesis import given
from hypothesis import strategies as st

from coffeedb.constants import (
    BASE_SITE_URL,
    WAYBACK_BASE_URL,
    build_detail_url,
    build_wayback_url,
)
from coffeedb.scraper import (
    _clean_text,
    _cleaned_values,
    _extract_bg_image_urls,
    _first_non_empty,
    _infer_city_and_country,
    _slug_from_url,
    is_empty_detail,
)
from coffeedb.wayback import _snapshot_date_from_timestamp


@given(st.one_of(st.none(), st.text()))
def test_clean_text_is_idempotent(value: str | None) -> None:
    cleaned = _clean_text(value)
    assert _clean_text(cleaned) == cleaned


@given(st.lists(st.text()))
def test_first_non_empty_matches_reference(values: list[str]) -> None:
    expected = next((v.strip() for v in values if v.strip()), None)
    assert _first_non_empty(values) == expected


@given(st.lists(st.text()))
def test_cleaned_values_matches_clean_text_filter(values: list[str]) -> None:
    expected = [clean for clean in (_clean_text(v) for v in values) if clean]
    assert _cleaned_values(values) == expected


def test_extract_bg_image_urls_handles_multiple_formats() -> None:
    style = "background-image: url('a.jpg'); background-image:url(\"b.png\");"
    assert _extract_bg_image_urls(style) == ["a.jpg", "b.png"]


@given(st.from_regex(r"[a-z0-9-]{1,40}", fullmatch=True))
def test_build_detail_url_includes_slug(slug: str) -> None:
    url = build_detail_url(slug)
    assert url == f"{BASE_SITE_URL}/locales/{slug}/"


@given(
    st.from_regex(r"\d{14}", fullmatch=True),
    st.from_regex(
        r"https?://[a-z0-9.-]+(?:/[a-z0-9._~:/?#\[\]@!$&'()*+,;=-]*)?", fullmatch=True
    ),
)
def test_build_wayback_url_shape(timestamp: str, target_url: str) -> None:
    url = build_wayback_url(timestamp, target_url)
    assert url.startswith(f"{WAYBACK_BASE_URL}/{timestamp}/")
    assert url.endswith(target_url)


@given(st.datetimes(min_value=datetime(1996, 1, 1), max_value=datetime(2099, 12, 31)))
def test_snapshot_date_from_timestamp_returns_iso_date(dt: datetime) -> None:
    timestamp = dt.strftime("%Y%m%d%H%M%S")
    snapshot_date = _snapshot_date_from_timestamp(timestamp)
    parsed = datetime.strptime(snapshot_date, "%Y-%m-%d")
    assert parsed.strftime("%Y-%m-%d") == snapshot_date


def test_slug_from_url_extracts_last_path_component() -> None:
    assert _slug_from_url("https://example.com/locales/shop-name/") == "shop-name"


def test_infer_city_and_country_from_address() -> None:
    city, country = _infer_city_and_country("123 Main St, Oslo, Norway", None, None)
    assert city == "Oslo"
    assert country == "Norway"


def test_infer_city_and_country_preserves_existing_values() -> None:
    city, country = _infer_city_and_country(
        "123 Main St, Oslo, Norway",
        "Existing City",
        "Existing Country",
    )
    assert city == "Existing City"
    assert country == "Existing Country"


def test_is_empty_detail_true_for_missing_content() -> None:
    assert is_empty_detail({"name": " ", "image_urls": []}) is True


def test_is_empty_detail_false_when_any_text_is_present() -> None:
    assert is_empty_detail({"name": "Cafe", "image_urls": []}) is False


def test_is_empty_detail_false_when_images_are_present() -> None:
    assert is_empty_detail({"name": None, "image_urls": ["https://img"]}) is False
