from coffeedb import db


def _setup_memory_db():
    conn = db.get_conn(":memory:")
    conn.executescript(db.SCHEMA)
    return conn


def test_insert_snapshot_is_idempotent() -> None:
    conn = _setup_memory_db()

    first = db.insert_snapshot(
        conn,
        snapshot_date="2026-01-01",
        list_page_url="https://example.com/list",
        wayback_timestamp=None,
    )
    second = db.insert_snapshot(
        conn,
        snapshot_date="2026-01-01",
        list_page_url="https://example.com/list",
        wayback_timestamp=None,
    )

    assert first == second


def test_get_or_create_shop_is_idempotent() -> None:
    conn = _setup_memory_db()

    first = db.get_or_create_shop(conn, "shop-a")
    second = db.get_or_create_shop(conn, "shop-a")

    assert first == second


def test_insert_ranking_replace_keeps_single_rank_per_snapshot() -> None:
    conn = _setup_memory_db()
    snapshot_id = db.insert_snapshot(
        conn,
        snapshot_date="2026-01-01",
        list_page_url="https://example.com/list",
        wayback_timestamp=None,
    )
    shop_a = db.get_or_create_shop(conn, "shop-a")
    shop_b = db.get_or_create_shop(conn, "shop-b")

    db.insert_ranking(
        conn,
        snapshot_id=snapshot_id,
        shop_id=shop_a,
        rank=1,
        detail_page_url="https://example.com/locales/shop-a/",
        name_on_page="Shop A",
        country_on_page="Japan",
    )
    db.insert_ranking(
        conn,
        snapshot_id=snapshot_id,
        shop_id=shop_b,
        rank=1,
        detail_page_url="https://example.com/locales/shop-b/",
        name_on_page="Shop B",
        country_on_page="Japan",
    )

    row = conn.execute(
        "SELECT shop_id, detail_page_url FROM rankings WHERE snapshot_id = ? AND rank = ?",
        (snapshot_id, 1),
    ).fetchone()

    assert row is not None
    assert int(row["shop_id"]) == shop_b
    assert row["detail_page_url"] == "https://example.com/locales/shop-b/"


def test_upsert_shop_detail_replaces_existing_row() -> None:
    conn = _setup_memory_db()
    snapshot_id = db.insert_snapshot(
        conn,
        snapshot_date="2026-01-01",
        list_page_url="https://example.com/list",
        wayback_timestamp=None,
    )
    shop_id = db.get_or_create_shop(conn, "shop-a")

    db.upsert_shop_detail(
        conn,
        shop_id=shop_id,
        snapshot_id=snapshot_id,
        is_wayback=False,
        name="Shop A",
        city="Tokyo",
    )
    db.upsert_shop_detail(
        conn,
        shop_id=shop_id,
        snapshot_id=snapshot_id,
        is_wayback=True,
        name="Shop A Updated",
        city="Osaka",
    )

    row = conn.execute(
        "SELECT name, city, is_wayback FROM shop_details WHERE shop_id = ? AND snapshot_id = ?",
        (shop_id, snapshot_id),
    ).fetchone()

    assert row is not None
    assert row["name"] == "Shop A Updated"
    assert row["city"] == "Osaka"
    assert int(row["is_wayback"]) == 1
