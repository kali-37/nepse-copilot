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


def _m0002_adjusted_close(conn) -> None:
    """Add adjusted_close column to reconciled_prices."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(reconciled_prices)")}
    if "adjusted_close" not in existing:
        conn.execute("ALTER TABLE reconciled_prices ADD COLUMN adjusted_close REAL")


def has_fts5(conn) -> bool:
    """Probe whether this SQLite build has the FTS5 extension compiled in.

    FTS5 ships with every mainstream CPython/SQLite build, but it is a compile
    time option — so we check rather than assume. Callers fall back to LIKE
    based search when it is missing (see ``nepse_trader.rag.index``).
    """
    try:
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts5_probe USING fts5(x)")
        conn.execute("DROP TABLE IF EXISTS _fts5_probe")
        return True
    except Exception:  # noqa: BLE001 - any failure means "not available"
        return False


def _m0003_rag_documents(conn) -> None:
    """Document corpus for retrieval, plus an FTS5 index over it when available.

    ``documents`` is the source of truth and works on any SQLite build.
    ``documents_fts`` is an external-content FTS5 index (it stores no copy of the
    text, just the terms) kept in sync by triggers.
    """
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS documents (
            doc_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            symbol TEXT,
            business_date TEXT,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            url TEXT,
            source TEXT,
            fetched_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_documents_kind ON documents(kind);
        CREATE INDEX IF NOT EXISTS idx_documents_symbol_date
            ON documents(symbol, business_date);
    """)

    if not has_fts5(conn):
        log.warning("SQLite build lacks FTS5; RAG search will use the LIKE fallback")
        return

    conn.executescript("""
        CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
            title, body, symbol, kind,
            content='documents', content_rowid='rowid',
            tokenize='porter unicode61'
        );

        CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
            INSERT INTO documents_fts(rowid, title, body, symbol, kind)
            VALUES (new.rowid, new.title, new.body, new.symbol, new.kind);
        END;
        CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
            INSERT INTO documents_fts(documents_fts, rowid, title, body, symbol, kind)
            VALUES ('delete', old.rowid, old.title, old.body, old.symbol, old.kind);
        END;
        CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
            INSERT INTO documents_fts(documents_fts, rowid, title, body, symbol, kind)
            VALUES ('delete', old.rowid, old.title, old.body, old.symbol, old.kind);
            INSERT INTO documents_fts(rowid, title, body, symbol, kind)
            VALUES (new.rowid, new.title, new.body, new.symbol, new.kind);
        END;
    """)


def _m0004_ai(conn) -> None:
    """LLM response cache and token-spend ledger.

    ``ai_cache`` is what makes a re-run free: the key is a hash of the prompt
    content, so identical evidence never pays twice. Provider and model are
    stored as metadata rather than part of the key — a cached answer stays usable
    when the chain falls through to a different provider tomorrow.

    ``ai_budget_ledger`` is the audit trail behind the hard caps: one row per
    call, with the ISO week alongside the day so the weekly deep-pass limit is a
    plain query rather than date arithmetic. Cache hits are recorded too, flagged
    ``cached=1``, so they show up in the accounting without spending budget.
    """
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS ai_cache (
            cache_key TEXT PRIMARY KEY,
            task TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            response TEXT NOT NULL,
            prompt_tokens INTEGER NOT NULL DEFAULT 0,
            completion_tokens INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ai_cache_created ON ai_cache(created_at);

        CREATE TABLE IF NOT EXISTS ai_budget_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            day TEXT NOT NULL,
            iso_week TEXT NOT NULL,
            task TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            prompt_tokens INTEGER NOT NULL DEFAULT 0,
            completion_tokens INTEGER NOT NULL DEFAULT 0,
            cached INTEGER NOT NULL DEFAULT 0,
            deep INTEGER NOT NULL DEFAULT 0,
            ok INTEGER NOT NULL DEFAULT 1,
            error TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_ai_ledger_day ON ai_budget_ledger(day);
        CREATE INDEX IF NOT EXISTS idx_ai_ledger_week ON ai_budget_ledger(iso_week);
    """)


def _m0005_advice(conn) -> None:
    """Persisted advisor runs and the plan cards they produced.

    Kept so a call can be scored against what actually happened afterwards —
    the frontend's "past call vs outcome" view is a join of ``advice_cards``
    against ``price_bars`` on the dates recorded here. Without persistence a
    prescription is unfalsifiable, which is the fastest way to stop trusting it.

    ``mode`` records whether the LLM narrative layer was involved and ``banner``
    carries the degradation notice when AI mode was asked for but fell back to
    deterministic-only. Every number in ``advice_cards`` comes from the
    deterministic engine; nothing an LLM emitted is stored as a number here.

    ``earliest_sell_date`` is the T+2 settlement date from the trading calendar,
    stored explicitly because it is not derivable from ``run_date`` without the
    holiday list that was in force at the time.
    """
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS advice_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TEXT NOT NULL,
            mode TEXT NOT NULL,
            horizon TEXT NOT NULL,
            online INTEGER NOT NULL DEFAULT 1,
            regime TEXT,
            sector_of_the_day TEXT,
            banner TEXT,
            equity REAL,
            generated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_advice_runs_date ON advice_runs(run_date);

        CREATE TABLE IF NOT EXISTS advice_cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL REFERENCES advice_runs(id) ON DELETE CASCADE,
            symbol TEXT NOT NULL,
            action TEXT NOT NULL,
            reference_price REAL,
            entry_low REAL,
            entry_high REAL,
            stop REAL,
            target_1 REAL,
            target_2 REAL,
            quantity INTEGER NOT NULL DEFAULT 0,
            horizon_days INTEGER,
            earliest_sell_date TEXT,
            gross_pnl REAL,
            net_pnl REAL,
            entry_cost REAL,
            exit_cost REAL,
            capital_gains_tax REAL,
            conviction INTEGER,
            rationale TEXT,
            note TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_advice_cards_run ON advice_cards(run_id);
        CREATE INDEX IF NOT EXISTS idx_advice_cards_symbol ON advice_cards(symbol);
    """)


def _m0006_meroshare(conn) -> None:
    """Read-only mirror of the user's own MeroShare/CDSC account.

    **No credential has a column here, by design.** Not the username, not the
    password, not a session token, not a keyring reference. Credentials live in
    env / .env / the OS keyring and are resolved per run — see
    ``nepse_trader/meroshare/credentials.py``. Anything in these three tables is
    account *content*, which the user already sees in the portal.

    ``ms_holdings`` is keyed by (symbol, demat_number) so a re-sync upserts
    rather than duplicates, and so a second demat under the same login stays
    separate. ``current_balance`` is a share count (INTEGER, comparable to
    ``Position.quantity``); ``wacc`` is the weighted average cost per share the
    portal reports, in NPR (REAL, like every other money column in this schema).

    ``ms_transactions`` uses a deterministic ``txn_id`` — a hash of the natural
    key — because the portal exposes no stable row id. ``quantity`` is signed:
    credits positive, debits negative.

    ``ms_sync_log`` records one row per *attempt*, success or failure, so a
    stale holdings table always has a visible reason next to it.
    """
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS ms_holdings (
            symbol TEXT NOT NULL,
            demat_number TEXT NOT NULL DEFAULT '',
            isin TEXT,
            script_desc TEXT,
            current_balance INTEGER NOT NULL DEFAULT 0,
            previous_balance INTEGER,
            pledged_balance INTEGER,
            wacc REAL,
            previous_closing_price REAL,
            last_transaction_date TEXT,
            dp_id TEXT,
            source TEXT NOT NULL,
            synced_at TEXT NOT NULL,
            PRIMARY KEY (symbol, demat_number)
        );
        CREATE INDEX IF NOT EXISTS idx_ms_holdings_symbol ON ms_holdings(symbol);

        CREATE TABLE IF NOT EXISTS ms_transactions (
            txn_id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            demat_number TEXT NOT NULL DEFAULT '',
            transaction_date TEXT NOT NULL,
            transaction_type TEXT NOT NULL DEFAULT '',
            description TEXT,
            quantity INTEGER NOT NULL DEFAULT 0,
            price REAL,
            balance_after INTEGER,
            reference TEXT,
            source TEXT NOT NULL,
            synced_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ms_transactions_symbol_date
            ON ms_transactions(symbol, transaction_date);

        CREATE TABLE IF NOT EXISTS ms_sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ran_at TEXT NOT NULL,
            method TEXT NOT NULL,
            status TEXT NOT NULL,
            holdings INTEGER NOT NULL DEFAULT 0,
            transactions INTEGER NOT NULL DEFAULT 0,
            error TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_ms_sync_log_ran ON ms_sync_log(ran_at);
    """)


# Ordered list of (version_name, migration_fn).  New migrations append at the end.
MIGRATIONS: list[tuple[str, _Migration]] = [
    ("0000_initial", _m0000_initial),
    ("0001_corporate_actions", _m0001_corporate_actions),
    ("0002_adjusted_close", _m0002_adjusted_close),
    ("0003_rag_documents", _m0003_rag_documents),
    ("0004_ai", _m0004_ai),
    ("0005_advice", _m0005_advice),
    ("0006_meroshare", _m0006_meroshare),
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
