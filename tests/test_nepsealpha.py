"""Tests for the NepseAlpha UDF datafeed client — no network."""

from __future__ import annotations

from datetime import date

import httpx
import respx

from nepse_trader.ingest.base import BaseClient
from nepse_trader.ingest.nepsealpha import NepseAlphaClient
from nepse_trader.models import SourceName

# TradingView UDF history fixture: 3 daily bars.
UDF_HISTORY = {
    "s": "ok",
    "t": [1704067200, 1704153600, 1704240000],  # 2024-01-01, 2024-01-02, 2024-01-03
    "o": [1000.0, 1010.0, 1020.0],
    "h": [1020.0, 1030.0, 1040.0],
    "l": [990.0, 1000.0, 1010.0],
    "c": [1010.0, 1020.0, 1030.0],
    "v": [10000, 12000, 11000],
}

EMPTY_UDF = {"s": "no_data"}


class TestParseBars:
    def test_parses_three_bars(self):
        bars = NepseAlphaClient.parse_bars(UDF_HISTORY)
        assert len(bars) == 3
        assert bars[0].business_date == date(2024, 1, 1)
        assert bars[0].close == 1010.0
        assert bars[0].volume == 10000
        assert bars[1].close == 1020.0
        assert bars[2].close == 1030.0

    def test_millisecond_timestamps(self):
        ms_payload = {
            "s": "ok",
            "t": [1704067200000, 1704153600000],
            "o": [100.0, 101.0],
            "h": [102.0, 103.0],
            "l": [99.0, 100.0],
            "c": [101.0, 102.0],
            "v": [1000, 2000],
        }
        bars = NepseAlphaClient.parse_bars(ms_payload)
        assert len(bars) == 2
        assert bars[0].business_date == date(2024, 1, 1)

    def test_empty_payload(self):
        assert NepseAlphaClient.parse_bars({}) == []

    def test_not_ok_status(self):
        assert NepseAlphaClient.parse_bars({"s": "error"}) == []

    def test_source_assignment(self):
        bars = NepseAlphaClient.parse_bars(UDF_HISTORY, source=SourceName.NEPSEALPHA)
        assert all(b.source is SourceName.NEPSEALPHA for b in bars)


class TestFetchBars:
    @respx.mock
    def test_fetch_parses_correctly(self):
        url = "https://www.nepsealpha.com/api/tradingview/history?symbol=NABIL&resolution=D"
        respx.get(url).mock(return_value=httpx.Response(200, json=UDF_HISTORY))

        http_client = httpx.Client()
        base = BaseClient(client=http_client, cache_raw=False)
        client = NepseAlphaClient(client=base, source_spec=None)
        bars = client.fetch_bars("NABIL")
        assert len(bars) == 3
        assert all(b.symbol == "NABIL" for b in bars)

    @respx.mock
    def test_fetch_empty_on_error(self):
        url = "https://www.nepsealpha.com/api/tradingview/history?symbol=NABIL&resolution=D"
        respx.get(url).mock(return_value=httpx.Response(500))

        http_client = httpx.Client()
        base = BaseClient(client=http_client, cache_raw=False)
        client = NepseAlphaClient(client=base, source_spec=None)
        assert client.fetch_bars("NABIL") == []

    def test_fetch_prices_returns_empty(self):
        http_client = httpx.Client()
        base = BaseClient(client=http_client, cache_raw=False)
        client = NepseAlphaClient(client=base, source_spec=None)
        assert client.fetch_prices() == []
