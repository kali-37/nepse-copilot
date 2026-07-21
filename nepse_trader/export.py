from __future__ import annotations

import csv
import logging
from pathlib import Path

from nepse_trader.storage.db import Storage

log = logging.getLogger("nepse_trader.export")

EXPORT_TABLES = {
    "price_bars": "all_price_bars",
    "reconciled_prices": "all_reconciled",
    "signals": "all_signals",
    "index_values": "all_index_values",
    "ingest_log": "all_ingest_logs",
    "corporate_actions": "all_corporate_actions",
    "paper_trades": "all_paper_trades",
}


def export_csv(storage: Storage, out_dir: Path, tables: list[str] | None = None) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    names = tables or list(EXPORT_TABLES)
    for name in names:
        meth_name = EXPORT_TABLES.get(name)
        if meth_name is None:
            log.warning("unknown table %r; skipping", name)
            continue
        rows = getattr(storage, meth_name)()
        if not rows:
            log.info("table %r is empty; skipping", name)
            continue
        path = out_dir / f"{name}.csv"
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(dict(r) for r in rows)
        written.append(path)
        log.info("exported %s → %s (%d rows)", name, path, len(rows))
    return written


def export_parquet(storage: Storage, out_dir: Path, tables: list[str] | None = None) -> list[Path]:
    try:
        import polars as pl
    except ImportError:
        log.warning("polars not installed; parquet export requires `pip install polars`")
        return []
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    names = tables or list(EXPORT_TABLES)
    for name in names:
        meth_name = EXPORT_TABLES.get(name)
        if meth_name is None:
            log.warning("unknown table %r; skipping", name)
            continue
        rows = getattr(storage, meth_name)()
        if not rows:
            log.info("table %r is empty; skipping", name)
            continue
        pdf = pl.from_dicts([dict(r) for r in rows])
        path = out_dir / f"{name}.parquet"
        pdf.write_parquet(str(path))
        written.append(path)
        log.info("exported %s → %s (%d rows)", name, path, pdf.height)
    return written
