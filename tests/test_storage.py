"""Tests for the SQLite storage layer."""

from __future__ import annotations

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
