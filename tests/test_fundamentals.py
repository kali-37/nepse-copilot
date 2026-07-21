"""Tests for fundamentals scraping."""

from __future__ import annotations

from nepse_trader.ingest.fundamentals import MeroLaganiFundamentalsClient

_SAMPLE_HTML = """
<div class="company_detail">
  <div>Sector</div>
  <div>Commercial Banks</div>
</div>
<div class="company_detail">
  <div>EPS</div>
  <div>33.34</div>
</div>
<div class="company_detail">
  <div>P/E Ratio</div>
  <div>16.47</div>
</div>
<div class="company_detail">
  <div>Book Value</div>
  <div>243.30</div>
</div>
<div class="company_detail">
  <div>PBV</div>
  <div>2.26</div>
</div>
<div class="company_detail">
  <div>Market Capitalization</div>
  <div>148,542,913,530.00</div>
</div>
<div class="company_detail">
  <div>52 Weeks High - Low</div>
  <div>563.00-471.00</div>
</div>
<div class="company_detail">
  <div>Market Price</div>
  <div>549.00</div>
</div>
<div class="company_detail">
  <div>Shares Outstanding</div>
  <div>270,569,970.00</div>
</div>
<table class="company_summary">
  <tr><td>Company Name</td><td>Nabil Bank Limited</td></tr>
</table>
"""


class TestMeroLaganiFundamentalsParse:
    def test_parse_basic_fields(self):
        client = MeroLaganiFundamentalsClient()
        data = client._parse_page(_SAMPLE_HTML, "NABIL")
        assert data is not None
        assert data.symbol == "NABIL"
        assert data.sector == "Commercial Banks"
        assert data.eps == 33.34
        assert data.pe_ratio == 16.47
        assert data.book_value == 243.30
        assert data.pbv == 2.26

    def test_market_cap(self):
        client = MeroLaganiFundamentalsClient()
        data = client._parse_page(_SAMPLE_HTML, "NABIL")
        assert data.market_cap == 148542913530.0

    def test_52w_high_low(self):
        client = MeroLaganiFundamentalsClient()
        data = client._parse_page(_SAMPLE_HTML, "NABIL")
        assert data.high_52w == 563.0
        assert data.low_52w == 471.0

    def test_market_price(self):
        client = MeroLaganiFundamentalsClient()
        data = client._parse_page(_SAMPLE_HTML, "NABIL")
        assert data.market_price == 549.0

    def test_shares_outstanding(self):
        client = MeroLaganiFundamentalsClient()
        data = client._parse_page(_SAMPLE_HTML, "NABIL")
        assert data.shares_outstanding == 270569970.0

    def test_company_name_from_summary_table(self):
        client = MeroLaganiFundamentalsClient()
        data = client._parse_page(_SAMPLE_HTML, "NABIL")
        assert data.company_name == "Nabil Bank Limited"

    def test_empty_html_returns_none(self):
        client = MeroLaganiFundamentalsClient()
        data = client._parse_page("<html></html>", "EMPTY")
        assert data is not None
        assert data.sector == ""
