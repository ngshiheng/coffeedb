import re
from urllib.parse import urljoin, urlparse

from parsel import Selector

from coffeedb.http_client import fetch_text


def _fetch(url: str, use_cache: bool = True) -> str:
    return fetch_text(url, timeout=20.0, use_cache=use_cache)


LIST_URL = "https://theworlds100bestcoffeeshops.com/top-100-coffee-shops/"


def _first_non_empty(values: list[str]) -> str | None:
    for value in values:
        cleaned = value.strip()
        if cleaned:
            return cleaned
    return None


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"\s+", " ", value).strip()
    return cleaned or None


def _extract_bg_image_urls(style: str | None) -> list[str]:
    if not style:
        return []
    return [
        m.strip(" '\"")
        for m in re.findall(
            r"background-image\s*:\s*url\(([^)]+)\)", style, flags=re.IGNORECASE
        )
    ]


def _parse_rank_from_item(item: Selector, fallback: int) -> int:
    rank_candidates = item.css("h2::text, p::text").getall()
    for text in rank_candidates:
        cleaned = _clean_text(text)
        if not cleaned:
            continue
        match = re.fullmatch(r"\d{1,3}", cleaned)
        if not match:
            continue
        value = int(cleaned)
        if 1 <= value <= 200:
            return value
    return fallback


def _parse_country_from_item(item: Selector, name: str | None) -> str:
    texts = [_clean_text(t) for t in item.css("p::text, a::text").getall()]
    candidates = [t for t in texts if t]
    if name:
        candidates = [t for t in candidates if t != name]

    for text in reversed(candidates):
        if text.startswith("http"):
            continue
        if re.fullmatch(r"\d{1,3}", text):
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

    items = sel.css("div.e-loop-item")
    if not items:
        items = sel.xpath(
            "//div[contains(@data-elementor-type, 'loop-item') and contains(@class, 'e-loop-item')]"
        )

    for idx, item in enumerate(items, start=1):
        item_url = item.css("a[href*='/locales/']::attr(href)").get()
        if not item_url:
            continue

        rank = _parse_rank_from_item(item, fallback=idx)
        name = _first_non_empty(
            [
                t
                for t in [
                    item.css("h1 a::text").get(),
                    item.css("h1::text").get(),
                    item.css("a[href*='/locales/']::text").get(),
                ]
                if t
            ]
        )
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
    """Return a dict with shop detail fields."""
    if html is None:
        html = _fetch(url, use_cache=use_cache)

    sel = Selector(text=html)
    root = sel.css("div[data-elementor-type='single-post']")
    page = root if root else sel

    name = _clean_text(
        page.css("h1.elementor-heading-title a::text").get()
        or page.css("h1.elementor-heading-title::text").get()
    )

    contact_section = page.xpath(
        ".//h2[normalize-space()='Contact']/ancestor::div[contains(@class, 'e-parent')][1]"
    )
    contact_links = contact_section.css("a[href^='http']::attr(href)").getall()
    website_candidates = (
        contact_links or page.css("a[href^='http']::attr(href)").getall()
    )
    website = _first_non_empty(
        [
            link
            for link in website_candidates
            if "instagram.com" not in link
            and "theworlds100bestcoffeeshops.com" not in link
            and "linkedin.com" not in link
        ]
    )
    instagram = _first_non_empty(
        [link for link in contact_links if "instagram.com" in link]
    ) or _first_non_empty(
        [
            link
            for link in page.css("a[href*='instagram.com']::attr(href)").getall()
            if "theworlds100bestcoffeeshops" not in link
        ]
    )

    heading_values = [
        _clean_text(t)
        for t in page.css("p.elementor-heading-title::text").getall()
        if _clean_text(t)
    ]

    city = heading_values[0] if len(heading_values) > 0 else None
    country = heading_values[1] if len(heading_values) > 1 else None
    address = heading_values[2] if len(heading_values) > 2 else None

    if not address:
        address = _first_non_empty(
            [
                _clean_text(t) or ""
                for t in contact_section.css("p::text").getall()
                if _clean_text(t)
                and re.search(r"\d", _clean_text(t) or "")
                and "http" not in (_clean_text(t) or "")
            ]
        )

    if (not city or not country) and address and "," in address:
        parts = [p.strip() for p in address.split(",") if p.strip()]
        if parts and not country:
            country = parts[-1]
        if len(parts) >= 2 and not city:
            city_part = re.sub(r"^\d+[A-Za-z-]*\s+", "", parts[-2]).strip()
            city = city_part or parts[-2]

    description_parts = [
        _clean_text(t)
        for t in page.css("div.elementor-widget-theme-post-content p::text").getall()
        if _clean_text(t)
    ]
    description = "\n\n".join(description_parts) if description_parts else None

    image_urls: list[str] = []
    for style in page.css("div.elementor-carousel-image::attr(style)").getall():
        for raw in _extract_bg_image_urls(style):
            absolute = urljoin(url, raw)
            if absolute not in image_urls:
                image_urls.append(absolute)

    for raw in page.css("div.elementor-carousel-image img::attr(src)").getall():
        absolute = urljoin(url, raw)
        if absolute not in image_urls:
            image_urls.append(absolute)

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
