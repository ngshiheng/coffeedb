"""HTML scraping helpers for the live site and archived detail pages."""

import re
from typing import Any, Mapping
from urllib.parse import urljoin, urlparse

from parsel import Selector

from coffeedb.client import build_client
from coffeedb.constants import (
    RANK_MAX,
    RANK_MIN,
    SCRAPER_HTTP_TIMEOUT_SECONDS,
)

WHITESPACE_PATTERN = r"\s+"
BACKGROUND_IMAGE_PATTERN = r"background-image\s*:\s*url\(([^)]+)\)"
RANK_PATTERN = r"\d{1,3}"
ADDRESS_CITY_PREFIX_PATTERN = r"^\d+[A-Za-z-]*\s+"

LIST_ITEM_SELECTOR = "div.e-loop-item"
LIST_ITEM_XPATH = (
    "//div[contains(@data-elementor-type, 'loop-item') and contains(@class, "
    "'e-loop-item')]"
)
DETAIL_LINK_SELECTOR = "a[href*='/locales/']::attr(href)"
LIST_NAME_SELECTORS = (
    "h1 a::text",
    "h1::text",
    "a[href*='/locales/']::text",
)
LIST_RANK_TEXT_SELECTOR = "h2::text, p::text"
LIST_COUNTRY_TEXT_SELECTOR = "p::text, a::text"

DETAIL_ROOT_SELECTOR = "div[data-elementor-type='single-post']"
DETAIL_NAME_SELECTORS = (
    "h1.elementor-heading-title a::text",
    "h1.elementor-heading-title::text",
)
CONTACT_SECTION_XPATH = (
    ".//h2[normalize-space()='Contact']/ancestor::div[contains(@class, 'e-parent')][1]"
)
HTTP_LINK_SELECTOR = "a[href^='http']::attr(href)"
INSTAGRAM_LINK_SELECTOR = "a[href*='instagram.com']::attr(href)"
HEADING_VALUE_SELECTOR = "p.elementor-heading-title::text"
CONTACT_TEXT_SELECTOR = "p::text"
DESCRIPTION_SELECTOR = "div.elementor-widget-theme-post-content p::text"
CAROUSEL_STYLE_SELECTOR = "div.elementor-carousel-image::attr(style)"
CAROUSEL_IMAGE_SELECTOR = "div.elementor-carousel-image img::attr(src)"

CITY_INDEX = 0
COUNTRY_INDEX = 1
ADDRESS_INDEX = 2

EXCLUDED_WEBSITE_TOKENS = (
    "instagram.com",
    "theworlds100bestcoffeeshops.com",
    "linkedin.com",
)
EXCLUDED_INSTAGRAM_TOKENS = ("theworlds100bestcoffeeshops",)
INSTAGRAM_DOMAIN_TOKEN = "instagram.com"

DETAIL_TEXT_FIELDS = (
    "name",
    "city",
    "country",
    "address",
    "website",
    "instagram",
    "description",
)


def _fetch(url: str, use_cache: bool = True) -> str:
    with build_client(
        timeout=SCRAPER_HTTP_TIMEOUT_SECONDS, use_cache=use_cache
    ) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.text


def _first_non_empty(values: list[str]) -> str | None:
    for value in values:
        cleaned = value.strip()
        if cleaned:
            return cleaned
    return None


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(WHITESPACE_PATTERN, " ", value).strip()
    return cleaned or None


def _extract_bg_image_urls(style: str | None) -> list[str]:
    if not style:
        return []
    return [
        m.strip(" '\"")
        for m in re.findall(BACKGROUND_IMAGE_PATTERN, style, flags=re.IGNORECASE)
    ]


def _cleaned_values(values: list[str]) -> list[str]:
    cleaned_values: list[str] = []
    for value in values:
        cleaned = _clean_text(value)
        if cleaned:
            cleaned_values.append(cleaned)
    return cleaned_values


def _first_text(item: Selector, selectors: tuple[str, ...]) -> str | None:
    for selector in selectors:
        text = _clean_text(item.css(selector).get())
        if text:
            return text
    return None


def _select_primary_link(
    links: list[str], excluded_tokens: tuple[str, ...]
) -> str | None:
    return _first_non_empty(
        [link for link in links if all(token not in link for token in excluded_tokens)]
    )


def _heading_value(values: list[str], index: int) -> str | None:
    if index >= len(values):
        return None
    return values[index]


def _extract_contact_links(
    contact_section: Selector, page: Selector
) -> tuple[list[str], list[str]]:
    contact_links = contact_section.css(HTTP_LINK_SELECTOR).getall()
    page_links = page.css(HTTP_LINK_SELECTOR).getall()
    return contact_links, page_links


def _extract_address(contact_section: Selector) -> str | None:
    address_candidates = [
        text
        for text in _cleaned_values(contact_section.css(CONTACT_TEXT_SELECTOR).getall())
        if re.search(r"\d", text) and "http" not in text
    ]
    return _first_non_empty(address_candidates)


def _infer_city_and_country(
    address: str | None,
    city: str | None,
    country: str | None,
) -> tuple[str | None, str | None]:
    if (city and country) or not address or "," not in address:
        return city, country

    parts = [part.strip() for part in address.split(",") if part.strip()]
    inferred_country = country or (parts[-1] if parts else None)
    inferred_city = city
    if len(parts) >= 2 and not inferred_city:
        city_part = re.sub(ADDRESS_CITY_PREFIX_PATTERN, "", parts[-2]).strip()
        inferred_city = city_part or parts[-2]
    return inferred_city, inferred_country


def _extract_description(page: Selector) -> str | None:
    description_parts = _cleaned_values(page.css(DESCRIPTION_SELECTOR).getall())
    if not description_parts:
        return None
    return "\n\n".join(description_parts)


def _extract_image_urls(page: Selector, page_url: str) -> list[str]:
    image_urls: list[str] = []

    for style in page.css(CAROUSEL_STYLE_SELECTOR).getall():
        for raw_url in _extract_bg_image_urls(style):
            absolute_url = urljoin(page_url, raw_url)
            if absolute_url not in image_urls:
                image_urls.append(absolute_url)

    for raw_url in page.css(CAROUSEL_IMAGE_SELECTOR).getall():
        absolute_url = urljoin(page_url, raw_url)
        if absolute_url not in image_urls:
            image_urls.append(absolute_url)

    return image_urls


def _parse_rank_from_item(item: Selector, fallback: int) -> int:
    rank_candidates = item.css(LIST_RANK_TEXT_SELECTOR).getall()
    for text in rank_candidates:
        cleaned = _clean_text(text)
        if not cleaned:
            continue
        match = re.fullmatch(RANK_PATTERN, cleaned)
        if not match:
            continue
        value = int(cleaned)
        if RANK_MIN <= value <= RANK_MAX:
            return value
    return fallback


def _parse_country_from_item(item: Selector, name: str | None) -> str:
    candidates = _cleaned_values(item.css(LIST_COUNTRY_TEXT_SELECTOR).getall())
    if name:
        candidates = [t for t in candidates if t != name]

    for text in reversed(candidates):
        if text.startswith("http"):
            continue
        if re.fullmatch(RANK_PATTERN, text):
            continue
        if len(text) > 40:
            continue
        return text
    return ""


def _slug_from_url(url: str) -> str:
    """Extract the shop slug from a detail-page URL."""
    path = urlparse(url).path.rstrip("/")
    return path.split("/")[-1]


def scrape_list(
    url: str, html: str | None = None, use_cache: bool = True
) -> list[dict]:
    """Return a list of dicts with keys: rank, name, slug, country."""
    if html is None:
        html = _fetch(url, use_cache=use_cache)
    sel = Selector(text=html)
    rows: list[dict] = []

    items = sel.css(LIST_ITEM_SELECTOR)
    if not items:
        items = sel.xpath(LIST_ITEM_XPATH)

    for idx, item in enumerate(items, start=1):
        item_url = item.css(DETAIL_LINK_SELECTOR).get()
        if not item_url:
            continue

        rank = _parse_rank_from_item(item, fallback=idx)
        name = _first_text(item, LIST_NAME_SELECTORS)
        country = _parse_country_from_item(item, name)

        rows.append(
            {
                "rank": rank,
                "name": name or "",
                "slug": _slug_from_url(item_url),
                "country": country,
            }
        )

    rows.sort(key=lambda r: r["rank"])
    return rows


def scrape_detail(url: str, html: str | None = None, use_cache: bool = True) -> dict:
    """Return a dict with detail fields parsed from an Elementor detail page."""
    if html is None:
        html = _fetch(url, use_cache=use_cache)

    sel = Selector(text=html)
    root = sel.css(DETAIL_ROOT_SELECTOR)
    page = root if root else sel

    name = _first_text(page, DETAIL_NAME_SELECTORS)

    contact_section = page.xpath(CONTACT_SECTION_XPATH)
    contact_links, page_links = _extract_contact_links(contact_section, page)
    website_candidates = contact_links or page_links
    website = _select_primary_link(website_candidates, EXCLUDED_WEBSITE_TOKENS)
    instagram = _first_non_empty(
        [link for link in contact_links if INSTAGRAM_DOMAIN_TOKEN in link]
    ) or _select_primary_link(
        page.css(INSTAGRAM_LINK_SELECTOR).getall(), EXCLUDED_INSTAGRAM_TOKENS
    )

    heading_values = _cleaned_values(page.css(HEADING_VALUE_SELECTOR).getall())

    city = _heading_value(heading_values, CITY_INDEX)
    country = _heading_value(heading_values, COUNTRY_INDEX)
    address = _heading_value(heading_values, ADDRESS_INDEX)

    if not address:
        address = _extract_address(contact_section)

    city, country = _infer_city_and_country(address, city, country)
    description = _extract_description(page)
    image_urls = _extract_image_urls(page, url)

    return {
        "name": name,
        "city": city,
        "country": country,
        "address": address,
        "website": website,
        "instagram": instagram,
        "description": description,
        "image_urls": image_urls,
    }


def is_empty_detail(detail: Mapping[str, Any] | None) -> bool:
    """Return True when a detail payload contains no meaningful extracted data."""
    if not detail:
        return True

    for field in DETAIL_TEXT_FIELDS:
        value = _clean_text(str(detail.get(field))) if detail.get(field) else None
        if value:
            return False

    image_urls = detail.get("image_urls")
    return not isinstance(image_urls, list) or len(image_urls) == 0
