"""Ordered DB migrations for schema evolution.

Each migration is a named function that applies DDL changes.  The framework
tracks which have been applied in a ``schema_version`` table and runs pending
migrations in order, exactly once.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime

log = logging.getLogger("nepse_trader.storage.migrations")

_Migration = Callable[["sqlite3.Connection"], None]  # noqa: F821


def _create_version_table(conn) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version ("
        "  version TEXT PRIMARY KEY,"
        "  applied_at TEXT NOT NULL"
        ")"
    )


def _applied_versions(conn) -> set[str]:
    return {row[0] for row in conn.execute("SELECT version FROM schema_version").fetchall()}


def _mark_applied(conn, version: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO schema_version (version, applied_at) VALUES (?, ?)",
        (version, datetime.now(UTC).isoformat()),
    )


# ---------------------------------------------------------------------------
# Migrations  —  each is a (name, callable) pair ordered by name.
# ``0000_initial`` is the original schema shipped in v0.1.0.
# ---------------------------------------------------------------------------


def _m0000_initial(conn) -> None:
    """Initial schema as defined in storage/db.py at v0.1.0."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS price_bars (
            symbol TEXT NOT NULL,
            business_date TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL, previous_close REAL,
            volume INTEGER, turnover REAL, trades INTEGER,
            source TEXT NOT NULL,
            fetched_at TEXT,
            PRIMARY KEY (symbol, business_date, source)
        );
        CREATE INDEX IF NOT EXISTS idx_price_symbol_date ON price_bars(symbol, business_date);

        CREATE TABLE IF NOT EXISTS index_values (
            name TEXT NOT NULL,
            business_date TEXT NOT NULL,
            value REAL NOT NULL,
            change REAL, change_percent REAL,
            source TEXT NOT NULL,
            fetched_at TEXT,
            PRIMARY KEY (name, business_date, source)
        );

        CREATE TABLE IF NOT EXISTS floorsheet (
            contract_id TEXT,
            symbol TEXT NOT NULL,
            business_date TEXT NOT NULL,
            buyer_broker TEXT, seller_broker TEXT,
            quantity INTEGER NOT NULL, rate REAL NOT NULL, amount REAL,
            source TEXT NOT NULL,
            PRIMARY KEY (contract_id, symbol, business_date, source)
        );

        CREATE TABLE IF NOT EXISTS reconciled_prices (
            symbol TEXT NOT NULL,
            business_date TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL, previous_close REAL,
            volume INTEGER, turnover REAL,
            sources_agreeing TEXT, sources_present TEXT, disputed_fields TEXT,
            confidence REAL,
            PRIMARY KEY (symbol, business_date)
        );

        CREATE TABLE IF NOT EXISTS signals (
            symbol TEXT NOT NULL,
            business_date TEXT NOT NULL,
            strategy TEXT NOT NULL,
            action TEXT NOT NULL,
            strength REAL,
            reason TEXT,
            price REAL,
            PRIMARY KEY (symbol, business_date, strategy)
        );

        CREATE TABLE IF NOT EXISTS paper_trades (
            trade_id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            business_date TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            price REAL NOT NULL,
            gross_amount REAL,
            broker_commission REAL,
            sebon_fee REAL,
            dp_charge REAL,
            cgt REAL,
            net_amount REAL,
            strategy TEXT
        );

        CREATE TABLE IF NOT EXISTS ingest_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            endpoint TEXT,
            business_date TEXT,
            rows INTEGER,
            status TEXT,
            message TEXT,
            ran_at TEXT
        );
    """)




def _m0001_corporate_actions(conn) -> None:
    """Add corporate_actions table for price-adjustment events."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS corporate_actions (
            symbol TEXT NOT NULL,
            ex_date TEXT NOT NULL,
            action_type TEXT NOT NULL,
            ratio_numerator INTEGER NOT NULL,
            ratio_denominator INTEGER NOT NULL DEFAULT 1,
            factor REAL NOT NULL,
            source TEXT NOT NULL,
            notes TEXT DEFAULT '',
            PRIMARY KEY (symbol, ex_date, action_type)
        )
    """)


# Ordered list of (version_name, migration_fn).  New migrations append at the end.
MIGRATIONS: list[tuple[str, _Migration]] = [
    ("0000_initial", _m0000_initial),
    ("0001_corporate_actions", _m0001_corporate_actions),
]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_pending(conn) -> int:
    """Apply any pending migrations.  Returns the number applied."""
    _create_version_table(conn)
    applied = _applied_versions(conn)
    count = 0
    for version, fn in MIGRATIONS:
        if version in applied:
            continue
        log.info("applying migration %s …", version)
        fn(conn)
        _mark_applied(conn, version)
        count += 1
        log.info("migration %s done", version)
    return count
