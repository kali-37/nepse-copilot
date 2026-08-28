from __future__ import annotations

from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient

from nepse_trader.models import PriceBar, ReconciledPrice, SourceName
from nepse_trader.storage import Storage
from nepse_trader.web.api import app


@pytest.fixture
def client(tmp_path):
    db = tmp_path / "test.db"
    storage = Storage(db)
    storage.upsert_price_bars(
        [
            PriceBar(
                symbol="TEST",
                business_date=date(2024, 1, 1),
                open=100.0,
                high=105.0,
                low=99.0,
                close=102.0,
                volume=1000,
                source=SourceName.SHARESANSAR,
                fetched_at=datetime(2024, 1, 1, 12, 0),
            ),
            PriceBar(
                symbol="TEST",
                business_date=date(2024, 1, 2),
                open=102.0,
                high=108.0,
                low=101.0,
                close=107.0,
                volume=1200,
                source=SourceName.SHARESANSAR,
                fetched_at=datetime(2024, 1, 2, 12, 0),
            ),
        ]
    )
    storage.upsert_reconciled(
        [
            ReconciledPrice(
                symbol="TEST",
                business_date=date(2024, 1, 1),
                open=100.0,
                high=105.0,
                low=99.0,
                close=102.0,
                volume=1000,
                turnover=0.0,
                sources_agreeing=[SourceName.SHARESANSAR],
                sources_present=[SourceName.SHARESANSAR],
                disputed_fields=[],
                confidence=1.0,
            ),
            ReconciledPrice(
                symbol="TEST",
                business_date=date(2024, 1, 2),
                open=102.0,
                high=108.0,
                low=101.0,
                close=107.0,
                volume=1200,
                turnover=0.0,
                sources_agreeing=[SourceName.SHARESANSAR],
                sources_present=[SourceName.SHARESANSAR],
                disputed_fields=[],
                confidence=1.0,
            ),
        ]
    )
    from nepse_trader.web.api import _state
    _state["storage"] = storage
    with TestClient(app) as c:
        yield c
    storage.close()
    _state.clear()


class TestHealth:
    def test_health(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}


class TestDashboard:
    def test_dashboard_stats(self, client):
        r = client.get("/api/dashboard")
        assert r.status_code == 200
        data = r.json()
        assert data["symbols_with_data"] == 1
        assert data["price_bar_rows"] == 2

    def test_market_breadth(self, client):
        r = client.get("/api/market-breadth")
        assert r.status_code == 200
        data = r.json()
        assert "symbols" in data

    def test_movers(self, client):
        r = client.get("/api/movers")
        assert r.status_code == 200
        data = r.json()
        assert "gainers" in data
        assert "losers" in data


class TestSymbols:
    def test_list_symbols(self, client):
        r = client.get("/api/symbols")
        assert r.status_code == 200
        assert r.json() == ["TEST"]

    def test_symbol_prices(self, client):
        r = client.get("/api/symbols/TEST/prices")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 2
        assert data[0]["business_date"] == "2024-01-01"
        assert data[0]["close"] == 102.0

    def test_symbol_prices_limit(self, client):
        r = client.get("/api/symbols/TEST/prices?limit=1")
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_symbol_prices_time_range(self, client):
        r = client.get("/api/symbols/TEST/prices?start=2024-01-02&end=2024-01-02")
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert r.json()[0]["business_date"] == "2024-01-02"

    def test_symbol_signals_missing_strategy(self, client):
        r = client.get("/api/symbols/TEST/signals?strategy=nonexistent")
        assert r.status_code == 400

    def test_symbol_quant(self, client):
        r = client.get("/api/symbols/TEST/quant")
        assert r.status_code == 200
        data = r.json()
        assert data["symbol"] == "TEST"
        assert data["n"] == 2

    def test_symbol_unknown(self, client):
        r = client.get("/api/symbols/UNKNOWN/prices")
        assert r.status_code == 200
        assert r.json() == []


class TestPortfolio:
    def test_portfolio_empty(self, client):
        r = client.get("/api/portfolio")
        assert r.status_code == 200
        data = r.json()
        assert data["initial_cash"] == 100_000.0
        assert data["trades"] == 0


class TestBacktest:
    def test_backtest_run(self, client):
        r = client.get("/api/backtest/run?symbol=TEST&strategy=sma_cross")
        assert r.status_code == 200
        data = r.json()
        assert "summary" in data
        assert "equity_curve" in data

    def test_backtest_screen_empty(self, client):
        r = client.get("/api/backtest/screen")
        assert r.status_code == 200
        assert r.json() == []


class TestSpaFallback:
    """Deep links like /rashifal must serve the app, not a 404."""

    def test_unknown_page_path_serves_index(self, client):
        r = client.get("/rashifal")
        # The dist build may be absent in CI; then the app is API-only and the
        # route legitimately 404s, so only assert when the frontend is mounted.
        from nepse_trader.web.api import app

        mounted = any(
            getattr(route, "name", "") == "frontend" for route in app.routes
        )
        if mounted:
            assert r.status_code == 200
            assert r.headers["content-type"].startswith("text/html")

    def test_api_paths_keep_json_404s(self, client):
        r = client.get("/api/bogus")
        assert r.status_code == 404
        assert r.headers["content-type"].startswith("application/json")
