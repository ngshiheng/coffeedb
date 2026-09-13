import sqlite3
from pathlib import Path

import yaml

from coffeedb import db


METADATA_PATH = Path(__file__).parents[1] / "data" / "metadata.yml"


def _queries() -> dict[str, dict]:
    metadata = yaml.safe_load(METADATA_PATH.read_text(encoding="utf-8"))
    return metadata["databases"]["coffee"]["queries"]


def _fixture_database() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(db.SCHEMA)

    shop_ids = {
        number: db.get_or_create_shop(conn, f"shop-{number:03d}")
        for number in range(1, 102)
    }

    def add_snapshot(snapshot_date: str, shop_order: list[int]) -> None:
        snapshot_id = db.insert_snapshot(
            conn,
            snapshot_date=snapshot_date,
            list_page_url=f"https://example.com/{snapshot_date}",
        )
        for rank, shop_number in enumerate(shop_order, start=1):
            db.insert_ranking(
                conn,
                snapshot_id=snapshot_id,
                shop_id=shop_ids[shop_number],
                rank=rank,
                detail_page_url=f"https://example.com/shops/shop-{shop_number:03d}",
                name_on_page=f"Shop {shop_number:03d}",
                country_on_page="Testland",
            )

    baseline = list(range(1, 101))
    changed = [101, *range(1, 100)]
    later_change = [1, 101, *range(2, 100)]

    add_snapshot("2025-01-01", baseline)
    add_snapshot("2025-02-01", baseline)
    add_snapshot("2026-01-01", baseline)
    add_snapshot("2026-02-01", changed)
    add_snapshot("2026-03-01", changed[:-1])
    add_snapshot("2026-04-01", later_change)
    conn.commit()
    return conn


def test_canned_queries_load_and_execute_with_blank_parameters() -> None:
    queries = _queries()
    conn = _fixture_database()

    assert set(queries) == {
        "current_top_100",
        "find_current_shop",
        "shop_history",
        "available_captures",
        "top_100_on_date",
        "changes_since_previous_check",
        "annual_editions",
        "annual_rank_changes",
        "annual_membership_changes",
        "country_summary",
    }

    for definition in queries.values():
        parameters = {name: None for name in definition.get("params", [])}
        conn.execute(definition["sql"], parameters).fetchall()

    conn.close()


def test_canned_queries_use_exact_observations_and_inferred_annual_editions() -> None:
    queries = _queries()
    conn = _fixture_database()

    current_rows = conn.execute(
        queries["current_top_100"]["sql"],
        {"country": None, "city": None},
    ).fetchall()
    assert len(current_rows) == 100
    assert current_rows[0][0] == "2026-04-01"

    history_rows = conn.execute(
        queries["shop_history"]["sql"],
        {"search": "shop-001"},
    ).fetchall()
    assert [(row[0], row[5], row[9]) for row in history_rows] == [
        ("2025-01-01", 1, "first observation"),
        ("2026-01-01", 1, "annual observation"),
        ("2026-02-01", 2, "dropped"),
        ("2026-04-01", 1, "climbed"),
    ]
    assert conn.execute(
        queries["shop_history"]["sql"],
        {"search": None},
    ).fetchall() == []

    exact_rows = conn.execute(
        queries["top_100_on_date"]["sql"],
        {"snapshot_date": "2025-02-01", "country": None, "city": None},
    ).fetchall()
    assert len(exact_rows) == 100
    assert {row[0] for row in exact_rows} == {"2025-02-01"}

    missing_rows = conn.execute(
        queries["top_100_on_date"]["sql"],
        {"snapshot_date": "2025-12-31", "country": None, "city": None},
    ).fetchall()
    assert missing_rows == []

    capture_rows = conn.execute(queries["available_captures"]["sql"]).fetchall()
    capture_by_date = {row[0]: row for row in capture_rows}
    assert len(capture_rows) == 6
    assert capture_by_date["2026-03-01"][7] == "partial ranking"
    assert capture_by_date["2025-01-01"][8] == "2025"
    assert capture_by_date["2026-02-01"][8] == "2026"
    assert capture_by_date["2026-04-01"][8] is None

    annual_rows = conn.execute(queries["annual_editions"]["sql"]).fetchall()
    assert [(row[0], row[1]) for row in annual_rows] == [
        ("2026", "2026-02-01"),
        ("2025", "2025-01-01"),
    ]

    conn.close()


def test_comparison_queries_skip_partial_observations() -> None:
    queries = _queries()
    conn = _fixture_database()

    recent_changes = conn.execute(
        queries["changes_since_previous_check"]["sql"],
        {"change_type": None, "search": None, "country": None},
    ).fetchall()
    assert recent_changes
    assert {row[1] for row in recent_changes} == {
        "2026-01-01",
        "2026-02-01",
    }
    assert {row[2] for row in recent_changes} == {
        "2026-02-01",
        "2026-04-01",
    }
    assert "annual observation" not in {row[0] for row in recent_changes}

    shop_changes = conn.execute(
        queries["changes_since_previous_check"]["sql"],
        {"change_type": None, "search": "shop-001", "country": None},
    ).fetchall()
    assert {row[0] for row in shop_changes} == {
        "rank change",
        "annual observation",
    }

    annual_changes = conn.execute(
        queries["annual_rank_changes"]["sql"],
        {
            "from_year": None,
            "to_year": None,
            "direction": None,
            "search": None,
            "country": None,
        },
    ).fetchall()
    assert annual_changes
    assert {row[0] for row in annual_changes} == {"2025"}
    assert {row[2] for row in annual_changes} == {"2026"}

    membership_changes = conn.execute(
        queries["annual_membership_changes"]["sql"],
        {
            "from_year": None,
            "to_year": None,
            "change_type": None,
            "search": None,
            "country": None,
        },
    ).fetchall()
    assert {row[0] for row in membership_changes} == {
        "observed entry",
        "observed exit",
    }

    conn.close()
