"""Tests for the Chukul JSON adapter. No network: synthetic payloads + respx."""

from __future__ import annotations

from datetime import date

import httpx
import respx

from nepse_trader.config import EndpointSpec, SourceSpec
from nepse_trader.ingest.base import BaseClient
from nepse_trader.ingest.chukul import ChukulClient
from nepse_trader.models import SourceName

BUSINESS_DATE = date(2026, 6, 10)

# Three accepted envelope shapes, each using a DIFFERENT key casing/alias set to
# prove the flexible _pick mapping works regardless of source naming drift.
PRICES_AS_LIST = [
    {
        "symbol": "nabil",
        "ltp": 1234.5,
        "open": 1200,
        "high": 1250,
        "low": 1195,
        "previous_close": 1204.4,
        "volume": 12345,
        "turnover": 15000000.75,
    },
    {"ticker": "NICA", "last_price": 950.0, "qty": 5000},
]

PRICES_AS_DATA = {
    "data": [
        {
            "Symbol": "NABIL",
            "lastTradedPrice": "1,234.50",
            "Open": "1,200.00",
            "High": "1,250.00",
            "Low": "1,195.00",
            "prevClose": "1,204.40",
            "totalTradedQuantity": "12,345",
            "amount": "15,000,000.75",
        }
    ]
}

PRICES_AS_RESULTS = {
    "results": [
        {"scrip": "NABIL", "close": 1234.5, "totalTradedQuantity": 12345},
        {"name": "no-symbol-here", "close": 1.0},  # skipped: no symbol key
    ]
}

INDICES_PAYLOAD = {
    "data": [
        {"name": "NEPSE", "value": 2100.55, "change": 10.5, "percent_change": 0.5},
        {"index": "Sensitive", "close": "400.10", "point_change": "-1.20"},
    ]
}


def _by_symbol(bars):
    return {b.symbol: b for b in bars}


def test_parse_prices_list_shape_and_aliases():
    bars = ChukulClient.parse_prices(PRICES_AS_LIST, BUSINESS_DATE)
    by = _by_symbol(bars)
    assert set(by) == {"NABIL", "NICA"}  # symbol auto-uppercased by model
    nabil = by["NABIL"]
    assert nabil.close == 1234.5
    assert nabil.open == 1200.0
    assert nabil.previous_close == 1204.4
    assert nabil.volume == 12345
    assert nabil.turnover == 15000000.75
    assert nabil.source == SourceName.CHUKUL
    # ticker alias + last_price alias resolve for the second record.
    assert by["NICA"].close == 950.0
    assert by["NICA"].volume == 5000


def test_parse_prices_data_shape_with_string_numbers():
    bars = ChukulClient.parse_prices(PRICES_AS_DATA, BUSINESS_DATE)
    assert len(bars) == 1
    nabil = bars[0]
    assert nabil.symbol == "NABIL"
    assert nabil.close == 1234.5  # parsed from "1,234.50"
    assert nabil.previous_close == 1204.4
    assert nabil.volume == 12345
    assert nabil.turnover == 15000000.75


def test_parse_prices_results_shape_skips_symbolless_rows():
    bars = ChukulClient.parse_prices(PRICES_AS_RESULTS, BUSINESS_DATE)
    assert [b.symbol for b in bars] == ["NABIL"]
    assert bars[0].volume == 12345


def test_parse_prices_unexpected_shape_returns_empty():
    assert ChukulClient.parse_prices(42, BUSINESS_DATE) == []
    assert ChukulClient.parse_prices({"oops": 1}, BUSINESS_DATE) == []
    assert ChukulClient.parse_prices(None, BUSINESS_DATE) == []


def test_parse_indices_flexible_keys():
    indices = ChukulClient.parse_indices(INDICES_PAYLOAD, BUSINESS_DATE)
    assert [i.name for i in indices] == ["NEPSE", "Sensitive"]
    assert indices[0].value == 2100.55
    assert indices[0].change == 10.5
    assert indices[0].change_percent == 0.5
    assert indices[1].value == 400.10  # parsed from "400.10"
    assert indices[1].change == -1.20
    assert indices[0].source == SourceName.CHUKUL


def test_config_driven_urls_override_defaults():
    spec = SourceSpec(
        name="chukul",
        endpoints={
            "live": EndpointSpec(name="live", url="https://api.chukul.com/v1/custom/live/"),
            "index": EndpointSpec(name="index", url="https://api.chukul.com/v1/custom/index/"),
        },
    )
    client = ChukulClient(client=object(), source_spec=spec)
    assert client.prices_url == "https://api.chukul.com/v1/custom/live/"
    assert client.index_url == "https://api.chukul.com/v1/custom/index/"


def test_default_urls_when_no_spec():
    client = ChukulClient(client=object())
    assert client.prices_url.startswith("https://api.chukul.com/v1/")
    assert client.index_url.startswith("https://api.chukul.com/v1/")


@respx.mock
def test_fetch_prices_over_respx():
    route = respx.get("https://api.chukul.com/v1/market/live/").mock(
        return_value=httpx.Response(200, json=PRICES_AS_LIST)
    )
    client = ChukulClient(client=BaseClient(cache_raw=False))
    bars = client.fetch_prices(BUSINESS_DATE)
    assert route.called
    assert {b.symbol for b in bars} == {"NABIL", "NICA"}
    assert all(b.source == SourceName.CHUKUL for b in bars)


@respx.mock
def test_fetch_prices_empty_on_error():
    respx.get("https://api.chukul.com/v1/market/live/").mock(
        return_value=httpx.Response(404, json={"detail": "not found"})
    )
    client = ChukulClient(client=BaseClient(cache_raw=False))
    assert client.fetch_prices(BUSINESS_DATE) == []
