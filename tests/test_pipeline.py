"""Integration tests for the daily pipeline (no network)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from nepse_trader.analysis.costs import CostEngine
from nepse_trader.config import get_settings
from nepse_trader.ingest.base import SourceClient
from nepse_trader.models import IndexValue, PriceBar, SourceName
from nepse_trader.pipeline import DailyPipeline
from nepse_trader.storage import Storage

START = date(2026, 1, 1)


class _StubSource(SourceClient):
    """A fake source that returns canned bars — exercises ingest without network."""

    def __init__(self, name: SourceName, offset: float = 0.0):
        self.name = name
        self._offset = offset

    def fetch_prices(self, business_date=None):
        bd = business_date or START
        return [
            PriceBar(symbol="NABIL", business_date=bd, open=500, high=505, low=495,
                     close=500 + self._offset, previous_close=498, volume=1000,
                     turnover=500000, source=self.name)
        ]

    def fetch_indices(self, business_date=None):
        bd = business_date or START
        return [IndexValue(name="NEPSE", business_date=bd, value=2500.0, source=self.name)]


@pytest.fixture
def pipe(tmp_path):
    storage = Storage(tmp_path / "p.db")
    clients = [
        _StubSource(SourceName.SHARESANSAR, 0.0),
        _StubSource(SourceName.MEROLAGANI, 0.2),  # within tolerance
    ]
    return DailyPipeline(storage=storage, clients=clients, cost_engine=CostEngine())


def test_ingest_then_reconcile(pipe):
    rep = pipe.ingest(START)
    assert rep.total_bars == 2  # one per stub source
    assert rep.total_indices == 2
    assert not rep.errors
    prices = pipe.reconcile(START)
    assert len(prices) == 1
    assert prices[0].symbol == "NABIL"
    assert prices[0].confidence == 1.0  # both sources agree within tolerance
    assert prices[0].is_trustworthy


def test_ingest_isolates_failing_source(pipe, tmp_path):
    class _Boom(SourceClient):
        name = SourceName.CHUKUL

        def fetch_prices(self, business_date=None):
            raise RuntimeError("boom")

    pipe.clients.append(_Boom())
    rep = pipe.ingest(START)
    # Errors are keyed per data type ("<source>:<kind>"); the failing source is isolated.
    assert any(k.startswith("chukul") for k in rep.errors)
    assert rep.total_bars == 2  # the two healthy sources still ingested


def test_ingest_isolates_failing_data_type_keeps_the_other(pipe):
    # A source whose indices fail must still contribute its prices.
    class _HalfBroken(SourceClient):
        name = SourceName.CHUKUL

        def fetch_prices(self, business_date=None):
            return [PriceBar(symbol="XYZ", business_date=START, close=100.0, source=self.name)]

        def fetch_indices(self, business_date=None):
            raise RuntimeError("indices boom")

    pipe.clients = [_HalfBroken()]
    rep = pipe.ingest(START)
    assert rep.total_bars == 1  # prices survived
    assert "chukul:indices" in rep.errors  # only indices failed
    assert "chukul:prices" not in rep.errors


def test_signals_for_uses_reconciled_history(pipe):
    # Seed a rise-then-fall path across both sources, reconcile, then signal.
    bars = []
    for i in range(60):
        d = START + timedelta(days=i)
        base = 500 + (i if i < 30 else 60 - i) * 3
        for src in (SourceName.SHARESANSAR, SourceName.MEROLAGANI):
            bars.append(PriceBar(symbol="NABIL", business_date=d, close=float(base), source=src))
    pipe.storage.upsert_price_bars(bars)
    for i in range(60):
        pipe.reconcile(START + timedelta(days=i))
    sigs = pipe.signals_for("NABIL", "sma_cross", fast=3, slow=8)
    actions = {s.action.value for s in sigs}
    assert "BUY" in actions and "SELL" in actions


def test_replay_portfolio_roundtrip(pipe):
    pf = pipe.replay_portfolio(initial_cash=200_000.0)
    pf.storage = pipe.storage
    pf.buy("NABIL", 1000, 100, START)
    pf.sell("NABIL", 1200, 100, START + timedelta(days=30))
    # Re-derive from storage; state must match.
    pf2 = pipe.replay_portfolio(initial_cash=200_000.0)
    assert abs(pf2.cash - pf.cash) < 0.01
    assert abs(pf2.realized_pnl - pf.realized_pnl) < 0.01
    assert pf2.realized_pnl > 0


def test_build_clients_respects_enabled(monkeypatch, tmp_path):
    # Only sharesansar is enabled in config/sources.yaml by default.
    monkeypatch.setenv("NEPSE_DB_PATH", str(tmp_path / "x.db"))
    get_settings.cache_clear()
    from nepse_trader.pipeline import build_clients

    clients = build_clients()
    names = {c.name for c in clients}
    assert SourceName.SHARESANSAR in names
    get_settings.cache_clear()


def test_build_clients_include_all_scrapes_every_source(monkeypatch, tmp_path):
    monkeypatch.setenv("NEPSE_DB_PATH", str(tmp_path / "y.db"))
    get_settings.cache_clear()
    from nepse_trader.pipeline import build_clients

    clients = build_clients(include_all=True)
    names = {c.name for c in clients}
    # Every known source is constructed regardless of the enabled flag.
    assert {
        SourceName.SHARESANSAR,
        SourceName.MEROLAGANI,
        SourceName.CHUKUL,
        SourceName.NEPSE_OFFICIAL,
    } <= names
    get_settings.cache_clear()


def _seed_hump(pipe, days=70, symbols=("AAA", "BBB")):
    bars = []
    for i in range(days):
        d = START + timedelta(days=i)
        base = 500 + (i if i < days // 2 else days - i) * 4
        for sym in symbols:
            for src in (SourceName.SHARESANSAR, SourceName.MEROLAGANI):
                bars.append(
                    PriceBar(symbol=sym, business_date=d, close=float(base),
                             previous_close=float(base - 1), turnover=float(base) * 1000,
                             source=src)
                )
    pipe.storage.upsert_price_bars(bars)
    for i in range(days):
        pipe.reconcile(START + timedelta(days=i))
    return symbols


def test_market_breadth_and_movers(pipe):
    _seed_hump(pipe, days=30)
    d = START + timedelta(days=10)  # a rising day
    breadth = pipe.market_breadth(d)
    assert breadth["symbols"] == 2
    assert breadth["advancers"] + breadth["decliners"] + breadth["unchanged"] == 2
    assert breadth["avg_confidence"] == 1.0  # both sources agree
    gainers, losers = pipe.top_movers(d, top=2)
    assert isinstance(gainers, list) and isinstance(losers, list)


def test_quant_stats_rows(pipe):
    _seed_hump(pipe, days=70)
    rows = pipe.quant_stats(["AAA", "BBB"])
    assert {r["symbol"] for r in rows} == {"AAA", "BBB"}
    for r in rows:
        assert r["n"] >= 60
        assert r["annualized_vol_pct"] is not None


def test_screen_strategies_leaderboard(pipe):
    _seed_hump(pipe, days=70)
    rows = pipe.screen_strategies(["AAA", "BBB"], ["sma_cross", "macd"], min_bars=60)
    assert len(rows) == 4  # 2 symbols x 2 strategies
    sharpes = [r.sharpe for r in rows]
    assert sharpes == sorted(sharpes, reverse=True)


def test_daily_report_assembles_all_sections(pipe):
    _seed_hump(pipe, days=70)
    d = START + timedelta(days=69)
    sections, summary = pipe.daily_report(d, strategies=["sma_cross", "macd"], top=10, min_bars=60)
    for title in ("Market overview", "Top movers", "Quantitative stats"):
        assert title in sections
        assert isinstance(sections[title], str) and sections[title]
    assert any("Backtest leaderboard" in k for k in sections)
    assert summary["business_date"] == d.isoformat()
    assert summary["backtests"] >= 1
