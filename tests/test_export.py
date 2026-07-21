from __future__ import annotations

import csv
import tempfile
from pathlib import Path

from nepse_trader.export import export_csv, export_parquet
from nepse_trader.storage import Storage


def _populate(storage: Storage) -> None:
    from datetime import date, datetime

    from nepse_trader.models import PriceBar, SourceName

    storage.upsert_price_bars(
        [
            PriceBar(
                symbol="TEST",
                business_date=date(2024, 1, 1),
                open=100.0,
                high=105.0,
                low=99.0,
                close=102.0,
                volume=1000,
                source=SourceName.SHARESANSAR,
                fetched_at=datetime(2024, 1, 1, 12, 0),
            ),
            PriceBar(
                symbol="TEST",
                business_date=date(2024, 1, 2),
                open=102.0,
                high=108.0,
                low=101.0,
                close=107.0,
                volume=1200,
                source=SourceName.SHARESANSAR,
                fetched_at=datetime(2024, 1, 2, 12, 0),
            ),
        ]
    )


def test_export_csv() -> None:
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "test.db"
        storage = Storage(db)
        _populate(storage)

        out = Path(td) / "csv_out"
        written = export_csv(storage, out, ["price_bars"])
        assert len(written) == 1
        assert written[0].name == "price_bars.csv"

        with open(written[0]) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["symbol"] == "TEST"
        assert rows[0]["close"] == "102.0"


def test_export_parquet_no_polars() -> None:
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "test.db"
        storage = Storage(db)
        _populate(storage)

        out = Path(td) / "pq_out"
        written = export_parquet(storage, out, ["price_bars"])
        assert written == []  # polars not installed


def test_export_unknown_table() -> None:
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "test.db"
        storage = Storage(db)
        _populate(storage)

        out = Path(td) / "csv_out"
        written = export_csv(storage, out, ["nonexistent"])
        assert written == []


def test_export_empty_table() -> None:
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "test.db"
        storage = Storage(db)

        out = Path(td) / "csv_out"
        written = export_csv(storage, out, ["price_bars"])
        assert written == []
