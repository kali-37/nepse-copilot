"""SQLite persistence for price bars, indices, floorsheet, signals and trades.

Schema favours idempotent daily ingestion: a price bar is unique per
(symbol, business_date, source) so re-running a day's pull upserts rather than
duplicates. Reconciled prices live in their own table keyed by (symbol, date).
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterable
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

from nepse_trader.models import (
    CorporateAction,
    CorporateActionType,
    IndexValue,
    OrderSide,
    PaperTrade,
    PriceBar,
    ReconciledPrice,
    Signal,
    SourceName,
)
from nepse_trader.storage.migrations import run_pending


def _d(value: date | str | None) -> str | None:
    if value is None:
        return None
    return value.isoformat() if isinstance(value, date) else str(value)


def _dt(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    return value.isoformat() if isinstance(value, datetime) else str(value)


class Storage:
    """One database, one connection *per thread*.

    A single ``sqlite3.Connection`` cannot be shared across threads even with
    ``check_same_thread=False``: concurrent callers re-enter the same cached
    prepared statement, so a ``SELECT`` can observe another thread's
    ``SQLITE_DONE`` and return no rows for a row that exists.  The web API runs
    every sync endpoint in a threadpool, which made that a source of phantom
    "missing table" and silently-empty results.  Handing each thread its own
    connection removes the shared statement cache and lets WAL serve reads in
    parallel instead of serialising them behind one lock.
    """

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._conns: list[sqlite3.Connection] = []
        self._conns_lock = threading.Lock()
        run_pending(self._conn)
        self._conn.commit()
        self._symbols_cache: list[str] | None = None

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA cache_size=-64000;")
        conn.execute("PRAGMA temp_store=MEMORY;")
        conn.execute("PRAGMA foreign_keys=ON;")
        # WAL allows one writer at a time; wait instead of raising SQLITE_BUSY.
        conn.execute("PRAGMA busy_timeout=10000;")
        return conn

    @property
    def _conn(self) -> sqlite3.Connection:
        """This thread's connection, opened on first use."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = self._connect()
            self._local.conn = conn
            with self._conns_lock:
                self._conns.append(conn)
        return conn

    def close(self) -> None:
        self._symbols_cache = None
        with self._conns_lock:
            conns, self._conns = self._conns, []
        self._local = threading.local()
        for conn in conns:
            conn.close()

    def __enter__(self) -> Storage:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @contextmanager
    def _tx(self):
        try:
            yield self._conn
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    # ---- writes ---------------------------------------------------------
    def upsert_price_bars(self, bars: Iterable[PriceBar]) -> int:
        rows = [
            (
                b.symbol,
                _d(b.business_date),
                b.open,
                b.high,
                b.low,
                b.close,
                b.previous_close,
                b.volume,
                b.turnover,
                b.trades,
                b.source.value,
                _dt(b.fetched_at),
            )
            for b in bars
        ]
        if not rows:
            return 0
        with self._tx() as c:
            c.executemany(
                """INSERT INTO price_bars
                   (symbol,business_date,open,high,low,close,previous_close,
                    volume,turnover,trades,source,fetched_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(symbol,business_date,source) DO UPDATE SET
                     open=excluded.open, high=excluded.high, low=excluded.low,
                     close=excluded.close, previous_close=excluded.previous_close,
                     volume=excluded.volume, turnover=excluded.turnover,
                     trades=excluded.trades, fetched_at=excluded.fetched_at""",
                rows,
            )
        self._invalidate_symbols()
        return len(rows)

    def upsert_index_values(self, values: Iterable[IndexValue]) -> int:
        rows = [
            (
                v.name,
                _d(v.business_date),
                v.value,
                v.change,
                v.change_percent,
                v.source.value,
                _dt(v.fetched_at),
            )
            for v in values
        ]
        if not rows:
            return 0
        with self._tx() as c:
            c.executemany(
                """INSERT INTO index_values
                   (name,business_date,value,change,change_percent,source,fetched_at)
                   VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT(name,business_date,source) DO UPDATE SET
                     value=excluded.value, change=excluded.change,
                     change_percent=excluded.change_percent,
                     fetched_at=excluded.fetched_at""",
                rows,
            )
        return len(rows)

    @staticmethod
    def _bump_market_revision(conn) -> None:
        conn.execute("""INSERT INTO app_settings(key,value,updated_at) VALUES('market_revision','1',?)
            ON CONFLICT(key) DO UPDATE SET value=CAST(app_settings.value AS INTEGER)+1,
            updated_at=excluded.updated_at""", (datetime.now().isoformat(),))

    def upsert_reconciled(self, prices: Iterable[ReconciledPrice]) -> int:
        rows = [
            (
                p.symbol,
                _d(p.business_date),
                p.open,
                p.high,
                p.low,
                p.close,
                p.previous_close,
                p.volume,
                p.turnover,
                ",".join(s.value for s in p.sources_agreeing),
                ",".join(s.value for s in p.sources_present),
                ",".join(p.disputed_fields),
                p.confidence,
                p.adjusted_close,
            )
            for p in prices
        ]
        if not rows:
            return 0
        with self._tx() as c:
            c.executemany(
                """INSERT INTO reconciled_prices
                   (symbol,business_date,open,high,low,close,previous_close,
                    volume,turnover,sources_agreeing,sources_present,
                    disputed_fields,confidence,adjusted_close)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(symbol,business_date) DO UPDATE SET
                     open=excluded.open, high=excluded.high, low=excluded.low,
                     close=excluded.close, previous_close=excluded.previous_close,
                     volume=excluded.volume, turnover=excluded.turnover,
                     sources_agreeing=excluded.sources_agreeing,
                     sources_present=excluded.sources_present,
                     disputed_fields=excluded.disputed_fields,
                     confidence=excluded.confidence,
                     adjusted_close=excluded.adjusted_close""",
                rows,
            )
            self._bump_market_revision(c)
        return len(rows)

    def upsert_signals(self, signals: Iterable[Signal]) -> int:
        rows = [
            (
                s.symbol,
                _d(s.business_date),
                s.strategy,
                s.action.value,
                s.strength,
                s.reason,
                s.price,
            )
            for s in signals
        ]
        if not rows:
            return 0
        with self._tx() as c:
            c.executemany(
                """INSERT INTO signals
                   (symbol,business_date,strategy,action,strength,reason,price)
                   VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT(symbol,business_date,strategy) DO UPDATE SET
                     action=excluded.action, strength=excluded.strength,
                     reason=excluded.reason, price=excluded.price""",
                rows,
            )
        return len(rows)

    def insert_paper_trade(self, t: PaperTrade) -> None:
        with self._tx() as c:
            c.execute(
                """INSERT OR REPLACE INTO paper_trades
                   (trade_id,symbol,side,business_date,quantity,price,gross_amount,
                    broker_commission,sebon_fee,dp_charge,cgt,net_amount,strategy)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    t.trade_id,
                    t.symbol,
                    t.side.value,
                    _d(t.business_date),
                    t.quantity,
                    str(t.price),
                    str(t.gross_amount),
                    str(t.broker_commission),
                    str(t.sebon_fee),
                    str(t.dp_charge),
                    str(t.cgt),
                    str(t.net_amount),
                    t.strategy,
                ),
            )

    def log_ingest(
        self,
        source: str,
        endpoint: str,
        business_date: date | None,
        rows: int,
        status: str,
        message: str = "",
    ) -> None:
        with self._tx() as c:
            c.execute(
                """INSERT INTO ingest_log
                   (source,endpoint,business_date,rows,status,message,ran_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    source,
                    endpoint,
                    _d(business_date),
                    rows,
                    status,
                    message,
                    datetime.now().isoformat(),
                ),
            )

    def batch_log_ingest(
        self,
        entries: list[tuple[str, str, date | None, int, str, str]],
    ) -> None:
        now = datetime.now().isoformat()
        rows = [(s, e, _d(bd), r, st, msg, now) for s, e, bd, r, st, msg in entries]
        with self._tx() as c:
            c.executemany(
                """INSERT INTO ingest_log
                   (source,endpoint,business_date,rows,status,message,ran_at)
                   VALUES (?,?,?,?,?,?,?)""",
                rows,
            )

    def record_run_metrics(self, kind: str, business_date: date | None, payload: dict) -> str:
        import json
        import uuid

        run_id = uuid.uuid4().hex
        with self._tx() as conn:
            conn.execute("INSERT INTO run_metrics(run_id,kind,business_date,recorded_at,payload) VALUES(?,?,?,?,?)",
                (run_id, kind, _d(business_date), datetime.now().isoformat(), json.dumps(payload, default=str)))
        return run_id

    def source_cooldown(self, source: str) -> float:
        row = self._conn.execute("SELECT cooldown_until FROM ingest_state WHERE source=?", (source,)).fetchone()
        return row[0] if row else 0.0

    def record_source_result(self, source: str, success: bool, threshold: int, cooldown: int) -> None:
        import time

        with self._tx() as conn:
            row = conn.execute("SELECT failures,cooldown_until FROM ingest_state WHERE source=?", (source,)).fetchone()
            failures = 0 if success else (row[0] if row else 0) + 1
            until = time.time() + cooldown if failures >= threshold else 0.0
            conn.execute("""INSERT INTO ingest_state(source,failures,cooldown_until) VALUES(?,?,?)
                ON CONFLICT(source) DO UPDATE SET failures=excluded.failures,cooldown_until=excluded.cooldown_until""",
                (source, failures, until))

    def source_date_ingested(self, source: str, business_date: date) -> bool:
        row = self._conn.execute("""SELECT rows FROM ingest_log WHERE source=? AND business_date=?
            AND endpoint='prices' AND status='ok' AND rows>0 ORDER BY id DESC LIMIT 1""", (source, _d(business_date))).fetchone()
        if not row:
            return False
        count = self._conn.execute("SELECT COUNT(*) FROM price_bars WHERE source=? AND business_date=?", (source, _d(business_date))).fetchone()[0]
        return count >= row[0]

    def recent_source_counts(self, source: str) -> list[int]:
        return [row[0] for row in self._conn.execute("""SELECT rows FROM ingest_log
            WHERE source=? AND endpoint='prices' AND status='ok' AND rows>0 ORDER BY id DESC LIMIT 5""", (source,))]

    # ---- reads ----------------------------------------------------------
    def price_history(self, symbol: str, source: SourceName | None = None) -> list[PriceBar]:
        symbol = symbol.strip().upper()
        if source is not None:
            cur = self._conn.execute(
                "SELECT * FROM price_bars WHERE symbol=? AND source=? ORDER BY business_date",
                (symbol, source.value),
            )
        else:
            cur = self._conn.execute(
                "SELECT * FROM price_bars WHERE symbol=? ORDER BY business_date",
                (symbol,),
            )
        return [self._row_to_bar(r) for r in cur.fetchall()]

    def reconciled_history(
        self, symbol: str, *, as_of: date | None = None, limit: int | None = None
    ) -> list[ReconciledPrice]:
        symbol = symbol.strip().upper()
        query = "SELECT * FROM reconciled_prices WHERE symbol=?"
        params: list[str | int] = [symbol]
        if as_of is not None:
            query += " AND business_date<=?"
            params.append(as_of.isoformat())
        if limit is None:
            rows = self._conn.execute(query + " ORDER BY business_date", params).fetchall()
        else:
            rows = self._conn.execute(
                query + " ORDER BY business_date DESC LIMIT ?", [*params, limit]
            ).fetchall()
            rows.reverse()
        out = []
        for r in rows:
            out.append(
                ReconciledPrice(
                    symbol=r["symbol"],
                    business_date=date.fromisoformat(r["business_date"]),
                    open=r["open"],
                    high=r["high"],
                    low=r["low"],
                    close=r["close"],
                    previous_close=r["previous_close"],
                    volume=r["volume"],
                    turnover=r["turnover"],
                    sources_agreeing=[
                        SourceName(s) for s in (r["sources_agreeing"] or "").split(",") if s
                    ],
                    sources_present=[
                        SourceName(s) for s in (r["sources_present"] or "").split(",") if s
                    ],
                    disputed_fields=[f for f in (r["disputed_fields"] or "").split(",") if f],
                    confidence=r["confidence"] or 0.0,
                    adjusted_close=r["adjusted_close"],
                )
            )
        return out

    def symbols(self) -> list[str]:
        if self._symbols_cache is None:
            cur = self._conn.execute("SELECT DISTINCT symbol FROM price_bars ORDER BY symbol")
            self._symbols_cache = [r["symbol"] for r in cur.fetchall()]
        return self._symbols_cache

    def _invalidate_symbols(self) -> None:
        self._symbols_cache = None

    def reconciled_history_for_date(self, business_date: date) -> list[ReconciledPrice]:
        """All reconciled consensus rows for a single business date."""
        cur = self._conn.execute(
            "SELECT * FROM reconciled_prices WHERE business_date=? ORDER BY symbol",
            (_d(business_date),),
        )
        out: list[ReconciledPrice] = []
        for r in cur.fetchall():
            out.append(
                ReconciledPrice(
                    symbol=r["symbol"],
                    business_date=date.fromisoformat(r["business_date"]),
                    open=r["open"],
                    high=r["high"],
                    low=r["low"],
                    close=r["close"],
                    previous_close=r["previous_close"],
                    volume=r["volume"],
                    turnover=r["turnover"],
                    sources_agreeing=[
                        SourceName(s) for s in (r["sources_agreeing"] or "").split(",") if s
                    ],
                    sources_present=[
                        SourceName(s) for s in (r["sources_present"] or "").split(",") if s
                    ],
                    disputed_fields=[f for f in (r["disputed_fields"] or "").split(",") if f],
                    confidence=r["confidence"] or 0.0,
                    adjusted_close=r["adjusted_close"],
                )
            )
        return out

    def bars_for_date(self, business_date: date) -> list[PriceBar]:
        cur = self._conn.execute(
            "SELECT * FROM price_bars WHERE business_date=? ORDER BY symbol, source",
            (_d(business_date),),
        )
        return [self._row_to_bar(r) for r in cur.fetchall()]

    def paper_trades(self) -> list[PaperTrade]:
        """All recorded paper trades in execution order (for portfolio replay)."""
        from decimal import Decimal as _D

        cur = self._conn.execute("SELECT * FROM paper_trades ORDER BY rowid")
        out: list[PaperTrade] = []
        for r in cur.fetchall():
            out.append(
                PaperTrade(
                    trade_id=r["trade_id"],
                    symbol=r["symbol"],
                    side=OrderSide(r["side"]),
                    business_date=date.fromisoformat(r["business_date"]),
                    quantity=r["quantity"],
                    price=_D(str(r["price"])),
                    gross_amount=_D(str(r["gross_amount"])),
                    broker_commission=_D(str(r["broker_commission"])),
                    sebon_fee=_D(str(r["sebon_fee"])),
                    dp_charge=_D(str(r["dp_charge"])),
                    cgt=_D(str(r["cgt"])),
                    net_amount=_D(str(r["net_amount"])),
                    strategy=r["strategy"],
                )
            )
        return out

    def upsert_corporate_action(self, ca: CorporateAction) -> None:
        with self._tx() as c:
            c.execute(
                """INSERT OR REPLACE INTO corporate_actions
                   (symbol,ex_date,action_type,ratio_numerator,ratio_denominator,factor,source,notes)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    ca.symbol,
                    _d(ca.ex_date),
                    ca.action_type.value,
                    ca.ratio_numerator,
                    ca.ratio_denominator,
                    float(ca.factor),
                    ca.source.value,
                    ca.notes,
                ),
            )
            self._bump_market_revision(c)

    def corporate_actions(self, symbol: str | None = None) -> list[CorporateAction]:
        query = "SELECT * FROM corporate_actions"
        params: tuple = ()
        if symbol:
            query += " WHERE symbol=?"
            params = (symbol.upper(),)
        query += " ORDER BY ex_date"
        cur = self._conn.execute(query, params)
        out: list[CorporateAction] = []
        from decimal import Decimal as _D
        for r in cur.fetchall():
            out.append(
                CorporateAction(
                    symbol=r["symbol"],
                    ex_date=date.fromisoformat(r["ex_date"]),
                    action_type=CorporateActionType(r["action_type"]),
                    ratio_numerator=r["ratio_numerator"],
                    ratio_denominator=r["ratio_denominator"],
                    factor=_D(str(r["factor"])),
                    source=SourceName(r["source"]),
                    notes=r["notes"] or "",
                )
            )
        return out

    def upsert_fundamental(self, data, business_date: date | None = None) -> None:
        """Store a dated snapshot rather than rewriting historical valuation."""
        from datetime import UTC

        observed = business_date or (data.fetched_at.date() if data.fetched_at else datetime.now(UTC).date())
        with self._tx() as conn:
            conn.execute("""INSERT INTO fundamentals(symbol,business_date,payload) VALUES(?,?,?)
                ON CONFLICT(symbol,business_date) DO UPDATE SET payload=excluded.payload""",
                (data.symbol.strip().upper(), observed.isoformat(), data.model_dump_json()))

            self._bump_market_revision(conn)
    def fundamentals(self, as_of: date | None = None) -> dict:
        """Latest available snapshot per name, bounded by an optional date."""
        from nepse_trader.models import FundamentalData

        rows = self._conn.execute("""SELECT f.symbol, f.payload FROM fundamentals f
            JOIN (SELECT symbol, MAX(business_date) AS business_date FROM fundamentals
                  WHERE business_date<=? GROUP BY symbol) latest
            ON f.symbol=latest.symbol AND f.business_date=latest.business_date""",
            ((as_of or date.max).isoformat(),)).fetchall()
        return {row["symbol"]: FundamentalData.model_validate_json(row["payload"]) for row in rows}

    def upsert_floorsheet(self, entries) -> int:
        """Upsert matched contracts; anonymous rows get a stable content ID."""
        import hashlib

        rows = []
        for entry in entries:
            identity = entry.contract_id or hashlib.sha256(entry.model_dump_json().encode()).hexdigest()
            rows.append((identity, entry.symbol, _d(entry.business_date), entry.buyer_broker,
                         entry.seller_broker, entry.quantity, entry.rate, entry.amount, entry.source.value))
        with self._tx() as conn:
            conn.executemany("""INSERT INTO floorsheet
                (contract_id,symbol,business_date,buyer_broker,seller_broker,quantity,rate,amount,source)
                VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(contract_id,symbol,business_date,source)
                DO UPDATE SET buyer_broker=excluded.buyer_broker,seller_broker=excluded.seller_broker,
                quantity=excluded.quantity,rate=excluded.rate,amount=excluded.amount""", rows)
        return len(rows)

    def floorsheet_entries(self, business_date: date, symbol: str | None = None) -> list:
        from nepse_trader.models import FloorsheetEntry

        rows = self._conn.execute("""SELECT * FROM floorsheet WHERE business_date=?
            AND (? IS NULL OR symbol=?) ORDER BY symbol,contract_id,source""",
            (_d(business_date), symbol, symbol)).fetchall()
        return [FloorsheetEntry(**dict(row)) for row in rows]

    def latest_reconciled_date(self) -> date | None:
        cur = self._conn.execute("SELECT MAX(business_date) AS d FROM reconciled_prices")
        row = cur.fetchone()
        return date.fromisoformat(row["d"]) if row and row["d"] else None

    def latest_price_date(self) -> date | None:
        """Newest ingested trading date, or ``None`` on an empty database.

        The right default wherever a date is optional: the last board NEPSE
        published is rarely ``date.today()`` — weekends, holidays and a session
        that has not closed yet all make "today" an empty date.
        """
        cur = self._conn.execute("SELECT MAX(business_date) AS d FROM price_bars")
        row = cur.fetchone()
        return date.fromisoformat(row["d"]) if row and row["d"] else None

    def all_price_bars(self) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM price_bars ORDER BY symbol, business_date"
        ).fetchall()

    def all_reconciled(self) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM reconciled_prices ORDER BY symbol, business_date"
        ).fetchall()

    def all_signals(self) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM signals ORDER BY symbol, business_date"
        ).fetchall()

    def all_index_values(self) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM index_values ORDER BY business_date"
        ).fetchall()

    def all_ingest_logs(self) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM ingest_log ORDER BY ran_at"
        ).fetchall()

    def all_corporate_actions(self) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM corporate_actions ORDER BY ex_date"
        ).fetchall()

    def all_paper_trades(self) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM paper_trades ORDER BY business_date"
        ).fetchall()

    def db_stats(self) -> dict:
        """Aggregate statistics about the database contents."""
        out: dict = {}

        cur = self._conn.execute("SELECT COUNT(DISTINCT symbol) AS n FROM price_bars")
        out["symbols_with_data"] = cur.fetchone()["n"]

        cur = self._conn.execute("SELECT COUNT(*) AS n FROM price_bars")
        out["price_bar_rows"] = cur.fetchone()["n"]

        cur = self._conn.execute("SELECT COUNT(*) AS n FROM reconciled_prices")
        out["reconciled_rows"] = cur.fetchone()["n"]
        out["history_ready_symbols"] = self._conn.execute("SELECT COUNT(*) FROM (SELECT symbol FROM reconciled_prices GROUP BY symbol HAVING COUNT(*)>=60)").fetchone()[0]
        out["trading_days"] = self._conn.execute("SELECT COUNT(DISTINCT business_date) FROM reconciled_prices").fetchone()[0]

        cur = self._conn.execute("SELECT MIN(business_date) AS earliest, MAX(business_date) AS latest FROM price_bars")
        row = cur.fetchone()
        out["price_date_earliest"] = row["earliest"]
        out["price_date_latest"] = row["latest"]

        cur = self._conn.execute("SELECT MIN(business_date) AS earliest, MAX(business_date) AS latest FROM reconciled_prices")
        row = cur.fetchone()
        out["reconciled_date_earliest"] = row["earliest"]
        out["reconciled_date_latest"] = row["latest"]

        cur = self._conn.execute("SELECT COUNT(DISTINCT source) AS n FROM price_bars")
        out["sources_with_data"] = cur.fetchone()["n"]

        cur = self._conn.execute("SELECT COUNT(DISTINCT strategy) AS n FROM signals")
        out["signal_strategies"] = cur.fetchone()["n"]

        cur = self._conn.execute("SELECT COUNT(*) AS n FROM signals")
        out["signal_rows"] = cur.fetchone()["n"]

        cur = self._conn.execute("SELECT COUNT(*) AS n FROM ingest_log")
        out["ingest_log_rows"] = cur.fetchone()["n"]

        lrd = self.latest_reconciled_date()
        out["latest_reconciled_date"] = lrd.isoformat() if lrd else None
        if lrd:
            cur = self._conn.execute(
                "SELECT COUNT(*) AS n, AVG(confidence) AS avg_conf FROM reconciled_prices WHERE business_date=?",
                (_d(lrd),),
            )
            row = cur.fetchone()
            out["latest_symbols"] = row["n"]
            out["latest_avg_confidence"] = round(row["avg_conf"], 4) if row["avg_conf"] else None
            cur = self._conn.execute(
                "SELECT COUNT(*) AS n FROM reconciled_prices WHERE business_date=? AND confidence<0.7",
                (_d(lrd),),
            )
            out["latest_disputed"] = cur.fetchone()["n"]

        cur = self._conn.execute("SELECT COUNT(*) AS n FROM paper_trades")
        out["paper_trades"] = cur.fetchone()["n"]

        return out

    @staticmethod
    def _row_to_bar(r: sqlite3.Row) -> PriceBar:
        return PriceBar(
            symbol=r["symbol"],
            business_date=date.fromisoformat(r["business_date"]),
            open=r["open"],
            high=r["high"],
            low=r["low"],
            close=r["close"],
            previous_close=r["previous_close"],
            volume=r["volume"],
            turnover=r["turnover"],
            trades=r["trades"],
            source=SourceName(r["source"]),
            fetched_at=datetime.fromisoformat(r["fetched_at"]) if r["fetched_at"] else None,
        )
