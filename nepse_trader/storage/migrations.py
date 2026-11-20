"""Ordered DB migrations for schema evolution.

Each migration is a named function that applies DDL changes.  The framework
tracks which have been applied in a ``schema_version`` table and runs pending
migrations in order, exactly once.
"""

from __future__ import annotations

import hashlib
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

    **No credential has a column here, by design.** Not the DP/client id, username, not the
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


def _m0007_journal(conn) -> None:
    """The prediction journal: every call logged, scored, reviewed, then retired.

    The advisor is only worth trusting if its past calls can be checked, so each
    prediction is written down *before* the outcome is known — expected price,
    stop, target, quantity, expected net PnL, and the confidence attached to it.
    Later, ``advisor/outcomes.py`` fills in what actually happened. The gap
    between ``expected_net_pnl`` and ``realized_net_pnl`` is the only honest
    measure of whether any of this works.

    **Five-step lifecycle**, tracked by ``status``:

    1. ``open`` — logged at run time, outcome unknown.
    2. ``scored`` — resolved against real bars; ``outcome``/``hit`` set.
    3. ``reviewed`` — an AI pass wrote ``review`` explaining the miss or hit.
    4. ``retired`` — the lesson has been distilled into ``prediction_lessons``
       and indexed for RAG, so the verbose row is no longer needed. It is kept
       with ``retired_at`` set rather than deleted: hit-rates are computed from
       these rows and deleting them would silently reset every calibration.
    5. Retired rows are excluded from the review queue but still counted.

    ``hit`` is deliberately narrow — 1 only when ``outcome`` is ``TARGET_HIT``.
    A call that merely drifted up without reaching its target is ``EXPIRED_UP``:
    a partial, not a win. Counting partials as hits would inflate every
    Wilson bound the confidence scale rests on, which is precisely the failure
    mode this table exists to prevent.

    ``UNRESOLVED`` and ``NO_DATA`` are recorded but excluded from calibration —
    "we don't know" must never be laundered into evidence either way.

    ``prediction_lessons`` holds the distilled, durable takeaway. ``superseded_at``
    rather than deletion, so a lesson that later proved wrong leaves a trace.

    ``calibration`` is a materialised roll-up keyed by (scope, subject, horizon).
    It is derived data — safe to rebuild from ``predictions`` at any time — and
    exists so a report does not have to aggregate the whole journal per symbol.
    """
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prediction_id TEXT NOT NULL UNIQUE,
            run_id INTEGER REFERENCES advice_runs(id) ON DELETE SET NULL,
            kind TEXT NOT NULL DEFAULT 'plan',
            symbol TEXT NOT NULL,
            made_on TEXT NOT NULL,
            horizon TEXT NOT NULL DEFAULT '',
            horizon_days INTEGER NOT NULL DEFAULT 0,
            deadline TEXT NOT NULL,
            action TEXT NOT NULL DEFAULT '',
            reference_price REAL,
            entry_low REAL,
            entry_high REAL,
            stop REAL,
            target_1 REAL,
            target_2 REAL,
            quantity INTEGER NOT NULL DEFAULT 0,
            expected_net_pnl REAL,
            confidence REAL NOT NULL DEFAULT 0.0,
            confidence_band TEXT NOT NULL DEFAULT '',
            confidence_basis TEXT NOT NULL DEFAULT '',
            rationale TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            outcome TEXT,
            resolved_on TEXT,
            realized_exit_price REAL,
            realized_net_pnl REAL,
            mfe REAL,
            mae REAL,
            hit INTEGER,
            bars_seen INTEGER NOT NULL DEFAULT 0,
            scored_at TEXT,
            review TEXT,
            lesson TEXT,
            lesson_id TEXT,
            reviewed_at TEXT,
            retired_at TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_predictions_symbol ON predictions(symbol);
        CREATE INDEX IF NOT EXISTS idx_predictions_status ON predictions(status);
        CREATE INDEX IF NOT EXISTS idx_predictions_made_on ON predictions(made_on);
        CREATE INDEX IF NOT EXISTS idx_predictions_kind_symbol ON predictions(kind, symbol);

        CREATE TABLE IF NOT EXISTS prediction_lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id TEXT NOT NULL UNIQUE,
            scope TEXT NOT NULL DEFAULT 'global',
            subject TEXT NOT NULL DEFAULT '',
            horizon TEXT NOT NULL DEFAULT '',
            lesson TEXT NOT NULL,
            sample_size INTEGER NOT NULL DEFAULT 0,
            hits INTEGER NOT NULL DEFAULT 0,
            hit_rate REAL,
            source TEXT NOT NULL DEFAULT 'deterministic',
            created_at TEXT NOT NULL,
            superseded_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_prediction_lessons_scope
            ON prediction_lessons(scope, subject);

        CREATE TABLE IF NOT EXISTS calibration (
            scope TEXT NOT NULL,
            subject TEXT NOT NULL DEFAULT '',
            horizon TEXT NOT NULL DEFAULT '',
            hits INTEGER NOT NULL DEFAULT 0,
            resolved INTEGER NOT NULL DEFAULT 0,
            hit_rate REAL,
            wilson_lower REAL,
            mean_expected_pnl REAL,
            mean_realized_pnl REAL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (scope, subject, horizon)
        );
    """)


def _m0008_doses_auction(conn) -> None:
    """Nested dose prescriptions, and advice on auction bids.

    **Doses.** One ``dose_runs`` row per prescription, four ``doses`` rows under
    it — day, week, month, year. They are *nested over the same capital*, so
    ``allocation_pct`` across the four must sum to at most 1.0 and every plan
    card belongs to exactly one dose. Storing them as separate rows with a
    UNIQUE (dose_run_id, horizon) makes double-counting a constraint violation
    rather than a silently inflated headline earnings figure — which would be
    the most dangerous possible bug in this whole system.

    ``reading`` holds the horoscope-shaped prose for that horizon. It is prose
    only; every number next to it comes from the deterministic engine.

    **Auction advice.** NEPSE auctions sell defaulted/unclaimed shares to the
    highest bidders, and the trap is bidding above what the position can
    actually clear after commission, SEBON fee, DP charge and CGT.
    ``breakeven_price`` is the price the share must reach just to return the
    bid net of the full cost stack; ``walk_away_price`` is the bid above which
    the expected edge disappears. ``verdict`` is 'bid' or 'skip'.

    This table records *advice*. No bid is ever placed by this software —
    consistent with the read-only rule that governs the MeroShare integration.
    """
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS dose_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER REFERENCES advice_runs(id) ON DELETE CASCADE,
            run_date TEXT NOT NULL,
            mode TEXT NOT NULL DEFAULT 'normal',
            capital REAL NOT NULL DEFAULT 0.0,
            deployed_capital REAL NOT NULL DEFAULT 0.0,
            expected_net_pnl REAL,
            confidence REAL NOT NULL DEFAULT 0.0,
            confidence_band TEXT NOT NULL DEFAULT '',
            banner TEXT,
            generated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_dose_runs_date ON dose_runs(run_date);

        CREATE TABLE IF NOT EXISTS doses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dose_run_id INTEGER NOT NULL REFERENCES dose_runs(id) ON DELETE CASCADE,
            horizon TEXT NOT NULL,
            horizon_days INTEGER NOT NULL DEFAULT 0,
            allocation_pct REAL NOT NULL DEFAULT 0.0,
            allocated_capital REAL NOT NULL DEFAULT 0.0,
            deployed_capital REAL NOT NULL DEFAULT 0.0,
            symbols TEXT NOT NULL DEFAULT '',
            card_count INTEGER NOT NULL DEFAULT 0,
            expected_gross_pnl REAL,
            expected_net_pnl REAL,
            expected_return_pct REAL,
            expected_costs REAL,
            expected_tax REAL,
            confidence REAL NOT NULL DEFAULT 0.0,
            confidence_band TEXT NOT NULL DEFAULT '',
            confidence_basis TEXT NOT NULL DEFAULT '',
            earliest_sell_date TEXT,
            reading TEXT,
            UNIQUE (dose_run_id, horizon)
        );
        CREATE INDEX IF NOT EXISTS idx_doses_run ON doses(dose_run_id);

        CREATE TABLE IF NOT EXISTS auction_advice (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            advice_id TEXT NOT NULL UNIQUE,
            symbol TEXT NOT NULL,
            auction_date TEXT NOT NULL,
            units INTEGER NOT NULL DEFAULT 0,
            min_bid_price REAL,
            market_price REAL,
            recommended_bid REAL,
            max_sensible_bid REAL,
            walk_away_price REAL,
            breakeven_price REAL,
            quantity INTEGER NOT NULL DEFAULT 0,
            outlay REAL,
            expected_exit_price REAL,
            expected_gross_pnl REAL,
            expected_net_pnl REAL,
            expected_return_pct REAL,
            horizon_days INTEGER NOT NULL DEFAULT 0,
            earliest_sell_date TEXT,
            confidence REAL NOT NULL DEFAULT 0.0,
            confidence_band TEXT NOT NULL DEFAULT '',
            confidence_basis TEXT NOT NULL DEFAULT '',
            verdict TEXT NOT NULL DEFAULT '',
            rationale TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_auction_advice_symbol
            ON auction_advice(symbol, auction_date);
    """)


def _m0009_advisor_confidence(conn) -> None:
    """Add the per-card confidence fields without rewriting old advice rows."""
    columns = {
        str(row[1]) for row in conn.execute("PRAGMA table_info(advice_cards)").fetchall()
    }
    for name, ddl in (
        ("confidence", "ALTER TABLE advice_cards ADD COLUMN confidence REAL NOT NULL DEFAULT 0.45"),
        ("confidence_band", "ALTER TABLE advice_cards ADD COLUMN confidence_band TEXT NOT NULL DEFAULT 'COIN_FLIP'"),
        ("confidence_basis", "ALTER TABLE advice_cards ADD COLUMN confidence_basis TEXT NOT NULL DEFAULT ''"),
        ("prediction_id", "ALTER TABLE advice_cards ADD COLUMN prediction_id TEXT"),
    ):
        if name not in columns:
            conn.execute(ddl)


def _m0010_meroshare_privacy(conn) -> None:
    """Remove the legacy DP/client-id column from the local mirror.

    SQLite cannot drop a column on every version we support, so rebuild the
    table from explicit, non-credential columns. The DDL is transactional: a
    failure leaves the old table untouched.
    """
    columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(ms_holdings)")}
    # Older development schemas used a few spellings for the account's
    # client/DP identifier.  Rebuild whenever *any* of those columns remain,
    # not only the first ``dp_id`` variant; otherwise a legacy ``client_id``
    # column could survive indefinitely in a user's local database.
    sensitive_columns = {
        "dp_id",
        "client_id",
        "client_code",
        "clientid",
        "clientcode",
        "dpid",
    }
    if not {name.casefold() for name in columns} & sensitive_columns:
        return
    # A database may already have the post-0012 hashed shape (for example a
    # caller invoking this legacy helper directly during an upgrade test).  In
    # that case preserve the safe columns while dropping only the newly found
    # legacy identifiers; there is no raw ``demat_number`` to copy.
    if "demat_number" not in columns and "demat_hash" in columns:
        conn.execute("DROP TABLE IF EXISTS ms_holdings_private")
        conn.execute("""
            CREATE TABLE ms_holdings_private (
                symbol TEXT NOT NULL,
                demat_hash TEXT NOT NULL DEFAULT '',
                demat_last4 TEXT NOT NULL DEFAULT '',
                isin TEXT,
                script_desc TEXT,
                current_balance INTEGER NOT NULL DEFAULT 0,
                previous_balance INTEGER,
                pledged_balance INTEGER,
                wacc REAL,
                previous_closing_price REAL,
                last_transaction_date TEXT,
                source TEXT NOT NULL,
                synced_at TEXT NOT NULL,
                PRIMARY KEY (symbol, demat_hash)
            )
        """)
        conn.execute("""
            INSERT INTO ms_holdings_private (
                symbol, demat_hash, demat_last4, isin, script_desc,
                current_balance, previous_balance, pledged_balance, wacc,
                previous_closing_price, last_transaction_date, source, synced_at
            )
            SELECT symbol, demat_hash, demat_last4, isin, script_desc,
                   current_balance, previous_balance, pledged_balance, wacc,
                   previous_closing_price, last_transaction_date, source, synced_at
            FROM ms_holdings
        """)
        conn.execute("DROP TABLE ms_holdings")
        conn.execute("ALTER TABLE ms_holdings_private RENAME TO ms_holdings")
        conn.execute("CREATE INDEX idx_ms_holdings_symbol ON ms_holdings(symbol)")
        return
    conn.execute("""
        CREATE TABLE ms_holdings_private (
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
            source TEXT NOT NULL,
            synced_at TEXT NOT NULL,
            PRIMARY KEY (symbol, demat_number)
        )
    """)
    conn.execute("""
        INSERT INTO ms_holdings_private (
            symbol, demat_number, isin, script_desc, current_balance,
            previous_balance, pledged_balance, wacc, previous_closing_price,
            last_transaction_date, source, synced_at
        )
        SELECT
            symbol, demat_number, isin, script_desc, current_balance,
            previous_balance, pledged_balance, wacc, previous_closing_price,
            last_transaction_date, source, synced_at
        FROM ms_holdings
    """)
    conn.execute("DROP TABLE ms_holdings")
    conn.execute("ALTER TABLE ms_holdings_private RENAME TO ms_holdings")
    conn.execute("CREATE INDEX idx_ms_holdings_symbol ON ms_holdings(symbol)")


def _m0011_app_settings(conn) -> None:
    """Persist small, runtime-editable application settings.

    Values are deliberately generic JSON strings so adding a toggle does not
    require another schema migration.  Secrets never belong in this table;
    MeroShare credentials remain environment/keyring-only.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def _m0012_meroshare_demat_privacy(conn) -> None:
    """Replace raw demat identifiers with a stable hash and masked suffix.

    ``0006`` originally stored ``demat_number`` to keep multiple demats under
    one login distinct.  That identifier is account data and must not survive
    in a database dump.  This rebuild preserves the same cardinality and
    upsert semantics using a domain-separated SHA-256 key plus the final four
    characters for display.  Empty demats remain a single empty bucket.
    """

    holding_columns = {
        str(row[1]) for row in conn.execute("PRAGMA table_info(ms_holdings)")
    }
    transaction_columns = {
        str(row[1]) for row in conn.execute("PRAGMA table_info(ms_transactions)")
    }
    if "demat_number" not in holding_columns and "demat_number" not in transaction_columns:
        return

    namespace = b"nepse-trader/meroshare/demat/v1:"

    def safe_parts(value: object) -> tuple[str, str]:
        raw = str(value or "").strip()
        if not raw:
            return "", ""
        return hashlib.sha256(namespace + raw.encode("utf-8")).hexdigest(), raw[-4:]

    conn.execute("DROP TABLE IF EXISTS ms_holdings_private")
    conn.execute("""
        CREATE TABLE ms_holdings_private (
            symbol TEXT NOT NULL,
            demat_hash TEXT NOT NULL DEFAULT '',
            demat_last4 TEXT NOT NULL DEFAULT '',
            isin TEXT,
            script_desc TEXT,
            current_balance INTEGER NOT NULL DEFAULT 0,
            previous_balance INTEGER,
            pledged_balance INTEGER,
            wacc REAL,
            previous_closing_price REAL,
            last_transaction_date TEXT,
            source TEXT NOT NULL,
            synced_at TEXT NOT NULL,
            PRIMARY KEY (symbol, demat_hash)
        )
    """)
    for row in conn.execute("SELECT * FROM ms_holdings").fetchall():
        raw = row["demat_number"] if hasattr(row, "keys") else row[1]
        digest, last4 = safe_parts(raw)
        conn.execute(
            """INSERT INTO ms_holdings_private (
                   symbol, demat_hash, demat_last4, isin, script_desc,
                   current_balance, previous_balance, pledged_balance, wacc,
                   previous_closing_price, last_transaction_date, source, synced_at
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(symbol, demat_hash) DO UPDATE SET
                   demat_last4=excluded.demat_last4, isin=excluded.isin,
                   script_desc=excluded.script_desc,
                   current_balance=excluded.current_balance,
                   previous_balance=excluded.previous_balance,
                   pledged_balance=excluded.pledged_balance, wacc=excluded.wacc,
                   previous_closing_price=excluded.previous_closing_price,
                   last_transaction_date=excluded.last_transaction_date,
                   source=excluded.source, synced_at=excluded.synced_at""",
            (
                row["symbol"] if hasattr(row, "keys") else row[0],
                digest,
                last4,
                row["isin"] if hasattr(row, "keys") else row[2],
                row["script_desc"] if hasattr(row, "keys") else row[3],
                row["current_balance"] if hasattr(row, "keys") else row[4],
                row["previous_balance"] if hasattr(row, "keys") else row[5],
                row["pledged_balance"] if hasattr(row, "keys") else row[6],
                row["wacc"] if hasattr(row, "keys") else row[7],
                row["previous_closing_price"] if hasattr(row, "keys") else row[8],
                row["last_transaction_date"] if hasattr(row, "keys") else row[9],
                row["source"] if hasattr(row, "keys") else row[10],
                row["synced_at"] if hasattr(row, "keys") else row[11],
            ),
        )
    conn.execute("DROP TABLE ms_holdings")
    conn.execute("ALTER TABLE ms_holdings_private RENAME TO ms_holdings")
    conn.execute("CREATE INDEX idx_ms_holdings_symbol ON ms_holdings(symbol)")

    conn.execute("DROP TABLE IF EXISTS ms_transactions_private")
    conn.execute("""
        CREATE TABLE ms_transactions_private (
            txn_id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            demat_hash TEXT NOT NULL DEFAULT '',
            demat_last4 TEXT NOT NULL DEFAULT '',
            transaction_date TEXT NOT NULL,
            transaction_type TEXT NOT NULL DEFAULT '',
            description TEXT,
            quantity INTEGER NOT NULL DEFAULT 0,
            price REAL,
            balance_after INTEGER,
            reference TEXT,
            source TEXT NOT NULL,
            synced_at TEXT NOT NULL
        )
    """)
    for row in conn.execute("SELECT * FROM ms_transactions").fetchall():
        raw = row["demat_number"] if hasattr(row, "keys") else row[2]
        digest, last4 = safe_parts(raw)
        conn.execute(
            """INSERT INTO ms_transactions_private (
                   txn_id, symbol, demat_hash, demat_last4, transaction_date,
                   transaction_type, description, quantity, price, balance_after,
                   reference, source, synced_at
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                row["txn_id"] if hasattr(row, "keys") else row[0],
                row["symbol"] if hasattr(row, "keys") else row[1],
                digest,
                last4,
                row["transaction_date"] if hasattr(row, "keys") else row[3],
                row["transaction_type"] if hasattr(row, "keys") else row[4],
                row["description"] if hasattr(row, "keys") else row[5],
                row["quantity"] if hasattr(row, "keys") else row[6],
                row["price"] if hasattr(row, "keys") else row[7],
                row["balance_after"] if hasattr(row, "keys") else row[8],
                row["reference"] if hasattr(row, "keys") else row[9],
                row["source"] if hasattr(row, "keys") else row[10],
                row["synced_at"] if hasattr(row, "keys") else row[11],
            ),
        )
    conn.execute("DROP TABLE ms_transactions")
    conn.execute("ALTER TABLE ms_transactions_private RENAME TO ms_transactions")
    conn.execute(
        "CREATE INDEX idx_ms_transactions_symbol_date "
        "ON ms_transactions(symbol, transaction_date)"
    )


def _m0013_health_snapshots(conn) -> None:
    """Keep a history of health reports so degradation is visible over time.

    A single report answers "is it healthy now"; a series answers "when did it
    stop being healthy", which is the question you actually have at 22:00 when
    the advice looks wrong. ``report`` is the whole JSON document, so adding a
    check does not need another migration, and the flat status columns exist so
    a trend query does not have to parse JSON.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS health_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            captured_at TEXT NOT NULL,
            status TEXT NOT NULL,
            ok INTEGER NOT NULL DEFAULT 0,
            warn INTEGER NOT NULL DEFAULT 0,
            fail INTEGER NOT NULL DEFAULT 0,
            off INTEGER NOT NULL DEFAULT 0,
            report TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_health_snapshots_captured "
        "ON health_snapshots(captured_at DESC)"
    )


def _m0014_advice_run_context(conn) -> None:
    """Store the run context that surrounds the cards, not just the cards.

    ``advice_runs`` kept the headline fields but dropped the sell queue, the
    exclusions, the breadth snapshot and the thesis, so a reloaded run was a
    strictly smaller document than the one that was generated — the exits a
    user was told to make simply vanished. Each is a JSON blob for the same
    reason ``health_snapshots.report`` is: their shape belongs to the advisor,
    and widening it should not need another migration.
    """
    columns = {
        str(row[1]) for row in conn.execute("PRAGMA table_info(advice_runs)").fetchall()
    }
    for name, ddl in (
        ("sell_queue", "ALTER TABLE advice_runs ADD COLUMN sell_queue TEXT"),
        ("do_not_touch", "ALTER TABLE advice_runs ADD COLUMN do_not_touch TEXT"),
        ("breadth", "ALTER TABLE advice_runs ADD COLUMN breadth TEXT"),
        ("thesis", "ALTER TABLE advice_runs ADD COLUMN thesis TEXT"),
    ):
        if name not in columns:
            conn.execute(ddl)


def _m0015_fundamentals(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS fundamentals (
        symbol TEXT NOT NULL, business_date TEXT NOT NULL, payload TEXT NOT NULL,
        PRIMARY KEY(symbol, business_date))""")


def _m0016_ingest_state(conn) -> None:
    conn.executescript("""CREATE TABLE IF NOT EXISTS ingest_state (
        source TEXT PRIMARY KEY, failures INTEGER NOT NULL DEFAULT 0,
        cooldown_until REAL NOT NULL DEFAULT 0);
        CREATE INDEX IF NOT EXISTS idx_price_date ON price_bars(business_date,source);
        CREATE INDEX IF NOT EXISTS idx_reconciled_date ON reconciled_prices(business_date);
        CREATE INDEX IF NOT EXISTS idx_ingest_source_date ON ingest_log(source,business_date,endpoint);
    """)


def _m0017_run_metrics(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS run_metrics (
        run_id TEXT PRIMARY KEY, kind TEXT NOT NULL, business_date TEXT,
        recorded_at TEXT NOT NULL, payload TEXT NOT NULL)""")


def _m0018_decision_board(conn) -> None:
    conn.executescript("""CREATE TABLE IF NOT EXISTS tracked_positions (
        symbol TEXT PRIMARY KEY, quantity INTEGER NOT NULL, cost_basis TEXT,
        bought_on TEXT, stop REAL, target REAL, horizon_days INTEGER NOT NULL DEFAULT 22,
        updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS position_records (
        id TEXT PRIMARY KEY, symbol TEXT NOT NULL, side TEXT NOT NULL,
        quantity INTEGER NOT NULL, price TEXT NOT NULL, business_date TEXT NOT NULL,
        recorded_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS decision_runs (
        id TEXT PRIMARY KEY, generated_at TEXT NOT NULL, payload TEXT NOT NULL);
    """)


def _m0019_position_entry(conn) -> None:
    conn.execute("ALTER TABLE tracked_positions ADD COLUMN entry_price REAL")


def _m0020_position_plan_review(conn) -> None:
    conn.execute("ALTER TABLE tracked_positions ADD COLUMN plan_reviewed_on TEXT")


# Ordered list of (version_name, migration_fn).  New migrations append at the end.
MIGRATIONS: list[tuple[str, _Migration]] = [
    ("0000_initial", _m0000_initial),
    ("0001_corporate_actions", _m0001_corporate_actions),
    ("0002_adjusted_close", _m0002_adjusted_close),
    ("0003_rag_documents", _m0003_rag_documents),
    ("0004_ai", _m0004_ai),
    ("0005_advice", _m0005_advice),
    ("0006_meroshare", _m0006_meroshare),
    ("0007_journal", _m0007_journal),
    ("0008_doses_auction", _m0008_doses_auction),
    ("0009_advisor_confidence", _m0009_advisor_confidence),
    ("0010_meroshare_privacy", _m0010_meroshare_privacy),
    ("0011_app_settings", _m0011_app_settings),
    ("0012_meroshare_demat_privacy", _m0012_meroshare_demat_privacy),
    ("0013_health_snapshots", _m0013_health_snapshots),
    ("0014_advice_run_context", _m0014_advice_run_context),
    ("0015_fundamentals", _m0015_fundamentals),
    ("0016_ingest_state", _m0016_ingest_state),
    ("0017_run_metrics", _m0017_run_metrics),
    ("0018_decision_board", _m0018_decision_board),
    ("0019_position_entry", _m0019_position_entry),
    ("0020_position_plan_review", _m0020_position_plan_review),
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
