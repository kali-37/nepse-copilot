"""Valuation support changes advice; historical risk never becomes a guarantee."""

from datetime import date, timedelta
from math import sin

import pytest
from freezegun import freeze_time
from test_decision_board import pipe as base_pipe

from nepse_trader.advisor.decision_signals import chart_states
from nepse_trader.advisor.decision_state import decision_state
from nepse_trader.advisor.decisions import build_decisions
from nepse_trader.advisor.fundamentals import assess_fundamentals
from nepse_trader.advisor.investments import investment_candidate
from nepse_trader.calendar import is_trading_day
from nepse_trader.models import FundamentalData, PriceBar, SourceName

TODAY = date(2026, 11, 20)
LAST = date(2026, 11, 19)


@pytest.fixture
def pipe(tmp_path):
    yield from base_pipe.__wrapped__(tmp_path)


def history():
    bars = []
    d = TODAY - timedelta(days=400)
    while d <= LAST:
        if is_trading_day(d):
            close = 100 + len(bars) * 0.08 + sin(len(bars) / 9) * 0.2
            bars.append(
                PriceBar(
                    symbol="BANK",
                    business_date=d,
                    open=close,
                    high=close + 1,
                    low=close - 1,
                    close=close,
                    volume=30000,
                    source=SourceName.MANUAL,
                )
            )
        d += timedelta(days=1)
    return bars


def test_quality_screen_shows_dated_net_history_without_forecast_or_reserved_budget():
    bars = history()
    state = chart_states(bars)[-1]
    report = investment_candidate(
        "BANK",
        bars,
        state,
        0.95,
        FundamentalData(symbol="BANK", eps=10, book_value=100),
        snapshot_date=LAST,
        today=TODAY,
    )
    assert report and report["historical_net_annual_return"] > 0
    assert report["max_drawdown"] < 25 and report["history_to"] == LAST.isoformat()
    assert "quantity" not in report and "estimated_net" not in report
    assert "not a future return probability" in report["confidence"]["basis"]


@pytest.mark.parametrize(
    "snapshot,age",
    [
        (None, 1),
        (FundamentalData(symbol="BANK", eps=-1, book_value=100), 1),
        (FundamentalData(symbol="BANK", eps=10, book_value=None), 1),
        (FundamentalData(symbol="BANK", eps=10, book_value=100), 91),
    ],
)
def test_missing_loss_making_or_stale_financials_cannot_be_called_lower_risk(snapshot, age):
    bars = history()
    assert (
        investment_candidate(
            "BANK",
            bars,
            chart_states(bars)[-1],
            0.95,
            snapshot,
            snapshot_date=TODAY - timedelta(days=age),
            today=TODAY,
        )
        is None
    )


def test_large_historical_drawdown_disqualifies_even_if_price_finishes_higher():
    bars = history()
    for i, b in enumerate(bars):
        b.close = 100 + min(i, 150) * 0.7 if i < 180 else 125 + (i - 180) * 0.03
        b.open = b.close
        b.high = b.close + 1
        b.low = b.close - 1
    assert bars[-1].close > bars[0].close
    assert (
        investment_candidate(
            "BANK",
            bars,
            chart_states(bars)[-1],
            0.95,
            FundamentalData(symbol="BANK", eps=10, book_value=100),
            snapshot_date=LAST,
            today=TODAY,
        )
        is None
    )


def test_fundamental_grade_is_calculated_from_current_quote_and_penalises_expensive_stock():
    data = FundamentalData(symbol="BANK", eps=10, book_value=100)
    supported = assess_fundamentals(data, quote=150, snapshot_date=LAST, today=TODAY)
    expensive = assess_fundamentals(data, quote=550, snapshot_date=LAST, today=TODAY)
    assert supported["current_pe"] == 15 and supported["rating"] == "supported"
    assert expensive["rating"] == "expensive" and expensive["multiplier"] < supported["multiplier"]


@pytest.mark.parametrize("eps,book_value", [(0, 0), (10, 100)])
def test_mutual_funds_require_nav_review_even_when_company_ratios_look_positive(eps, book_value):
    data = FundamentalData(symbol="FUND", sector="Mutual Fund", eps=eps, book_value=book_value)
    report = assess_fundamentals(data, quote=10, snapshot_date=LAST, today=TODAY)
    assert report["asset_kind"] == "mutual_fund" and report["rating"] == "fund_review"
    assert report["multiplier"] == 0 and not report["needs_refresh"]
    assert report["eps"] is None and "NAV" in report["reasons"][1]
    bars = history()
    assert investment_candidate("FUND", bars, chart_states(bars)[-1], .95, data,
        snapshot_date=LAST, today=TODAY) is None


def test_rolling_volume_and_chart_validity_recover_at_the_correct_window_boundary():
    bars = history()[-90:]
    bars[30].high = None
    for i, bar in enumerate(bars):
        bar.volume = None if i % 3 == 0 else i * 100
    states = chart_states(bars)
    assert states[79] is None  # The missing high remains in the last 50 sessions.
    assert states[80] is not None
    for i in range(80, len(bars)):
        known = [b.volume for b in bars[i - 19:i + 1] if b.volume is not None]
        assert states[i].volume_samples == len(known)
        assert states[i].average_volume == sum(known) / len(known)


def test_losing_company_is_removed_from_buys_even_when_charts_are_strong(pipe):
    with freeze_time("2026-11-20"):
        initial = build_decisions(pipe)
        symbol = initial["buys"]["day"][0]["symbol"]
        pipe.storage.upsert_fundamental(
            FundamentalData(symbol=symbol, eps=-2, book_value=200), LAST
        )
        after = build_decisions(pipe)
    assert all(p["symbol"] != symbol for group in after["buys"].values() for p in group)


def test_missing_fundamentals_are_queued_for_refresh_instead_of_silent_technical_only_buy(pipe):
    with pipe.storage._tx() as conn:
        conn.execute("DELETE FROM fundamentals")
    with freeze_time("2026-11-20"):
        report = build_decisions(pipe)
    assert report["fundamental_checks_needed"]
    assert report["buys"] == {"day": [], "month": []}


def test_fundamental_changes_invalidate_saved_advice_state(pipe):
    before = decision_state(pipe, TODAY)
    pipe.storage.upsert_fundamental(FundamentalData(symbol="AAA", eps=-1, book_value=100), LAST)
    assert decision_state(pipe, TODAY) != before


def test_fundamental_facility_reports_the_effect_on_buys_and_has_limits(pipe):
    from fastapi.testclient import TestClient

    from nepse_trader.web.api import _state, app

    _state.update(storage=pipe.storage, settings=pipe.settings)
    with freeze_time("2026-11-20"), TestClient(app) as client:
        data = client.get("/api/decisions/fundamentals/AAA").json()
        assert data["rating"] == "supported" and data["multiplier"] == 1
        assert data["eps"] == 15 and data["limitations"]
        assert client.get("/api/decisions/fundamentals/UNKNOWN").json()["rating"] == "missing"
    _state.clear()


@pytest.mark.parametrize("missing_latest", [True, False])
def test_one_volume_observation_cannot_establish_lower_risk_liquidity(missing_latest):
    bars = history()
    for bar in bars[-20:]:
        bar.volume = None
    bars[-2 if missing_latest else -1].volume = 30000
    assert (
        investment_candidate(
            "BANK",
            bars,
            chart_states(bars)[-1],
            0.95,
            FundamentalData(symbol="BANK", eps=10, book_value=100),
            snapshot_date=LAST,
            today=TODAY,
        )
        is None
    )
