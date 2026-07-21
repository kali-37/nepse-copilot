"""Tests for the MeroLagani HTML adapter. No network: fixtures + one respx call."""

from __future__ import annotations

from datetime import date

import httpx
import respx

from nepse_trader.ingest.base import BaseClient
from nepse_trader.ingest.merolagani import MeroLaganiClient
from nepse_trader.models import SourceName

BUSINESS_DATE = date(2026, 6, 10)

# Realistic-ish StockQuote.aspx markup: a header row mapped by NAME, columns in
# a deliberately non-obvious order, comma-grouped numbers, and a junk row to be
# skipped (no symbol). A second smaller table exists to confirm we pick the
# largest matching one.
STOCK_QUOTE_HTML = """
<html><body>
  <table id="decoy">
    <thead><tr><th>Symbol</th><th>LTP</th></tr></thead>
    <tbody><tr><td>ZZZ</td><td>1.00</td></tr></tbody>
  </table>
  <table id="headFixed" class="table">
    <thead>
      <tr>
        <th>S.No</th><th>Symbol</th><th>LTP</th><th>% Change</th>
        <th>Open</th><th>High</th><th>Low</th><th>Qty</th>
        <th>Turnover</th><th>Prev. Close</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td>1</td><td>NABIL</td><td>1,234.50</td><td>2.50</td>
        <td>1,200.00</td><td>1,250.00</td><td>1,195.00</td><td>12,345</td>
        <td>15,000,000.75</td><td>1,204.40</td>
      </tr>
      <tr>
        <td>2</td><td>NICA</td><td>950.00</td><td>-1.00</td>
        <td>960.00</td><td>965.00</td><td>948.00</td><td>5,000</td>
        <td>4,750,000.00</td><td>959.60</td>
      </tr>
      <tr>
        <td>3</td><td></td><td>-</td><td>-</td>
        <td>-</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td>
      </tr>
    </tbody>
  </table>
</body></html>
"""

INDICES_HTML = """
<html><body>
  <table class="table">
    <thead>
      <tr><th>Index</th><th>Value</th><th>Change</th><th>% Change</th></tr>
    </thead>
    <tbody>
      <tr><td>NEPSE Index</td><td>2,100.55</td><td>10.50</td><td>0.50</td></tr>
      <tr><td>Sensitive</td><td>400.10</td><td>-1.20</td><td>-0.30</td></tr>
      <tr><td></td><td>-</td><td>-</td><td>-</td></tr>
    </tbody>
  </table>
</body></html>
"""


def test_parse_stock_quote_maps_columns_by_header_name():
    bars = MeroLaganiClient.parse_stock_quote(
        STOCK_QUOTE_HTML, BUSINESS_DATE, SourceName.MEROLAGANI
    )
    # The junk (no-symbol) row is skipped; the larger table wins over the decoy.
    assert [b.symbol for b in bars] == ["NABIL", "NICA"]

    nabil = bars[0]
    assert nabil.close == 1234.50
    assert nabil.open == 1200.00
    assert nabil.high == 1250.00
    assert nabil.low == 1195.00
    assert nabil.previous_close == 1204.40
    assert nabil.volume == 12345
    assert nabil.turnover == 15000000.75
    assert nabil.business_date == BUSINESS_DATE
    assert nabil.source == SourceName.MEROLAGANI
    # change/change_percent derive from close - previous_close.
    assert nabil.change is not None and round(nabil.change, 2) == 30.10


def test_parse_stock_quote_handles_missing_table():
    assert MeroLaganiClient.parse_stock_quote("<html><body>no tables</body></html>",
                                              BUSINESS_DATE) == []


def test_parse_indices_maps_name_and_value():
    indices = MeroLaganiClient.parse_indices(INDICES_HTML, SourceName.MEROLAGANI,
                                             BUSINESS_DATE)
    assert [i.name for i in indices] == ["NEPSE Index", "Sensitive"]
    nepse = indices[0]
    assert nepse.value == 2100.55
    assert nepse.change == 10.50
    assert nepse.change_percent == 0.50
    assert nepse.source == SourceName.MEROLAGANI
    assert nepse.business_date == BUSINESS_DATE


def test_endpoint_urls_default():
    client = MeroLaganiClient(client=object())  # client unused for URL props
    assert client.stock_quote_url.endswith("StockQuote.aspx")
    assert client.indices_url.endswith("Indices.aspx")


@respx.mock
def test_fetch_prices_over_respx():
    route = respx.get("https://merolagani.com/StockQuote.aspx").mock(
        return_value=httpx.Response(200, text=STOCK_QUOTE_HTML)
    )
    client = MeroLaganiClient(client=BaseClient(cache_raw=False))
    bars = client.fetch_prices(BUSINESS_DATE)
    assert route.called
    assert {b.symbol for b in bars} == {"NABIL", "NICA"}
    assert all(b.source == SourceName.MEROLAGANI for b in bars)


@respx.mock
def test_fetch_prices_returns_empty_on_error():
    # 404 -> FetchError (non-retryable): fetch is wrapped so we get [] back.
    respx.get("https://merolagani.com/StockQuote.aspx").mock(
        return_value=httpx.Response(404, text="not found")
    )
    client = MeroLaganiClient(client=BaseClient(cache_raw=False))
    assert client.fetch_prices(BUSINESS_DATE) == []
