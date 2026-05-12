"""SQLite schema and persistence helpers for temporal coffee shop snapshots."""

import sqlite3
from typing import TypedDict


class ShopDetailFields(TypedDict, total=False):
    name: str | None
    city: str | None
    country: str | None
    address: str | None
    website: str | None
    instagram: str | None
    description: str | None
    image_urls: str | None


SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date DATE NOT NULL UNIQUE,
    list_page_url TEXT NOT NULL,
    wayback_timestamp TEXT,
    scraped_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS shops (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS rankings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
    shop_id INTEGER NOT NULL REFERENCES shops(id) ON DELETE RESTRICT,
    rank INTEGER NOT NULL CHECK(rank > 0),
    detail_page_url TEXT NOT NULL,
    name_on_page TEXT,
    country_on_page TEXT,
    UNIQUE(snapshot_id, rank),
    UNIQUE(snapshot_id, shop_id)
);

CREATE TABLE IF NOT EXISTS shop_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shop_id INTEGER NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    snapshot_id INTEGER NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
    name TEXT,
    city TEXT,
    country TEXT,
    address TEXT,
    website TEXT,
    instagram TEXT,
    description TEXT,
    image_urls TEXT,
    is_wayback BOOLEAN DEFAULT 0,
    UNIQUE(shop_id, snapshot_id)
);

CREATE INDEX IF NOT EXISTS idx_rankings_snapshot ON rankings(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_rankings_shop ON rankings(shop_id);
CREATE INDEX IF NOT EXISTS idx_shop_details_shop ON shop_details(shop_id);
CREATE INDEX IF NOT EXISTS idx_shop_details_snapshot ON shop_details(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_date ON snapshots(snapshot_date);
"""


def get_conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row["name"] for row in rows}


def init_db(db_path: str) -> None:
    with get_conn(db_path) as conn:
        conn.executescript(SCHEMA)
        detail_cols = _table_columns(conn, "shop_details")
        if "image_urls" not in detail_cols:
            conn.execute("ALTER TABLE shop_details ADD COLUMN image_urls TEXT")
            conn.commit()


def insert_snapshot(
    conn: sqlite3.Connection,
    snapshot_date: str,
    list_page_url: str,
    wayback_timestamp: str | None = None,
) -> int:
    conn.execute(
        """
        INSERT OR IGNORE INTO snapshots (snapshot_date, list_page_url, wayback_timestamp)
        VALUES (?, ?, ?)
        """,
        (snapshot_date, list_page_url, wayback_timestamp),
    )
    cur = conn.execute(
        "SELECT id FROM snapshots WHERE snapshot_date = ?",
        (snapshot_date,),
    )
    row = cur.fetchone()
    if row is None:
        raise RuntimeError(f"Failed to create or fetch snapshot for {snapshot_date}")
    return int(row["id"])


def get_or_create_shop(conn: sqlite3.Connection, slug: str) -> int:
    conn.execute(
        "INSERT OR IGNORE INTO shops (slug) VALUES (?)",
        (slug,),
    )
    cur = conn.execute(
        "SELECT id FROM shops WHERE slug = ?",
        (slug,),
    )
    row = cur.fetchone()
    if row is None:
        raise RuntimeError(f"Failed to create or fetch shop for slug={slug}")
    return int(row["id"])


def insert_ranking(
    conn: sqlite3.Connection,
    snapshot_id: int,
    shop_id: int,
    rank: int,
    detail_page_url: str,
    name_on_page: str | None,
    country_on_page: str | None,
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO rankings
        (snapshot_id, shop_id, rank, detail_page_url, name_on_page, country_on_page)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (snapshot_id, shop_id, rank, detail_page_url, name_on_page, country_on_page),
    )


def upsert_shop_detail(
    conn: sqlite3.Connection,
    shop_id: int,
    snapshot_id: int,
    is_wayback: bool,
    fields: ShopDetailFields,
) -> None:
    data = {
        "shop_id": shop_id,
        "snapshot_id": snapshot_id,
        "is_wayback": 1 if is_wayback else 0,
        **fields,
    }
    columns = ", ".join(data.keys())
    placeholders = ", ".join("?" * len(data))
    conn.execute(
        f"INSERT OR REPLACE INTO shop_details ({columns}) VALUES ({placeholders})",
        list(data.values()),
    )


def get_shop_slug_rows_for_snapshot(
    conn: sqlite3.Connection, snapshot_id: int, limit: int
) -> list[sqlite3.Row]:
    cur = conn.execute(
        """
        SELECT r.rank, r.name_on_page AS name, r.country_on_page AS country, s.slug
        FROM rankings r
        JOIN shops s ON s.id = r.shop_id
        WHERE r.snapshot_id = ?
        ORDER BY r.rank
        LIMIT ?
        """,
        (snapshot_id, limit),
    )
    return list(cur.fetchall())
