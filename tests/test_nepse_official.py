"""Tests for the NEPSE official adapter (optional lib) and HAR replay client.

No network: every test feeds fixtures to pure parsers or replays an in-memory
HAR written to ``tmp_path``. The optional ``nepse_scraper`` library is assumed
absent in CI, which is exactly the path we assert below.
"""

from __future__ import annotations

import base64
import json
from datetime import date

import pytest

from nepse_trader.ingest.nepse_official import (
    HarReplayClient,
    NepseScraperClient,
    decode_content,
    find_entries,
    is_available,
    load_har,
    parse_today_price,
)
from nepse_trader.models import PriceBar, SourceName

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
NEPSE_PAYLOAD = {
    "content": [
        {
            "symbol": "nabil",
            "openPrice": 500.0,
            "highPrice": 510.0,
            "lowPrice": 495.0,
            "lastTradedPrice": 505.0,
            "previousClose": 498.0,
            "totalTradedQuantity": 12000,
            "totalTradedValue": 6060000.0,
            "totalTrades": 150,
            "businessDate": "2024-01-15",
        },
        {
            "symbol": "ADBL",
            "openPrice": 320.0,
            "highPrice": 325.0,
            "lowPrice": 318.0,
            "lastTradedPrice": 322.0,
            "previousDayClose": 319.0,
            "totalTradedQuantity": 8000,
            "totalTradedValue": 2576000.0,
            "totalTrades": 90,
            "businessDate": "2024-01-15",
        },
    ]
}

SHARESANSAR_PAYLOAD = {
    "data": [
        {
            "Symbol": "nica",
            "Open": "800",
            "High": "812",
            "Low": "798",
            "LTP": "810",
            "PreviousClose": "805",
            "Volume": "5,000",
            "Turnover": "4,050,000",
            "Trans": "60",
            "BusinessDate": "2024-02-01",
        }
    ]
}


def _make_har(body: str, *, base64_encoded: bool, url: str) -> dict:
    """Build a minimal HAR with one today-price entry carrying ``body``."""
    content: dict = {"mimeType": "application/json"}
    if base64_encoded:
        content["text"] = base64.b64encode(body.encode("utf-8")).decode("ascii")
        content["encoding"] = "base64"
    else:
        content["text"] = body
    return {
        "log": {
            "version": "1.2",
            "entries": [
                {
                    "request": {"method": "GET", "url": "https://example.test/static.js"},
                    "response": {"status": 200, "content": {"text": "irrelevant"}},
                },
                {
                    "request": {"method": "GET", "url": url},
                    "response": {"status": 200, "content": content},
                },
            ],
        }
    }


# ---------------------------------------------------------------------------
# parse_today_price (pure, NEPSE shape)
# ---------------------------------------------------------------------------
def test_parse_today_price_maps_nepse_shape() -> None:
    bars = parse_today_price(NEPSE_PAYLOAD, SourceName.NEPSE_OFFICIAL)
    assert len(bars) == 2

    nabil = bars[0]
    assert isinstance(nabil, PriceBar)
    assert nabil.symbol == "NABIL"  # auto-uppercased by the model
    assert nabil.business_date == date(2024, 1, 15)
    assert nabil.open == 500.0
    assert nabil.high == 510.0
    assert nabil.low == 495.0
    assert nabil.close == 505.0
    assert nabil.previous_close == 498.0
    assert nabil.volume == 12000
    assert nabil.turnover == 6060000.0
    assert nabil.trades == 150
    assert nabil.source == SourceName.NEPSE_OFFICIAL
    # change property derived from close/previous_close
    assert nabil.change == pytest.approx(7.0)

    # Second record uses the alternative previousDayClose key.
    assert bars[1].symbol == "ADBL"
    assert bars[1].previous_close == 319.0


def test_parse_today_price_business_date_fallback() -> None:
    payload = {"content": [{"symbol": "HBL", "lastTradedPrice": 600}]}
    bars = parse_today_price(
        payload, SourceName.NEPSE_OFFICIAL, business_date=date(2023, 12, 31)
    )
    assert len(bars) == 1
    assert bars[0].business_date == date(2023, 12, 31)
    assert bars[0].close == 600.0


def test_parse_today_price_skips_bad_records_and_never_raises() -> None:
    payload = {
        "content": [
            {"openPrice": 10},  # no symbol -> skipped
            "not-a-dict",  # wrong type -> skipped
            {"symbol": "PCBL", "lastTradedPrice": 400, "businessDate": "2024-01-15"},
        ]
    }
    bars = parse_today_price(payload, SourceName.NEPSE_OFFICIAL)
    assert [b.symbol for b in bars] == ["PCBL"]


def test_parse_today_price_handles_empty_and_garbage() -> None:
    assert parse_today_price({}, SourceName.NEPSE_OFFICIAL) == []
    assert parse_today_price({"content": []}, SourceName.NEPSE_OFFICIAL) == []
    assert parse_today_price([], SourceName.NEPSE_OFFICIAL) == []
    assert parse_today_price({"content": "oops"}, SourceName.NEPSE_OFFICIAL) == []


# ---------------------------------------------------------------------------
# HAR helpers
# ---------------------------------------------------------------------------
def test_load_har_missing_file_returns_empty(tmp_path) -> None:
    assert load_har(tmp_path / "nope.har") == {}


def test_load_har_invalid_json_returns_empty(tmp_path) -> None:
    bad = tmp_path / "bad.har"
    bad.write_text("{not json", encoding="utf-8")
    assert load_har(bad) == {}


def test_find_entries_matches_substring_case_insensitive() -> None:
    har = _make_har(
        json.dumps(NEPSE_PAYLOAD),
        base64_encoded=False,
        url="https://nepse.test/api/nots/nepse-data/TODAY-PRICE",
    )
    matched = find_entries(har, "today-price")
    assert len(matched) == 1
    assert "TODAY-PRICE" in matched[0]["request"]["url"]


def test_find_entries_tolerates_malformed_har() -> None:
    assert find_entries({}, "today-price") == []
    assert find_entries({"log": {}}, "today-price") == []
    assert find_entries({"log": {"entries": "x"}}, "today-price") == []


def test_decode_content_plain_text() -> None:
    har = _make_har(json.dumps(NEPSE_PAYLOAD), base64_encoded=False, url="x/today-price")
    entry = find_entries(har, "today-price")[0]
    assert json.loads(decode_content(entry)) == NEPSE_PAYLOAD


def test_decode_content_base64() -> None:
    har = _make_har(json.dumps(NEPSE_PAYLOAD), base64_encoded=True, url="x/today-price")
    entry = find_entries(har, "today-price")[0]
    assert json.loads(decode_content(entry)) == NEPSE_PAYLOAD


def test_decode_content_handles_missing_body() -> None:
    assert decode_content({}) == ""
    assert decode_content({"response": {}}) == ""
    assert decode_content({"response": {"content": {}}}) == ""


# ---------------------------------------------------------------------------
# HarReplayClient (plain + base64, NEPSE + ShareSansar shapes)
# ---------------------------------------------------------------------------
def test_har_replay_plain_json_nepse_shape(tmp_path) -> None:
    har_path = tmp_path / "plain.har"
    har_path.write_text(
        json.dumps(
            _make_har(
                json.dumps(NEPSE_PAYLOAD),
                base64_encoded=False,
                url="https://nepse.test/api/nots/nepse-data/today-price",
            )
        ),
        encoding="utf-8",
    )
    client = HarReplayClient(har_path)
    assert client.name == SourceName.HAR_REPLAY
    bars = client.fetch_prices()
    assert {b.symbol for b in bars} == {"NABIL", "ADBL"}
    assert all(b.source == SourceName.HAR_REPLAY for b in bars)
    assert bars[0].close == 505.0


def test_har_replay_base64_json_nepse_shape(tmp_path) -> None:
    har_path = tmp_path / "b64.har"
    har_path.write_text(
        json.dumps(
            _make_har(
                json.dumps(NEPSE_PAYLOAD),
                base64_encoded=True,
                url="https://nepse.test/today-share-price",
            )
        ),
        encoding="utf-8",
    )
    bars = HarReplayClient(har_path).fetch_prices()
    assert {b.symbol for b in bars} == {"NABIL", "ADBL"}
    assert bars[0].business_date == date(2024, 1, 15)


def test_har_replay_sharesansar_shape(tmp_path) -> None:
    har_path = tmp_path / "ss.har"
    har_path.write_text(
        json.dumps(
            _make_har(
                json.dumps(SHARESANSAR_PAYLOAD),
                base64_encoded=False,
                url="https://sharesansar.test/today-price",
            )
        ),
        encoding="utf-8",
    )
    bars = HarReplayClient(har_path).fetch_prices()
    assert len(bars) == 1
    bar = bars[0]
    assert bar.symbol == "NICA"
    assert bar.open == 800.0
    assert bar.close == 810.0
    assert bar.previous_close == 805.0
    assert bar.volume == 5000  # thousands separator stripped
    assert bar.turnover == 4050000.0
    assert bar.trades == 60
    assert bar.business_date == date(2024, 2, 1)


def test_har_replay_no_matching_entry_returns_empty(tmp_path) -> None:
    har = {
        "log": {
            "entries": [
                {
                    "request": {"url": "https://nepse.test/api/nots/market-open"},
                    "response": {"status": 200, "content": {"text": "{}"}},
                }
            ]
        }
    }
    har_path = tmp_path / "nomatch.har"
    har_path.write_text(json.dumps(har), encoding="utf-8")
    assert HarReplayClient(har_path).fetch_prices() == []


def test_har_replay_missing_file_returns_empty(tmp_path) -> None:
    assert HarReplayClient(tmp_path / "absent.har").fetch_prices() == []


def test_har_replay_non_json_body_returns_empty(tmp_path) -> None:
    har = _make_har("<html>not json</html>", base64_encoded=False, url="x/today-price")
    har_path = tmp_path / "html.har"
    har_path.write_text(json.dumps(har), encoding="utf-8")
    assert HarReplayClient(har_path).fetch_prices() == []


# ---------------------------------------------------------------------------
# Optional library availability / NepseScraperClient absent path
# ---------------------------------------------------------------------------
def test_is_available_returns_bool() -> None:
    assert isinstance(is_available(), bool)


def test_nepse_scraper_client_when_library_absent() -> None:
    """With ``nepse_scraper`` not installed (the CI default), fetches are []."""
    if is_available():
        pytest.skip("nepse_scraper is installed; absent-path test not applicable")

    client = NepseScraperClient()
    assert client.name == SourceName.NEPSE_OFFICIAL
    assert client.available is False
    assert client.fetch_prices() == []
    # Default SourceClient methods stay empty/None.
    assert client.fetch_indices() == []
    assert client.fetch_floorsheet() == []
    assert client.market_status() is None
