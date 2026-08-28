"""Tests for the SQLite storage layer."""

from __future__ import annotations

import threading
from datetime import date, datetime

from nepse_trader.models import IndexValue, PriceBar, SourceName
from nepse_trader.storage import Storage

D = date(2026, 6, 9)


def _bar(symbol, close, source, **kw):
    return PriceBar(
        symbol=symbol,
        business_date=D,
        close=close,
        source=source,
        fetched_at=datetime(2026, 6, 9, 16, 0, 0),
        **kw,
    )


def test_upsert_and_read_back(tmp_path):
    db = Storage(tmp_path / "t.db")
    n = db.upsert_price_bars([_bar("nabil", 500.0, SourceName.SHARESANSAR, volume=100)])
    assert n == 1
    hist = db.price_history("NABIL")
    assert len(hist) == 1
    assert hist[0].close == 500.0
    assert hist[0].symbol == "NABIL"  # auto-uppercased
    db.close()


def test_upsert_is_idempotent_per_source(tmp_path):
    db = Storage(tmp_path / "t.db")
    db.upsert_price_bars([_bar("NABIL", 500.0, SourceName.SHARESANSAR)])
    db.upsert_price_bars([_bar("NABIL", 510.0, SourceName.SHARESANSAR)])  # same PK -> update
    hist = db.price_history("NABIL", SourceName.SHARESANSAR)
    assert len(hist) == 1
    assert hist[0].close == 510.0
    db.close()


def test_different_sources_kept_separately(tmp_path):
    db = Storage(tmp_path / "t.db")
    db.upsert_price_bars(
        [
            _bar("NABIL", 500.0, SourceName.SHARESANSAR),
            _bar("NABIL", 501.0, SourceName.MEROLAGANI),
        ]
    )
    assert len(db.price_history("NABIL")) == 2
    assert db.symbols() == ["NABIL"]
    db.close()


def test_index_values_roundtrip(tmp_path):
    db = Storage(tmp_path / "t.db")
    db.upsert_index_values(
        [
            IndexValue(
                name="NEPSE",
                business_date=D,
                value=2500.0,
                change=10.0,
                change_percent=0.4,
                source=SourceName.SHARESANSAR,
            )
        ]
    )
    db.log_ingest("sharesansar", "indices", D, 1, "ok")
    db.close()


def test_bars_for_date(tmp_path):
    db = Storage(tmp_path / "t.db")
    db.upsert_price_bars(
        [
            _bar("AAA", 10.0, SourceName.SHARESANSAR),
            _bar("BBB", 20.0, SourceName.SHARESANSAR),
        ]
    )
    rows = db.bars_for_date(D)
    assert {r.symbol for r in rows} == {"AAA", "BBB"}
    db.close()


def test_db_stats(tmp_path):
    db = Storage(tmp_path / "t.db")
    stats = db.db_stats()
    assert stats["symbols_with_data"] == 0
    assert stats["price_bar_rows"] == 0
    assert stats["reconciled_rows"] == 0
    assert stats["latest_reconciled_date"] is None

    db.upsert_price_bars([_bar("NABIL", 500.0, SourceName.SHARESANSAR, volume=100)])
    stats = db.db_stats()
    assert stats["symbols_with_data"] == 1
    assert stats["price_bar_rows"] == 1
    assert stats["price_date_earliest"] is not None
    assert stats["price_date_latest"] is not None
    db.close()


def test_latest_price_date(tmp_path):
    db = Storage(tmp_path / "t.db")
    assert db.latest_price_date() is None

    db.upsert_price_bars([_bar("NABIL", 500.0, SourceName.SHARESANSAR)])
    assert db.latest_price_date() == D

    newer = PriceBar(
        symbol="NABIL",
        business_date=date(2026, 6, 10),
        close=505.0,
        source=SourceName.SHARESANSAR,
    )
    db.upsert_price_bars([newer])
    assert db.latest_price_date() == date(2026, 6, 10)
    db.close()


def test_each_thread_gets_its_own_connection(tmp_path):
    """One connection shared across threads corrupts reads.

    Concurrent callers on a single ``sqlite3.Connection`` re-enter the same
    cached prepared statement, so a ``SELECT`` can pick up another thread's
    ``SQLITE_DONE`` and report no rows for a row that exists. That surfaced as
    the API claiming ``app_settings`` was missing on a fully migrated database.
    """
    db = Storage(tmp_path / "t.db")
    db.upsert_price_bars([_bar("NABIL", 500.0, SourceName.SHARESANSAR)])
    sql = "SELECT 1 FROM sqlite_master WHERE type='table' AND name='price_bars'"

    conns: list[int] = []
    misses = 0
    lock = threading.Lock()

    def read() -> None:
        nonlocal misses
        with lock:
            conns.append(id(db._conn))
        for _ in range(500):
            if db._conn.execute(sql).fetchone() is None:
                with lock:
                    misses += 1

    threads = [threading.Thread(target=read) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert misses == 0
    assert len(set(conns)) == len(threads)  # no connection reused across threads
    db.close()
