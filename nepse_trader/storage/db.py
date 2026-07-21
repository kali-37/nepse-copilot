"""SQLite persistence for price bars, indices, floorsheet, signals and trades.

Schema favours idempotent daily ingestion: a price bar is unique per
(symbol, business_date, source) so re-running a day's pull upserts rather than
duplicates. Reconciled prices live in their own table keyed by (symbol, date).
"""

from __future__ import annotations

import sqlite3
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
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        self._conn.execute("PRAGMA cache_size=-64000;")
        self._conn.execute("PRAGMA temp_store=MEMORY;")
        self._conn.execute("PRAGMA foreign_keys=ON;")
        run_pending(self._conn)
        self._conn.commit()
        self._symbols_cache: list[str] | None = None

    def close(self) -> None:
        self._symbols_cache = None
        self._conn.close()

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
                    disputed_fields,confidence)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(symbol,business_date) DO UPDATE SET
                     open=excluded.open, high=excluded.high, low=excluded.low,
                     close=excluded.close, previous_close=excluded.previous_close,
                     volume=excluded.volume, turnover=excluded.turnover,
                     sources_agreeing=excluded.sources_agreeing,
                     sources_present=excluded.sources_present,
                     disputed_fields=excluded.disputed_fields,
                     confidence=excluded.confidence""",
                rows,
            )
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

    def reconciled_history(self, symbol: str) -> list[ReconciledPrice]:
        symbol = symbol.strip().upper()
        cur = self._conn.execute(
            "SELECT * FROM reconciled_prices WHERE symbol=? ORDER BY business_date",
            (symbol,),
        )
        out = []
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

    def latest_reconciled_date(self) -> date | None:
        cur = self._conn.execute("SELECT MAX(business_date) AS d FROM reconciled_prices")
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
