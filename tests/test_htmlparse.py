"""Tests for the resilient HTML table extractor (Scrapling / selectolax)."""

from __future__ import annotations

import pytest

from nepse_trader.ingest import htmlparse as hp

_HTML = """
<table id="headFixed">
  <tr><th>S.No</th><th>Symbol</th><th>Close</th></tr>
  <tr><td>1</td><td><a href="/company/nabil">NABIL</a></td><td>1,234.50</td></tr>
  <tr><td>2</td><td>ADBL</td><td>-</td></tr>
  <tr><td></td><td>Total</td><td>9,999</td></tr>
</table>
"""

_EXPECTED = [
    [("th", "S.No"), ("th", "Symbol"), ("th", "Close")],
    [("td", "1"), ("td", "NABIL"), ("td", "1,234.50")],
    [("td", "2"), ("td", "ADBL"), ("td", "-")],
    [("td", ""), ("td", "Total"), ("td", "9,999")],
]


def test_selectolax_backend_matches_expected():
    assert hp.table_rows(_HTML, "table#headFixed", engine="selectolax") == _EXPECTED


@pytest.mark.skipif(not hp.scrapling_available(), reason="scrapling not installed")
def test_scrapling_backend_matches_selectolax():
    # The whole point: both backends produce byte-identical rows, incl. anchor text.
    sc = hp.table_rows(_HTML, "table#headFixed", engine="scrapling")
    assert sc == _EXPECTED


def test_missing_table_returns_empty():
    assert hp.table_rows("<div>no table</div>", "table#headFixed") == []
    assert hp.table_rows("", "table#headFixed") == []


def test_helpers():
    row = [("th", "X")]
    assert hp.has_header(row)
    body = [("td", "A"), ("th", "skip"), ("td", "B")]
    assert hp.td_texts(body) == ["A", "B"]


def test_resolve_engine_explicit_selectolax():
    assert hp.resolve_engine("selectolax") == "selectolax"


def test_resolve_engine_auto_picks_available():
    resolved = hp.resolve_engine("auto")
    assert resolved in ("scrapling", "selectolax")
    if hp.scrapling_available():
        assert resolved == "scrapling"
