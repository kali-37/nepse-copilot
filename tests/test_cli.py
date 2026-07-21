"""CLI smoke tests via Typer's CliRunner (no network)."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from nepse_trader.cli.main import app
from nepse_trader.config import get_settings

runner = CliRunner()


@pytest.fixture(autouse=True)
def _temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("NEPSE_DB_PATH", str(tmp_path / "cli.db"))
    monkeypatch.setenv("NEPSE_RAW_CACHE_DIR", str(tmp_path / "raw"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "paper" in result.output


def test_sources_lists_configured():
    result = runner.invoke(app, ["sources"])
    assert result.exit_code == 0
    assert "sharesansar" in result.output


def test_paper_buy_sell_status_roundtrip():
    r1 = runner.invoke(app, ["paper", "buy", "NABIL", "--price", "1000", "--qty",
                             "100", "--date", "2026-01-10", "--cash", "200000"])
    assert r1.exit_code == 0, r1.output
    assert "BUY" in r1.output

    r2 = runner.invoke(app, ["paper", "sell", "NABIL", "--price", "1200", "--qty",
                             "100", "--date", "2026-02-10", "--cash", "200000"])
    assert r2.exit_code == 0, r2.output
    assert "CGT" in r2.output

    r3 = runner.invoke(app, ["paper", "status", "--cash", "200000"])
    assert r3.exit_code == 0
    assert "realized_pnl=17751" in r3.output  # matches the researched worked example


def test_paper_buy_insufficient_funds_rejected():
    r = runner.invoke(app, ["paper", "buy", "NABIL", "--price", "1000", "--qty",
                            "100", "--cash", "100000"])
    assert r.exit_code == 1
    assert "insufficient funds" in r.output


def test_har_analyze(tmp_path):
    har = {
        "log": {"entries": [
            {"request": {"url": "https://www.sharesansar.com/top-gainers", "method": "GET",
                         "queryString": [], "headers": []},
             "response": {"status": 200,
                          "content": {"mimeType": "application/json",
                                      "text": json.dumps({"data": [{"symbol": "NABIL", "ltp": "1"}]})},
                          "headers": []}}
        ]}
    }
    p = tmp_path / "s.har"
    p.write_text(json.dumps(har), encoding="utf-8")
    r = runner.invoke(app, ["har", "analyze", str(p)])
    assert r.exit_code == 0
    assert "json_api" in r.output


def test_har_redact_writes_file(tmp_path):
    har = {"log": {"entries": [
        {"request": {"url": "https://x/api", "method": "GET", "queryString": [],
                     "headers": [{"name": "Cookie", "value": "secret"}],
                     "cookies": [{"name": "sid", "value": "secret"}]},
         "response": {"status": 200, "content": {"mimeType": "application/json", "text": "{}"},
                      "headers": []}}
    ]}}
    p = tmp_path / "c.har"
    p.write_text(json.dumps(har), encoding="utf-8")
    r = runner.invoke(app, ["har", "redact", str(p)])
    assert r.exit_code == 0
    out = tmp_path / "c.redacted.har"
    assert out.exists()
    assert "secret" not in out.read_text()


def test_signal_no_history_is_graceful():
    r = runner.invoke(app, ["signal", "NABIL"])
    assert r.exit_code == 0
    assert "No signals" in r.output
