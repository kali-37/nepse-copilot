"""Test the database migration framework."""

from __future__ import annotations

import sqlite3

from nepse_trader.storage.migrations import MIGRATIONS, run_pending


def test_migrations_are_ordered() -> None:
    """Migrations are ordered by version name (lexicographic)."""
    versions = [v for v, _ in MIGRATIONS]
    assert versions == sorted(versions), f"migrations not sorted: {versions}"


def test_migration_versions_are_unique() -> None:
    """No duplicate version names."""
    versions = [v for v, _ in MIGRATIONS]
    assert len(versions) == len(set(versions))


def test_run_pending_idempotent() -> None:
    """Running pending twice applies nothing the second time."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")

    n1 = run_pending(conn)
    assert n1 == len(MIGRATIONS), f"expected {len(MIGRATIONS)} migrations, got {n1}"

    n2 = run_pending(conn)
    assert n2 == 0, "second run should apply 0 migrations"

    # Verify the version table exists with the right entries.
    versions = {row[0] for row in conn.execute("SELECT version FROM schema_version").fetchall()}
    expected = {v for v, _ in MIGRATIONS}
    assert versions == expected

    conn.close()


def test_run_pending_creates_tables() -> None:
    """After running pending, expected tables exist."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA journal_mode=WAL;")

    run_pending(conn)

    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    for tbl in (
        "price_bars",
        "reconciled_prices",
        "signals",
        "paper_trades",
        "ingest_log",
        "schema_version",
        "app_settings",
    ):
        assert tbl in tables, f"missing table {tbl}"

    conn.close()


def test_migration_adds_column() -> None:
    """Simulate adding a column via migration: column exists after."""
    conn = sqlite3.connect(":memory:")
    run_pending(conn)

    # Simulate a column that should be present after migration 0000.
    cols = {
        row[1]
        for row in conn.execute("PRAGMA table_info(reconciled_prices)").fetchall()
    }
    assert "close" in cols
    assert "symbol" in cols
    assert "business_date" in cols

    conn.close()
