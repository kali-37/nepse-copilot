"""Golden-file tests: load fixture files and assert parsers produce expected output.

These tests detect layout drift — if a source changes column names or HTML
structure, the fixture stays frozen and the test fails, alerting us to update.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from nepse_trader.ingest.chukul import ChukulClient
from nepse_trader.ingest.merolagani import MeroLaganiClient
from nepse_trader.ingest.sharesansar import ShareSansarClient
from nepse_trader.models import SourceName

FIXTURES = Path(__file__).resolve().parent / "fixtures"
BDATE = date(2024, 1, 15)


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# ---- ShareSansar golden tests -------------------------------------------


def test_ss_today_share_price() -> None:
    raw = _load("sharesansar_today.html")
    bars = ShareSansarClient.parse_today_share_price(raw, BDATE)
    # NABIL row: close from explicit Close (not LTP fallback).
    nabil = [b for b in bars if b.symbol == "NABIL"]
    assert len(nabil) == 1
    b = nabil[0]
    assert b.close == 1010.25
    assert b.open == 1000.00
    assert b.high == 1020.50
    assert b.low == 995.00
    assert b.volume == 12345
    assert b.turnover == 1234567.50
    assert b.previous_close == 1000.00
    assert b.trades == 250
    assert b.source == SourceName.SHARESANSAR

    # KHPL row: close falls back to LTP (Close was "-").
    khpl = [b for b in bars if b.symbol == "KHPL"]
    assert len(khpl) == 1
    b = khpl[0]
    assert b.close == 505.50  # LTP fallback
    assert b.volume == 2000

    # Total row skipped.
    assert len(bars) == 2


def test_ss_floorsheet() -> None:
    raw = _load("sharesansar_floorsheet.json")
    entries = ShareSansarClient.parse_floorsheet(json.loads(raw), BDATE)
    assert len(entries) == 1
    e = entries[0]
    assert e.symbol == "KHPL"
    assert e.contract_id == "2024011500001"
    assert e.buyer_broker == "58"
    assert e.seller_broker == "42"
    assert e.quantity == 1500
    assert e.rate == 505.50
    assert e.amount == 758250.00


# ---- MeroLagani golden tests --------------------------------------------


def test_ml_stock_quote() -> None:
    raw = _load("merolagani_stock_quote.html")
    bars = MeroLaganiClient.parse_stock_quote(raw, BDATE)
    nabil = [b for b in bars if b.symbol == "NABIL"]
    assert len(nabil) == 1
    b = nabil[0]
    assert b.close == 1234.50
    assert b.open == 1200.00
    assert b.high == 1250.00
    assert b.low == 1195.00
    assert b.volume == 12345
    assert b.turnover == 15000000.75
    assert b.previous_close == 1204.40
    assert b.source == SourceName.MEROLAGANI

    nica = [b for b in bars if b.symbol == "NICA"]
    assert len(nica) == 1
    b = nica[0]
    assert b.close == 950.00

    # Empty-symbol row is skipped.
    assert len(bars) == 2


def test_ml_indices() -> None:
    raw = _load("merolagani_indices.html")
    indices = MeroLaganiClient.parse_indices(raw, business_date=BDATE)
    nepsi = [i for i in indices if i.name == "NEPSE Index"]
    assert len(nepsi) == 1
    i = nepsi[0]
    assert i.value == 2100.55
    assert i.change == 10.50
    assert i.change_percent == 0.50

    sens = [i for i in indices if i.name == "Sensitive"]
    assert len(sens) == 1
    assert sens[0].value == 400.10

    # Empty-name row is skipped.
    assert len(indices) == 2


# ---- Chukul golden tests ------------------------------------------------


def test_chukul_prices_list() -> None:
    raw = _load("chukul_prices_list.json")
    client = ChukulClient()
    bars = client.parse_prices(json.loads(raw), BDATE)
    nabil = [b for b in bars if b.symbol == "NABIL"]
    assert len(nabil) == 1
    b = nabil[0]
    assert b.close == 1234.50
    assert b.open == 1200.00
    assert b.high == 1250.00
    assert b.low == 1195.00
    assert b.volume == 12345
    assert b.turnover == 15000000.75
    assert b.previous_close == 1204.40

    nica = [b for b in bars if b.symbol == "NICA"]
    assert len(nica) == 1
    assert nica[0].close == 950.00


def test_chukul_prices_data() -> None:
    raw = _load("chukul_prices_data.json")
    client = ChukulClient()
    bars = client.parse_prices(json.loads(raw), BDATE)
    nabil = [b for b in bars if b.symbol == "NABIL"]
    assert len(nabil) == 1
    b = nabil[0]
    assert b.close == 1234.50
    assert b.open == 1200.00
    assert b.high == 1250.00
    assert b.low == 1195.00


def test_chukul_prices_results() -> None:
    raw = _load("chukul_prices_results.json")
    client = ChukulClient()
    bars = client.parse_prices(json.loads(raw), BDATE)
    nabil = [b for b in bars if b.symbol == "NABIL"]
    assert len(nabil) == 1
    assert nabil[0].close == 1234.50
    assert nabil[0].volume == 12345
    # Row without a symbol key is skipped.
    assert len(bars) == 1
