"""Typer command-line interface for scraping and querying coffee shop snapshots."""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import nullcontext
from datetime import date
from typing import Any, Mapping

import typer

from coffeedb import db as database
from coffeedb import scraper as scraper_module
from coffeedb import wayback
from coffeedb.constants import (
    LIST_URL,
    build_detail_url,
    build_wayback_url,
)

_DB_OPTION = typer.Option("coffee.db", "--db", help="Path to the SQLite database.")

app = typer.Typer(
    name="coffeedb",
    help="Scrape and query the World's 100 Best Coffee Shops - live and historical.",
    no_args_is_help=True,
)
scrape_app = typer.Typer(help="Scrape coffee shop data.", no_args_is_help=True)

app.add_typer(scrape_app, name="scrape")

logger = logging.getLogger(__name__)


def _build_detail_fields(
    detail: Mapping[str, Any] | None,
    *,
    fallback_name: str | None,
    fallback_country: str | None,
) -> dict[str, Any]:
    """Normalize scraped detail data into the database payload shape."""
    payload = dict(detail or {})
    image_urls = payload.get("image_urls")
    if not isinstance(image_urls, list):
        image_urls = []

    return {
        "name": payload.get("name") or fallback_name,
        "city": payload.get("city"),
        "country": payload.get("country") or fallback_country,
        "address": payload.get("address"),
        "website": payload.get("website"),
        "instagram": payload.get("instagram"),
        "description": payload.get("description"),
        "image_urls": json.dumps(image_urls),
    }


def _normalize_detail_fields_or_none(
    detail: Mapping[str, Any] | None,
    *,
    fallback_name: str | None,
    fallback_country: str | None,
    shop_slug: str,
    detail_url: str,
    snapshot_date: str | None = None,
) -> dict[str, Any] | None:
    """Return normalized detail payload, or None when extracted detail is empty."""
    if scraper_module.is_empty_detail(detail):
        logger.warning(
            "Skipping empty detail payload for slug=%s snapshot=%s url=%s",
            shop_slug,
            snapshot_date or "live",
            detail_url,
        )
        return None

    return _build_detail_fields(
        detail,
        fallback_name=fallback_name,
        fallback_country=fallback_country,
    )


def _save_shop_snapshot(
    conn: sqlite3.Connection,
    *,
    snapshot_id: int,
    shop: Mapping[str, Any],
    ranking_detail_url: str,
    is_wayback: bool,
    detail_fields: Mapping[str, Any] | None,
) -> None:
    """Persist one ranking row and its detail payload in a single transaction."""
    with conn:
        shop_id = database.get_or_create_shop(
            conn, slug=shop["slug"], auto_commit=False
        )
        database.insert_ranking(
            conn,
            snapshot_id=snapshot_id,
            shop_id=shop_id,
            rank=shop["rank"],
            detail_page_url=ranking_detail_url,
            name_on_page=shop["name"],
            country_on_page=shop["country"],
            auto_commit=False,
        )
        if detail_fields is not None:
            database.upsert_shop_detail(
                conn,
                shop_id=shop_id,
                snapshot_id=snapshot_id,
                is_wayback=is_wayback,
                auto_commit=False,
                **detail_fields,
            )


@app.command()
def init(db: str = _DB_OPTION) -> None:
    """Create database tables (safe to re-run)."""
    database.init_db(db)
    typer.echo(f"Database initialised: {db}")


@scrape_app.command("live")
def scrape_live(
    db: str = _DB_OPTION,
    fresh: bool = typer.Option(
        False,
        "-f",
        "--fresh",
        help="Bypass HTTP cache and fetch fresh responses.",
    ),
    verbose: bool = typer.Option(
        False, "-v", "--verbose", help="Print each URL being fetched."
    ),
) -> None:
    """Scrape the current live site: list page + all 100 detail pages."""
    database.init_db(db)
    conn = database.get_conn(db)
    use_cache = not fresh

    typer.echo(f"Scraping list: {LIST_URL}")
    shops = scraper_module.scrape_list(LIST_URL, use_cache=use_cache)
    if not shops:
        typer.echo("No shops found on list page. Aborting.", err=True)
        raise typer.Exit(code=1)

    today = date.today().isoformat()
    snapshot_id = database.insert_snapshot(
        conn,
        snapshot_date=today,
        list_page_url=LIST_URL,
        wayback_timestamp=None,
    )
    typer.echo(f"Inserted snapshot id={snapshot_id} ({today})")

    n = len(shops)
    ctx = (
        typer.progressbar(shops, label="Scraping detail pages")
        if not verbose
        else nullcontext(shops)
    )
    with ctx as progress:
        for shop in progress:
            slug = shop["slug"]
            detail_url = build_detail_url(slug)
            if verbose:
                typer.echo(f"  [{shop['rank']:>3}/{n}] {slug}")
            detail = scraper_module.scrape_detail(detail_url, use_cache=use_cache)
            detail_fields = _normalize_detail_fields_or_none(
                detail,
                fallback_name=shop["name"],
                fallback_country=shop["country"],
                shop_slug=slug,
                detail_url=detail_url,
                snapshot_date=today,
            )
            _save_shop_snapshot(
                conn,
                snapshot_id=snapshot_id,
                shop=shop,
                ranking_detail_url=detail_url,
                is_wayback=False,
                detail_fields=detail_fields,
            )

    typer.echo(f"Done. {len(shops)} shops saved.")


@scrape_app.command("historical")
def scrape_historical(
    db: str = _DB_OPTION,
    fresh: bool = typer.Option(
        False,
        "-f",
        "--fresh",
        help="Bypass HTTP cache and fetch fresh responses.",
    ),
    verbose: bool = typer.Option(
        False, "-v", "--verbose", help="Print each URL being fetched."
    ),
) -> None:
    """Scrape all Wayback Machine snapshots of the list page."""
    database.init_db(db)
    conn = database.get_conn(db)
    use_cache = not fresh

    typer.echo("Querying Wayback CDX API...")
    snapshots = wayback.get_snapshots(LIST_URL, use_cache=use_cache)
    if not snapshots:
        typer.echo("No Wayback snapshots found.", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Found {len(snapshots)} snapshot(s) to process.")

    total = len(snapshots)
    ctx = (
        typer.progressbar(snapshots, label="Snapshots")
        if not verbose
        else nullcontext(snapshots)
    )
    with ctx as progress:
        for i, snap in enumerate(progress, 1):
            ts = snap["timestamp"]
            snap_date = snap["snapshot_date"]

            if verbose:
                typer.echo(f"[{i}/{total}] {snap_date}", nl=False)
            html, from_cache = wayback.fetch_archived(ts, LIST_URL, use_cache=use_cache)
            if verbose:
                typer.echo(f"  list:[{'cache' if from_cache else 'fetch'}]", nl=False)
            if html is None:
                if verbose:
                    typer.echo("  failed")
                continue

            shops = scraper_module.scrape_list(LIST_URL, html=html)
            if not shops:
                if verbose:
                    typer.echo("  no shops")
                continue

            if verbose:
                typer.echo(f"  {len(shops)} shops", nl=False)

            snapshot_id = database.insert_snapshot(
                conn,
                snapshot_date=snap_date,
                list_page_url=build_wayback_url(ts, LIST_URL),
                wayback_timestamp=ts,
            )

            failed = 0
            skipped_empty = 0
            total_shops = len(shops)
            for idx, shop in enumerate(shops, 1):
                slug = shop["slug"]
                detail_url = build_detail_url(slug)
                archived_detail_url = build_wayback_url(ts, detail_url)

                detail_html, _from_cache_detail = wayback.fetch_archived(
                    ts, detail_url, use_cache=use_cache
                )
                if detail_html is None:
                    failed += 1
                    logger.warning(
                        "Missing archived detail HTML for slug=%s snapshot=%s url=%s",
                        slug,
                        snap_date,
                        archived_detail_url,
                    )
                    _save_shop_snapshot(
                        conn,
                        snapshot_id=snapshot_id,
                        shop=shop,
                        ranking_detail_url=archived_detail_url,
                        is_wayback=True,
                        detail_fields=None,
                    )
                    if verbose and idx % 10 == 0 and idx < total_shops:
                        typer.echo(
                            f"  |  details:{idx}/{total_shops} (failed:{failed})"
                        )
                    continue

                detail = scraper_module.scrape_detail(
                    detail_url,
                    html=detail_html,
                    use_cache=use_cache,
                )
                detail_fields = _normalize_detail_fields_or_none(
                    detail,
                    fallback_name=shop["name"],
                    fallback_country=shop["country"],
                    shop_slug=slug,
                    detail_url=archived_detail_url,
                    snapshot_date=snap_date,
                )
                if detail_fields is None:
                    skipped_empty += 1

                _save_shop_snapshot(
                    conn,
                    snapshot_id=snapshot_id,
                    shop=shop,
                    ranking_detail_url=archived_detail_url,
                    is_wayback=True,
                    detail_fields=detail_fields,
                )

                if verbose and idx % 10 == 0 and idx < total_shops:
                    typer.echo(f"  |  details:{idx}/{total_shops} (failed:{failed})")

            if verbose:
                saved_details = len(shops) - failed - skipped_empty
                notes: list[str] = []
                if failed:
                    notes.append(f"{failed} failed")
                if skipped_empty:
                    notes.append(f"{skipped_empty} empty")
                suffix = f" ({', '.join(notes)})" if notes else ""
                typer.echo(f"  |  details:{saved_details}/{len(shops)}{suffix}")

    typer.echo("Done.")


if __name__ == "__main__":
    app()
