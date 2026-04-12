"""Typer command-line interface for scraping and querying coffee shop snapshots."""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from typing import Any, Mapping, Optional

import typer

from coffeedb import db as database
from coffeedb import scraper as scraper_module
from coffeedb import wayback
from coffeedb.constants import (
    DEFAULT_WAYBACK_DELAY_SECONDS,
    LIST_URL,
    build_detail_url,
    build_wayback_url,
)

DEFAULT_HISTORICAL_LIMIT = 0
DEFAULT_TOP_RESULTS = 10
TOP_COLUMN_WIDTHS = (5, 40, 25, 35)
HISTORY_COLUMN_WIDTHS = (12, 10, 6, 35, 25)

app = typer.Typer(
    name="coffeedb",
    help="Scrape and query the World's 100 Best Coffee Shops — live and historical.",
    no_args_is_help=True,
)
scrape_app = typer.Typer(help="Scrape coffee shop data.", no_args_is_help=True)
query_app = typer.Typer(help="Query the local database.", no_args_is_help=True)

app.add_typer(scrape_app, name="scrape")
app.add_typer(query_app, name="query")

_DB_OPTION = typer.Option(
    "coffeedb.sqlite", "--db", help="Path to the SQLite database."
)


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


def _save_shop_snapshot(
    conn: sqlite3.Connection,
    *,
    snapshot_id: int,
    shop: Mapping[str, Any],
    ranking_detail_url: str,
    is_wayback: bool,
    detail_fields: Mapping[str, Any],
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
        database.upsert_shop_detail(
            conn,
            shop_id=shop_id,
            snapshot_id=snapshot_id,
            is_wayback=is_wayback,
            auto_commit=False,
            **detail_fields,
        )


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


@app.command()
def init(db: str = _DB_OPTION) -> None:
    """Create database tables (safe to re-run)."""
    database.init_db(db)
    typer.echo(f"Database initialised: {db}")


# ---------------------------------------------------------------------------
# scrape live
# ---------------------------------------------------------------------------


@scrape_app.command("live")
def scrape_live(
    db: str = _DB_OPTION,
    fresh: bool = typer.Option(
        False,
        "-f",
        "--fresh",
        help="Bypass HTTP cache and fetch fresh responses.",
    ),
) -> None:
    """Scrape the current live site: list page + all 100 detail pages."""
    database.init_db(db)
    conn = database.get_conn(db)

    typer.echo(f"Scraping list: {LIST_URL}")
    use_cache = not fresh
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

    with typer.progressbar(shops, label="Scraping detail pages") as progress:
        for shop in progress:
            slug = shop["slug"]
            detail_url = build_detail_url(slug)
            detail = scraper_module.scrape_detail(detail_url, use_cache=use_cache)
            detail_fields = _build_detail_fields(
                detail,
                fallback_name=shop["name"],
                fallback_country=shop["country"],
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


# ---------------------------------------------------------------------------
# scrape historical
# ---------------------------------------------------------------------------


@scrape_app.command("historical")
def scrape_historical(
    db: str = _DB_OPTION,
    fresh: bool = typer.Option(
        False,
        "-f",
        "--fresh",
        help="Bypass HTTP cache and fetch fresh responses.",
    ),
    delay: float = typer.Option(
        DEFAULT_WAYBACK_DELAY_SECONDS,
        "--delay",
        help="Seconds between Wayback requests.",
    ),
    limit: int = typer.Option(
        DEFAULT_HISTORICAL_LIMIT,
        "--limit",
        help="Max snapshots to process (0 = all).",
    ),
    timestamps: list[str] = typer.Option(
        [],
        "--timestamp",
        help="Explicit Wayback timestamp(s) to process (YYYYMMDDhhmmss). Can be repeated.",
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Print per-snapshot diagnostics (fetch/parse/insert counters).",
    ),
) -> None:
    """Scrape all Wayback Machine snapshots of the list page."""
    database.init_db(db)
    conn = database.get_conn(db)
    use_cache = not fresh

    if timestamps:
        snapshots = [
            {
                "timestamp": ts,
                "snapshot_date": f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}",
            }
            for ts in timestamps
        ]
    else:
        typer.echo("Querying Wayback CDX API...")
        snapshots = wayback.get_snapshots(LIST_URL, use_cache=use_cache)
        if not snapshots:
            typer.echo("No Wayback snapshots found.", err=True)
            raise typer.Exit(code=1)

    if limit > 0:
        snapshots = snapshots[:limit]

    typer.echo(f"Found {len(snapshots)} snapshot(s) to process.")

    with typer.progressbar(snapshots, label="Snapshots") as progress:
        for snap in progress:
            ts = snap["timestamp"]
            snap_date = snap["snapshot_date"]
            if debug:
                typer.echo(f"[historical] ts={ts} date={snap_date} start")

            html = wayback.fetch_archived(
                ts, LIST_URL, delay=delay, use_cache=use_cache
            )
            if html is None:
                if debug:
                    typer.echo(f"[historical] ts={ts} list_fetch=none skip")
                continue
            if debug:
                typer.echo(f"[historical] ts={ts} list_fetch=ok html_len={len(html)}")

            shops = scraper_module.scrape_list(LIST_URL, html=html)
            if not shops:
                if debug:
                    typer.echo(f"[historical] ts={ts} parsed_shops=0 skip")
                continue
            if debug:
                typer.echo(f"[historical] ts={ts} parsed_shops={len(shops)}")

            snapshot_id = database.insert_snapshot(
                conn,
                snapshot_date=snap_date,
                list_page_url=build_wayback_url(ts, LIST_URL),
                wayback_timestamp=ts,
            )
            if debug:
                typer.echo(f"[historical] ts={ts} snapshot_id={snapshot_id}")

            details_missing = 0

            for shop in shops:
                slug = shop["slug"]
                detail_url = build_detail_url(slug)
                archived_detail_url = build_wayback_url(ts, detail_url)

                detail_html = wayback.fetch_archived(
                    ts, detail_url, delay=delay, use_cache=use_cache
                )
                if detail_html is None:
                    details_missing += 1
                    detail_fields = _build_detail_fields(
                        None,
                        fallback_name=shop["name"],
                        fallback_country=shop["country"],
                    )
                    _save_shop_snapshot(
                        conn,
                        snapshot_id=snapshot_id,
                        shop=shop,
                        ranking_detail_url=archived_detail_url,
                        is_wayback=True,
                        detail_fields=detail_fields,
                    )
                    continue

                detail = scraper_module.scrape_detail(
                    detail_url, html=detail_html, use_cache=use_cache
                )
                detail_fields = _build_detail_fields(
                    detail,
                    fallback_name=shop["name"],
                    fallback_country=shop["country"],
                )
                _save_shop_snapshot(
                    conn,
                    snapshot_id=snapshot_id,
                    shop=shop,
                    ranking_detail_url=archived_detail_url,
                    is_wayback=True,
                    detail_fields=detail_fields,
                )

            if debug:
                typer.echo(
                    f"[historical] ts={ts} rankings_saved={len(shops)} detail_missing={details_missing}"
                )

    typer.echo("Done.")


# ---------------------------------------------------------------------------
# query top
# ---------------------------------------------------------------------------


@query_app.command("top")
def query_top(
    db: str = _DB_OPTION,
    snapshot_date: Optional[str] = typer.Option(
        None, "--date", help="YYYY-MM-DD snapshot date (default: latest)."
    ),
    n: int = typer.Option(
        DEFAULT_TOP_RESULTS,
        "--n",
        help="Number of results to show.",
    ),
) -> None:
    """Show the top N ranked coffee shops for a snapshot."""
    conn = database.get_conn(db)

    if snapshot_date:
        row = conn.execute(
            "SELECT id, snapshot_date, wayback_timestamp FROM snapshots WHERE snapshot_date = ? ORDER BY id DESC LIMIT 1",
            (snapshot_date,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT id, snapshot_date, wayback_timestamp FROM snapshots ORDER BY snapshot_date DESC, id DESC LIMIT 1"
        ).fetchone()

    if row is None:
        typer.echo("No snapshots found. Run `coffeedb scrape live` first.", err=True)
        raise typer.Exit(code=1)

    snapshot_id, snap_date = row["id"], row["snapshot_date"]
    source = "wayback" if row["wayback_timestamp"] else "live"
    typer.echo(f"Snapshot: {snap_date} (source={source}, id={snapshot_id})\n")

    rows = database.get_shop_slug_rows_for_snapshot(
        conn, snapshot_id=snapshot_id, limit=n
    )

    if not rows:
        typer.echo("No rankings found for this snapshot.")
        return

    col_w = TOP_COLUMN_WIDTHS
    header = f"{'Rank':<{col_w[0]}}  {'Name':<{col_w[1]}}  {'Country':<{col_w[2]}}  {'Slug':<{col_w[3]}}"
    typer.echo(header)
    typer.echo("-" * len(header))
    for r in rows:
        typer.echo(
            f"{r['rank']:<{col_w[0]}}  {(r['name'] or ''):<{col_w[1]}}  {(r['country'] or ''):<{col_w[2]}}  {(r['slug'] or ''):<{col_w[3]}}"
        )


# ---------------------------------------------------------------------------
# query history
# ---------------------------------------------------------------------------


@query_app.command("history")
def query_history(
    slug: str = typer.Argument(..., help="Shop slug, e.g. onyx-coffee-lab"),
    db: str = _DB_OPTION,
) -> None:
    """Show the ranking history of a coffee shop across all snapshots."""
    conn = database.get_conn(db)

    rows = conn.execute(
        """
        SELECT
            s.snapshot_date,
            CASE WHEN s.wayback_timestamp IS NULL THEN 'live' ELSE 'wayback' END AS source,
            r.rank,
            r.name_on_page,
            r.country_on_page
        FROM rankings r
        JOIN shops sh ON sh.id = r.shop_id
        JOIN snapshots s ON r.snapshot_id = s.id
        WHERE sh.slug = ?
        ORDER BY s.snapshot_date
        """,
        (slug,),
    ).fetchall()

    if not rows:
        typer.echo(f"No ranking history found for slug: {slug}", err=True)
        raise typer.Exit(code=1)

    shop = conn.execute(
        """
        SELECT sd.name
        FROM shops sh
        LEFT JOIN shop_details sd ON sd.shop_id = sh.id
        WHERE sh.slug = ?
        ORDER BY sd.snapshot_id DESC
        LIMIT 1
        """,
        (slug,),
    ).fetchone()
    name = shop["name"] if (shop and shop["name"]) else slug
    typer.echo(f"Ranking history for: {name} ({slug})\n")

    col_w = HISTORY_COLUMN_WIDTHS
    header = f"{'Date':<{col_w[0]}}  {'Source':<{col_w[1]}}  {'Rank':<{col_w[2]}}  {'Name on page':<{col_w[3]}}  {'Country':<{col_w[4]}}"
    typer.echo(header)
    typer.echo("-" * len(header))
    for r in rows:
        typer.echo(
            f"{r['snapshot_date']:<{col_w[0]}}  {r['source']:<{col_w[1]}}  {r['rank']:<{col_w[2]}}  {(r['name_on_page'] or ''):<{col_w[3]}}  {(r['country_on_page'] or ''):<{col_w[4]}}"
        )


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app()
