"""Export the temporal coffee-shop database for Kaggle publication."""

from __future__ import annotations

import argparse
import csv
import sqlite3
from collections.abc import Iterable, Sequence
from pathlib import Path


SNAPSHOT_FIELDS = (
    "snapshot_date",
    "list_page_url",
    "wayback_timestamp",
    "scraped_at",
)
SHOP_FIELDS = ("slug", "created_at")
RANKING_FIELDS = (
    "snapshot_date",
    "rank",
    "name",
    "slug",
    "city",
    "country",
    "address",
    "website",
    "instagram",
    "description",
    "image_urls",
    "detail_page_url",
    "is_wayback",
)
HISTORY_FIELDS = (
    "snapshot_date",
    "wayback_timestamp",
    "rank",
    "name",
    "slug",
    "city",
    "country",
    "address",
    "website",
    "instagram",
    "description",
    "image_urls",
    "detail_page_url",
    "is_wayback",
)


def _write_csv(
    output_path: Path,
    fieldnames: Sequence[str],
    rows: Iterable[sqlite3.Row],
) -> int:
    """Write SQLite rows to a UTF-8 CSV and return the number of data rows."""
    count = 0
    with output_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(fieldnames)
        for row in rows:
            writer.writerow([row[field] for field in fieldnames])
            count += 1
    return count


def export_snapshots(conn: sqlite3.Connection, output_dir: Path) -> int:
    rows = conn.execute(
        """
        SELECT snapshot_date, list_page_url, wayback_timestamp, scraped_at
        FROM snapshots
        ORDER BY snapshot_date
        """
    )
    return _write_csv(output_dir / "snapshots.csv", SNAPSHOT_FIELDS, rows)


def export_shops(conn: sqlite3.Connection, output_dir: Path) -> int:
    rows = conn.execute(
        """
        SELECT slug, created_at
        FROM shops
        ORDER BY slug
        """
    )
    return _write_csv(output_dir / "shops.csv", SHOP_FIELDS, rows)


def _ranking_query(*, latest_only: bool) -> str:
    latest_filter = "WHERE s.id = (SELECT id FROM latest)" if latest_only else ""
    return f"""
        WITH latest AS (
            SELECT id
            FROM snapshots
            ORDER BY snapshot_date DESC
            LIMIT 1
        )
        SELECT
            s.snapshot_date,
            s.wayback_timestamp,
            r.rank,
            COALESCE(sd.name, r.name_on_page) AS name,
            sh.slug,
            sd.city,
            COALESCE(sd.country, r.country_on_page) AS country,
            sd.address,
            sd.website,
            sd.instagram,
            sd.description,
            sd.image_urls,
            r.detail_page_url,
            COALESCE(sd.is_wayback, CASE WHEN s.wayback_timestamp IS NULL THEN 0 ELSE 1 END) AS is_wayback
        FROM rankings r
        JOIN snapshots s ON s.id = r.snapshot_id
        JOIN shops sh ON sh.id = r.shop_id
        LEFT JOIN shop_details sd
            ON sd.shop_id = r.shop_id AND sd.snapshot_id = r.snapshot_id
        {latest_filter}
        ORDER BY s.snapshot_date, r.rank
    """


def export_latest_ranking(conn: sqlite3.Connection, output_dir: Path) -> int:
    rows = conn.execute(_ranking_query(latest_only=True))
    return _write_csv(output_dir / "latest_ranking.csv", RANKING_FIELDS, rows)


def export_ranking_history(conn: sqlite3.Connection, output_dir: Path) -> int:
    rows = conn.execute(_ranking_query(latest_only=False))
    return _write_csv(output_dir / "ranking_history.csv", HISTORY_FIELDS, rows)


def export_database(db_path: Path, output_dir: Path) -> dict[str, int]:
    """Export all public CSV views from one SQLite database."""
    if not db_path.is_file():
        raise FileNotFoundError(f"Database not found: {db_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return {
            "snapshots": export_snapshots(conn, output_dir),
            "shops": export_shops(conn, output_dir),
            "latest_ranking": export_latest_ranking(conn, output_dir),
            "ranking_history": export_ranking_history(conn, output_dir),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("data/coffee.db"))
    parser.add_argument("--output-dir", type=Path, default=Path("kaggle"))
    args = parser.parse_args()

    counts = export_database(args.db, args.output_dir)
    for name, count in counts.items():
        print(f"Exported {count} {name} row(s) to {args.output_dir}")


if __name__ == "__main__":
    main()
