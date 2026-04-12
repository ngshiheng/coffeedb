"""Shared constants and URL helpers for the coffeedb package."""

BASE_SITE_URL = "https://theworlds100bestcoffeeshops.com"
LIST_PATH = "/top-100-coffee-shops/"
DETAIL_PATH = "/locales/"

LIST_URL = f"{BASE_SITE_URL}{LIST_PATH}"
DETAIL_BASE_URL = f"{BASE_SITE_URL}{DETAIL_PATH}"

WAYBACK_CDX_API_URL = "https://web.archive.org/cdx/search/cdx"
WAYBACK_BASE_URL = "https://web.archive.org/web"

DEFAULT_HTTP_TIMEOUT_SECONDS = 30.0
SCRAPER_HTTP_TIMEOUT_SECONDS = 20.0
WAYBACK_HTTP_TIMEOUT_SECONDS = DEFAULT_HTTP_TIMEOUT_SECONDS
DEFAULT_WAYBACK_DELAY_SECONDS = 1.0


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

CACHE_DIR_ENV_VAR = "COFFEEDB_CACHE_DIR"
DEFAULT_CACHE_DIR = ".cache/"

RANK_MIN = 1
RANK_MAX = 200


def build_detail_url(slug: str) -> str:
    """Return the live detail page URL for a shop slug."""
    return f"{DETAIL_BASE_URL}{slug}/"


def build_wayback_url(timestamp: str, target_url: str) -> str:
    """Return the Wayback Machine URL for an archived page."""
    return f"{WAYBACK_BASE_URL}/{timestamp}/{target_url}"
