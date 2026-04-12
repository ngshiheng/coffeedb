"""SQLite schema and persistence helpers for temporal coffee shop snapshots."""

import sqlite3

FINAL_SCHEMA_TABLES = {"snapshots", "shops", "rankings", "shop_details"}
RANKING_REQUIRED_COLUMNS = {"shop_id", "detail_page_url"}
SNAPSHOT_REQUIRED_COLUMNS = {"list_page_url"}
SHOP_REQUIRED_COLUMNS = {"id", "slug"}
DETAIL_REQUIRED_COLUMNS = {"shop_id", "snapshot_id", "is_wayback"}
LEGACY_TABLES_TO_DROP = (
    "shop_details",
    "rankings",
    "shops",
    "coffee_shops",
    "snapshots",
)

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


def _is_final_schema(conn: sqlite3.Connection) -> bool:
    """Return whether the current database already matches the expected schema."""
    tables = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if not FINAL_SCHEMA_TABLES.issubset(tables):
        return False

    ranking_cols = _table_columns(conn, "rankings")
    snapshot_cols = _table_columns(conn, "snapshots")
    shops_cols = _table_columns(conn, "shops")
    details_cols = _table_columns(conn, "shop_details")

    return (
        RANKING_REQUIRED_COLUMNS.issubset(ranking_cols)
        and SNAPSHOT_REQUIRED_COLUMNS.issubset(snapshot_cols)
        and SHOP_REQUIRED_COLUMNS.issubset(shops_cols)
        and DETAIL_REQUIRED_COLUMNS.issubset(details_cols)
    )


def _reset_to_final_schema(conn: sqlite3.Connection) -> None:
    """Drop old tables so the final schema can be recreated cleanly."""
    drop_statements = "\n".join(
        f"DROP TABLE IF EXISTS {table};" for table in LEGACY_TABLES_TO_DROP
    )
    conn.executescript(
        f"""
        PRAGMA foreign_keys = OFF;
        {drop_statements}
        PRAGMA foreign_keys = ON;
        """
    )


def _commit_if_requested(conn: sqlite3.Connection, auto_commit: bool) -> None:
    if auto_commit:
        conn.commit()


def init_db(db_path: str) -> None:
    with get_conn(db_path) as conn:
        if not _is_final_schema(conn):
            _reset_to_final_schema(conn)
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
    auto_commit: bool = True,
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
    _commit_if_requested(conn, auto_commit)
    return int(row["id"])


def get_or_create_shop(
    conn: sqlite3.Connection, slug: str, auto_commit: bool = True
) -> int:
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
    _commit_if_requested(conn, auto_commit)
    return int(row["id"])


def insert_ranking(
    conn: sqlite3.Connection,
    snapshot_id: int,
    shop_id: int,
    rank: int,
    detail_page_url: str,
    name_on_page: str | None,
    country_on_page: str | None,
    auto_commit: bool = True,
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO rankings
        (snapshot_id, shop_id, rank, detail_page_url, name_on_page, country_on_page)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (snapshot_id, shop_id, rank, detail_page_url, name_on_page, country_on_page),
    )
    _commit_if_requested(conn, auto_commit)


def upsert_shop_detail(
    conn: sqlite3.Connection,
    shop_id: int,
    snapshot_id: int,
    is_wayback: bool,
    auto_commit: bool = True,
    **fields,
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
    _commit_if_requested(conn, auto_commit)


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
