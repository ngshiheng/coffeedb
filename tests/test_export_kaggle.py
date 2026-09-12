import csv
import sqlite3

from coffeedb import db
from coffeedb.kaggle import export_database


def test_export_database_writes_latest_and_historical_views(tmp_path) -> None:
    db_path = tmp_path / "coffee.db"
    output_dir = tmp_path / "kaggle"

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(db.SCHEMA)
    first_snapshot = db.insert_snapshot(
        conn,
        snapshot_date="2025-01-01",
        list_page_url="https://example.com/2025",
        wayback_timestamp="20250101000000",
    )
    second_snapshot = db.insert_snapshot(
        conn,
        snapshot_date="2026-01-01",
        list_page_url="https://example.com/2026",
    )
    shop_id = db.get_or_create_shop(conn, "shop-a")
    for snapshot_id, rank, name in (
        (first_snapshot, 2, "Shop A Old"),
        (second_snapshot, 1, "Shop A New"),
    ):
        db.insert_ranking(
            conn,
            snapshot_id=snapshot_id,
            shop_id=shop_id,
            rank=rank,
            detail_page_url="https://example.com/shops/shop-a",
            name_on_page=name,
            country_on_page="Japan",
        )
        db.upsert_shop_detail(
            conn,
            shop_id=shop_id,
            snapshot_id=snapshot_id,
            is_wayback=snapshot_id == first_snapshot,
            fields={"name": name, "city": "Tokyo", "image_urls": "[]"},
        )
    conn.commit()
    conn.close()

    counts = export_database(db_path, output_dir)

    assert counts == {
        "snapshots": 2,
        "shops": 1,
        "latest_ranking": 1,
        "ranking_history": 2,
    }

    with (output_dir / "latest_ranking.csv").open(newline="", encoding="utf-8") as file:
        latest = list(csv.DictReader(file))
    with (output_dir / "ranking_history.csv").open(
        newline="", encoding="utf-8"
    ) as file:
        history = list(csv.DictReader(file))

    assert latest[0]["snapshot_date"] == "2026-01-01"
    assert latest[0]["rank"] == "1"
    assert latest[0]["name"] == "Shop A New"
    assert [row["snapshot_date"] for row in history] == ["2025-01-01", "2026-01-01"]
    assert history[0]["is_wayback"] == "1"
    assert history[1]["is_wayback"] == "0"
