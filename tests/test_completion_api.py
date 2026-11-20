from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from nepse_trader.config import Settings
from nepse_trader.models import FundamentalData, PriceBar, SourceName
from nepse_trader.pipeline import DailyPipeline
from nepse_trader.storage import Storage
from nepse_trader.web.api import _state, app
from nepse_trader.web.jobs import registry


@pytest.fixture
def client(tmp_path):
    storage = Storage(tmp_path / "db")
    settings = Settings(_env_file=None, db_path=storage.db_path, online=False)
    storage.upsert_price_bars([PriceBar(symbol=symbol, business_date=date(2026, 1, 1) + timedelta(days=i),
        close=100 + i * 0.1, open=100 + i * 0.1, high=102 + i * 0.1, low=99 + i * 0.1,
        previous_close=99.9 + i * 0.1, source=SourceName.SHARESANSAR) for symbol in ["A", "B"] for i in range(100)])
    pipe = DailyPipeline(settings, storage, clients=[])
    for day in [date(2026, 1, 1) + timedelta(days=i) for i in range(100)]:
        pipe.reconcile(day)
    storage.upsert_fundamental(FundamentalData(symbol="A", pe_ratio=10, eps=5, sector="Banks"), date(2026, 1, 1))
    _state.update(storage=storage, settings=settings)
    registry.reset()
    with TestClient(app) as http:
        yield http
    registry.reset()
    storage.close()
    _state.clear()


def test_portfolio_walk_forward_market_and_fundamentals_are_available_offline(client):
    assert client.get("/api/research/portfolio?symbols=A,B").status_code == 200
    result = client.get("/api/research/walk-forward?symbol=A").json()
    assert result["folds"]
    market = client.get("/api/research/market").json()
    assert {row["sector"] for row in market["sectors"]} == {"Banks", "Unclassified"}
    assert client.get("/api/symbols/A/fundamentals").json()["pe_ratio"] == 10
    assert client.get("/api/symbols/B/fundamentals").status_code == 404


def test_valuation_screen_uses_stored_snapshot_and_excludes_missing(client):
    response = client.get("/api/backtest/screen?max_pe=15&strategies=sma_cross")
    assert response.status_code == 200
    assert {row["symbol"] for row in response.json()} == {"A"}


def test_research_boundaries_reject_invalid_inputs(client):
    assert client.get("/api/research/portfolio?symbols=A&cash=-1").status_code == 422
    assert client.get("/api/research/walk-forward?symbol=A&train_pct=0.8&val_pct=0.8").status_code == 400
    assert client.get("/api/research/walk-forward?symbol=A&strategy=bogus").status_code == 400


def test_backfill_job_honors_offline_settings_and_rejects_invalid_symbol_type(client):
    for params in [{"symbols": ["A"]}, {"symbols": 123}]:
        response = client.post("/api/jobs", json={"kind": "backfill", "params": params})
        assert response.status_code == 200
        job_id = response.json()["id"]
        registry.join(job_id)
        result = client.get(f"/api/jobs/{job_id}").json()
        assert result["status"] == "failed"
        assert "online" in result["error"] or "Symbols must" in result["error"]
