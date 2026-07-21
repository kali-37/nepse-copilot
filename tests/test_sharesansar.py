"""Tests for the ShareSansar ingestion client — no network.

Parsing is exercised with small inline HTML/JSON fixtures. The single network
test mocks ``/top-gainers`` with respx so nothing real is contacted.
"""

from __future__ import annotations

from datetime import date

import httpx
import respx

from nepse_trader.config import EndpointSpec, SourceSpec
from nepse_trader.ingest.base import BaseClient
from nepse_trader.ingest.sharesansar import (
    ShareSansarClient,
    _int,
    _num,
    _strip_html,
)
from nepse_trader.models import SourceName

BDATE = date(2024, 1, 15)


# A 3-row #headFixed table: two real rows (one with a blank Close that should
# fall back to LTP) plus a totals row that must be skipped. Header is <th>.
TODAY_HTML = """
<html><body>
<table id="headFixed" class="table">
  <thead>
    <tr>
      <th>S.No</th><th>Symbol</th><th>Conf.</th><th>Open</th><th>High</th>
      <th>Low</th><th>Close</th><th>LTP</th><th>Close-LTP</th><th>Close-LTP%</th>
      <th>VWAP</th><th>Vol</th><th>Prev.Close</th><th>Turnover</th><th>Trans.</th>
      <th>Diff</th><th>Range</th><th>Diff%</th><th>Range%</th><th>VWAP%</th>
      <th>120/180Days</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>1</td><td>NABIL</td><td>0.50</td><td>1,000.00</td><td>1,020.50</td>
      <td>995.00</td><td>1,010.25</td><td>1,010.25</td><td>10.25</td><td>1.02</td>
      <td>1,008.00</td><td>12,345</td><td>1,000.00</td><td>1,234,567.50</td>
      <td>250</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td>
    </tr>
    <tr>
      <td>2</td><td>KHPL</td><td>-</td><td>500.00</td><td>510.00</td>
      <td>498.00</td><td>-</td><td>505.50</td><td>-</td><td>-</td>
      <td>504.00</td><td>2,000</td><td>495.00</td><td>1,011,000.00</td>
      <td>40</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td>
    </tr>
    <tr>
      <td></td><td>Total</td><td></td><td></td><td></td><td></td><td></td>
      <td></td><td></td><td></td><td></td><td></td><td></td><td></td>
      <td></td><td></td><td></td><td></td><td></td><td></td><td></td>
    </tr>
  </tbody>
</table>
</body></html>
"""

FLOORSHEET_JSON = {
    "data": [
        {
            "contract_no": "2024011500001",
            "symbol": '<a href="https://www.sharesansar.com/company/khpl">KHPL</a>',
            "buyer": "58",
            "seller": "42",
            "quantity": "1,500",
            "rate": "505.50",
            "amount": "758,250.00",
            "date_": "2024-01-15",
        }
    ]
}

INDICES_JSON = {
    "data": [
        {
            "published_date": "2024-01-15",
            "open": "2,100.00",
            "high": "2,130.00",
            "low": "2,095.00",
            "current": "2,125.40",
            "change_": "25.40",
            "per_change": "1.21",
            "turnover": "5,000,000.00",
        }
    ]
}

TOP_GAINERS_JSON = {
    "data": [
        {
            "symbol": '<a href="https://www.sharesansar.com/company/ghl">GHL</a>',
            "companyname": '<a href="#">Ghorahi Hydropower Ltd</a>',
            "ltp": "1,200.00",
            "point_change": "109.00",
            "change_percent": "9.99",
        }
    ]
}


# -- helpers -----------------------------------------------------------------


def test_num_handles_commas_dash_and_blank():
    assert _num("1,234.50") == 1234.5
    assert _num("-") is None
    assert _num("") is None
    assert _num(None) is None
    assert _num("995.00") == 995.0


def test_int_handles_commas_and_missing():
    assert _int("12,345") == 12345
    assert _int("-") is None
    assert _int("") is None


def test_strip_html_extracts_anchor_text():
    anchor = '<a href="https://www.sharesansar.com/company/khpl">KHPL</a>'
    assert _strip_html(anchor) == "KHPL"
    assert _strip_html("PLAIN") == "PLAIN"
    assert _strip_html(None) == ""


# -- parse_today_share_price -------------------------------------------------


def test_parse_today_share_price_basic_row():
    bars = ShareSansarClient.parse_today_share_price(TODAY_HTML, BDATE, SourceName.SHARESANSAR)
    # Two data rows; the "Total" row is skipped.
    assert len(bars) == 2

    nabil = bars[0]
    assert nabil.symbol == "NABIL"
    assert nabil.business_date == BDATE
    assert nabil.open == 1000.0
    assert nabil.high == 1020.5
    assert nabil.low == 995.0
    assert nabil.close == 1010.25
    assert nabil.previous_close == 1000.0
    assert nabil.volume == 12345
    assert nabil.turnover == 1234567.5
    assert nabil.trades == 250
    assert nabil.source == SourceName.SHARESANSAR


def test_parse_today_share_price_close_falls_back_to_ltp():
    bars = ShareSansarClient.parse_today_share_price(TODAY_HTML, BDATE, SourceName.SHARESANSAR)
    khpl = bars[1]
    assert khpl.symbol == "KHPL"
    # Close cell was "-", so close should fall back to LTP (505.50).
    assert khpl.close == 505.5
    assert khpl.previous_close == 495.0
    assert khpl.volume == 2000


def test_parse_today_share_price_missing_table_returns_empty():
    assert ShareSansarClient.parse_today_share_price("<html></html>", BDATE) == []


# -- parse_floorsheet --------------------------------------------------------


def test_parse_floorsheet_strips_anchor_and_parses_numbers():
    entries = ShareSansarClient.parse_floorsheet(FLOORSHEET_JSON, BDATE)
    assert len(entries) == 1
    e = entries[0]
    assert e.symbol == "KHPL"  # anchor stripped + uppercased
    assert e.contract_id == "2024011500001"
    assert e.buyer_broker == "58"
    assert e.seller_broker == "42"
    assert e.quantity == 1500  # comma stripped
    assert e.rate == 505.5
    assert e.amount == 758250.0
    assert e.business_date == BDATE
    assert e.source == SourceName.SHARESANSAR


def test_parse_floorsheet_empty_payload():
    assert ShareSansarClient.parse_floorsheet({"data": []}, BDATE) == []
    assert ShareSansarClient.parse_floorsheet({}, BDATE) == []


# -- parse_indices -----------------------------------------------------------


def test_parse_indices_maps_current_change_perchange():
    values = ShareSansarClient.parse_indices(INDICES_JSON, "NEPSE")
    assert len(values) == 1
    v = values[0]
    assert v.name == "NEPSE"
    assert v.business_date == date(2024, 1, 15)
    assert v.value == 2125.4
    assert v.change == 25.4
    assert v.change_percent == 1.21
    assert v.source == SourceName.SHARESANSAR


# -- parse_market_status -----------------------------------------------------


def test_parse_market_status_open():
    html = "<html><body><div>Market Open</div><span>As of: 2024-01-15 15:00:00</span></body></html>"
    status = ShareSansarClient.parse_market_status(html)
    assert status.is_open is True
    assert status.as_of is not None
    assert status.source == SourceName.SHARESANSAR


def test_parse_market_status_closed_default():
    html = "<html><body><div>Market Closed</div></body></html>"
    status = ShareSansarClient.parse_market_status(html)
    assert status.is_open is False
    assert status.as_of is None


def test_parse_market_status_empty_defaults_closed():
    status = ShareSansarClient.parse_market_status("")
    assert status.is_open is False
    assert status.as_of is None
    assert status.session is None


# -- parse_top_movers --------------------------------------------------------


def test_parse_top_movers_cleans_rows():
    rows = ShareSansarClient.parse_top_movers(TOP_GAINERS_JSON)
    assert rows == [
        {
            "symbol": "GHL",
            "company": "Ghorahi Hydropower Ltd",
            "ltp": 1200.0,
            "point_change": 109.0,
            "change_percent": 9.99,
        }
    ]


# -- endpoint resolution -----------------------------------------------------


def test_url_resolution_falls_back_when_spec_lacks_endpoint():
    # An empty spec (no endpoints) -> hardcoded fallback URL.
    empty_spec = SourceSpec(name="sharesansar", endpoints={})
    client = ShareSansarClient(client=_FakeClient(), source_spec=empty_spec)
    assert client._url("top_gainers") == "https://www.sharesansar.com/top-gainers"


def test_url_resolution_prefers_spec_url():
    spec = SourceSpec(
        name="sharesansar",
        endpoints={"top_gainers": EndpointSpec(name="top_gainers", url="https://example.test/tg")},
    )
    client = ShareSansarClient(client=_FakeClient(), source_spec=spec)
    assert client._url("top_gainers") == "https://example.test/tg"


# -- a single network test (respx) -------------------------------------------


class _FakeClient:
    """Stub BaseClient that is never actually called over the network."""

    def fetch(self, *args, **kwargs):  # pragma: no cover - guarded by tests
        raise AssertionError("network should not be hit in this test")


@respx.mock
def test_top_gainers_fetch_with_respx():
    url = "https://www.sharesansar.com/top-gainers"
    respx.get(url).mock(return_value=httpx.Response(200, json=TOP_GAINERS_JSON))

    # Real BaseClient with a no-cache httpx client respx intercepts.
    http_client = httpx.Client()
    base = BaseClient(client=http_client, cache_raw=False)
    client = ShareSansarClient(client=base, source_spec=None)

    rows = client.top_gainers()
    assert rows == [
        {
            "symbol": "GHL",
            "company": "Ghorahi Hydropower Ltd",
            "ltp": 1200.0,
            "point_change": 109.0,
            "change_percent": 9.99,
        }
    ]
    http_client.close()


@respx.mock
def test_fetch_prices_returns_empty_on_error():
    url = "https://www.sharesansar.com/today-share-price"
    respx.get(url).mock(return_value=httpx.Response(404, text="nope"))

    http_client = httpx.Client()
    base = BaseClient(client=http_client, cache_raw=False)
    client = ShareSansarClient(client=base, source_spec=None)

    # 404 -> FetchError inside fetch -> degrade to [].
    assert client.fetch_prices(BDATE) == []
    http_client.close()


# ---------------------------------------------------------------------------
# Corporate actions parsing
# ---------------------------------------------------------------------------

ANNOUNCEMENTS_HTML = """
<html><body>
<table id="headFixed" class="table">
  <thead><tr><th>S.No</th><th>Headline</th><th>Symbol</th><th>Date</th></tr></thead>
  <tbody>
    <tr><td>1</td><td>NABIL Proposed 10% Bonus Share</td><td>NABIL</td><td>2082-04-15</td></tr>
    <tr><td>2</td><td>NLIC 1:1 Right Share Issue</td><td>NLIC</td><td>2082-04-20</td></tr>
    <tr><td>3</td><td>SCB announces 21% dividend</td><td>SCB</td><td>2082-05-01</td></tr>
  </tbody>
</table>
</body></html>
"""


def test_parse_corporate_actions_bonus():
    cas = ShareSansarClient.parse_corporate_actions(ANNOUNCEMENTS_HTML)
    bonuses = [ca for ca in cas if ca.action_type.value == "bonus"]
    assert len(bonuses) == 1
    assert bonuses[0].symbol == "NABIL"
    assert bonuses[0].ratio_numerator == 1
    assert bonuses[0].ratio_denominator == 10
    from decimal import Decimal as _D
    assert bonuses[0].factor == _D(str(round(100 / 110, 6)))


def test_parse_corporate_actions_rights():
    cas = ShareSansarClient.parse_corporate_actions(ANNOUNCEMENTS_HTML)
    rights = [ca for ca in cas if ca.action_type.value == "rights"]
    assert len(rights) == 1
    assert rights[0].symbol == "NLIC"


def test_parse_corporate_actions_dividend():
    cas = ShareSansarClient.parse_corporate_actions(ANNOUNCEMENTS_HTML)
    dividends = [ca for ca in cas if ca.action_type.value == "dividend"]
    assert len(dividends) == 1
    assert dividends[0].symbol == "SCB"


def test_parse_corporate_actions_empty_html():
    cas = ShareSansarClient.parse_corporate_actions("<html></html>")
    assert cas == []


@respx.mock
def test_fetch_corporate_actions_network():
    url = "https://www.sharesansar.com/announcements"
    respx.get(url).mock(return_value=httpx.Response(200, text=ANNOUNCEMENTS_HTML))

    http_client = httpx.Client()
    base = BaseClient(client=http_client, cache_raw=False)
    client = ShareSansarClient(client=base, source_spec=None)
    cas = client.fetch_corporate_actions()
    assert len(cas) == 3
    assert any(ca.action_type.value == "bonus" for ca in cas)
    http_client.close()


@respx.mock
def test_fetch_corporate_actions_error_degrades():
    url = "https://www.sharesansar.com/announcements"
    respx.get(url).mock(return_value=httpx.Response(500))
    http_client = httpx.Client()
    base = BaseClient(client=http_client, cache_raw=False)
    client = ShareSansarClient(client=base, source_spec=None)
    assert client.fetch_corporate_actions() == []
    http_client.close()
