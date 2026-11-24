"""A purchase keeps its dated thesis; daily noise is not a monthly exit."""

import json
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from freezegun import freeze_time
from test_decision_board import pipe as base_pipe

from nepse_trader.advisor.decision_signals import ChartState
from nepse_trader.advisor.decisions import publish_decisions
from nepse_trader.advisor.holding_advice import holding_advice, record_advice_history
from nepse_trader.advisor.positions import owned_positions, record_trade, set_position_plan
from nepse_trader.calendar import add_trading_days
from nepse_trader.models import PriceBar, SourceName


@pytest.fixture
def pipe(tmp_path):
    yield from base_pipe.__wrapped__(tmp_path)


ENTRY = date(2026, 11, 18)
WEAK = ChartState(100, 1, 80, 110, 120, -0.04, 0.3, 30000)
STRONG = ChartState(100, 1, 55, 99, 95, 0.01, 1.2, 30000)


def purchase(pipe, *, horizon=22, origin=None):
    with freeze_time("2026-11-20"):
        record_trade(
            pipe,
            symbol="DOLTI",
            side="buy",
            quantity=100,
            price=Decimal(100),
            bought_on=ENTRY,
            stop=90,
            target=150,
            horizon_days=horizon,
            origin_decision_id=origin,
            origin_horizon="month" if origin else None,
        )
    return next(p for p in owned_positions(pipe) if p["symbol"] == "DOLTI")


def evaluate(pipe, position, days, states=None, quote=100):
    bars = [
        PriceBar(
            symbol="DOLTI",
            business_date=d,
            close=quote,
            high=quote + 1,
            low=quote - 1,
            source=SourceName.MANUAL,
        )
        for d in days
    ]
    return holding_advice(
        pipe,
        position,
        bars,
        states or [WEAK] * len(days),
        quote=quote,
        quality=0.95,
        expected=days[-1],
        completed=days[-1],
        today=days[-1],
    )


def test_monthly_purchase_does_not_reverse_on_one_weak_day_or_repeated_refresh(pipe):
    position = purchase(pipe)
    for _ in range(10):
        advice = evaluate(pipe, position, [date(2026, 11, 19)])
        assert advice["action"] == "hold" and advice["trend_confirmations"] == 1
        assert advice["confirmations_required"] == 3 and "1/3" in advice["reason"]
        assert advice["review_on"] == add_trading_days(ENTRY, 22).isoformat()


def test_confirming_unknown_mirror_purchase_date_restores_review_deadline(pipe, monkeypatch):
    monkeypatch.setattr(
        "nepse_trader.advisor.positions.stored_holdings",
        lambda _: [SimpleNamespace(symbol="DOLTI", current_balance=100, cost_basis=None)],
    )
    with freeze_time("2026-11-20"):
        set_position_plan(pipe, symbol="DOLTI", quantity=100, stop=90, target=150)
        original = json.loads(owned_positions(pipe)[0]["entry_thesis"])
        assert original["opened_on"] is None
        set_position_plan(
            pipe, symbol="DOLTI", quantity=100, stop=90, target=150, bought_on=ENTRY
        )
    position = owned_positions(pipe)[0]
    assert json.loads(position["entry_thesis"]) == original
    advice = evaluate(pipe, position, [date(2026, 11, 23)])
    assert advice["review_on"] == add_trading_days(ENTRY, 22).isoformat()
    assert advice["earliest_sell_date"] == "2026-11-22"
    assert advice["trend_confirmations"] == 1


def test_three_completed_weak_sessions_trigger_named_monthly_exit(pipe):
    position = purchase(pipe)
    advice = evaluate(pipe, position, [date(2026, 11, 19), date(2026, 11, 22), date(2026, 11, 23)])
    assert advice["action"] == "sell" and advice["trigger_code"] == "confirmed_weakness"
    assert advice["settled"] and advice["trend_confirmations"] == 3
    assert "3 consecutive completed sessions" in advice["reason"]


def test_live_weak_candle_does_not_count_as_completed_confirmation(pipe):
    position = purchase(pipe)
    days = [date(2026, 11, 19), date(2026, 11, 22), date(2026, 11, 23)]
    bars = [
        PriceBar(symbol="DOLTI", business_date=d, close=100, source=SourceName.MANUAL) for d in days
    ]
    advice = holding_advice(
        pipe,
        position,
        bars,
        [WEAK] * 3,
        quote=100,
        quality=0.95,
        expected=days[-1],
        completed=days[-2],
        today=days[-1],
    )
    assert advice["action"] == "hold" and advice["trend_confirmations"] == 2


def test_hard_stop_overrides_monthly_patience_but_waits_for_settlement(pipe):
    advice = evaluate(pipe, purchase(pipe), [date(2026, 11, 19)], quote=89)
    assert advice["action"] == "sell" and advice["trigger_code"] == "stop_hit"
    assert advice["exit_status"] == "waiting_settlement"
    assert advice["earliest_sell_date"] == "2026-11-22"
    assert "90.00" in advice["reason"]


def test_missing_completed_session_and_recovering_trend_break_confirmations(pipe):
    p = purchase(pipe)
    assert evaluate(pipe, p, [date(2026, 11, 19), date(2026, 11, 23)])["trend_confirmations"] == 1
    days = [date(2026, 11, 19), date(2026, 11, 22), date(2026, 11, 23)]
    advice = evaluate(pipe, p, days, [WEAK, STRONG, WEAK])
    assert advice["action"] == "hold" and advice["trend_confirmations"] == 1


def test_long_term_plan_requires_more_confirmation_than_daily_plan(pipe):
    long_term = purchase(pipe, horizon=252)
    days = [date(2026, 11, 19), date(2026, 11, 22), date(2026, 11, 23)]
    assert evaluate(pipe, long_term, days)["action"] == "hold"
    assert evaluate(pipe, long_term, days)["confirmations_required"] == 5


def test_original_rationale_survives_run_pruning_topup_and_partial_sale(pipe):
    original = {
        "id": "dated-entry",
        "requested_date": ENTRY.isoformat(),
        "market_date": ENTRY.isoformat(),
        "buys": {
            "month": [
                {
                    "symbol": "DOLTI",
                    "horizon_days": 22,
                    "rationale": ["Monthly trend supported the entry."],
                    "confidence": {"value": 0.72, "basis": "Completed comparable outcomes."},
                }
            ]
        },
    }
    with pipe.storage._tx() as conn:
        conn.execute(
            "INSERT INTO decision_runs(id,generated_at,payload) VALUES(?,?,?)",
            ("dated-entry", "2026-11-18", json.dumps(original)),
        )
    p = purchase(pipe, origin="dated-entry")
    thesis = json.loads(p["entry_thesis"])
    assert (
        thesis["rationale"] == ["Monthly trend supported the entry."]
        and thesis["confidence"]["value"] == 0.72
    )
    with pipe.storage._tx() as conn:
        conn.execute("DELETE FROM decision_runs")
    with freeze_time("2026-11-23"):
        record_trade(
            pipe,
            symbol="DOLTI",
            side="buy",
            quantity=10,
            price=Decimal(105),
            bought_on=date(2026, 11, 23),
            horizon_days=3,
        )
        p = next(p for p in owned_positions(pipe) if p["symbol"] == "DOLTI")
        assert p["horizon_days"] == 22 and p["stop"] == 90 and p["target"] == 150
        assert json.loads(p["entry_thesis"]) == thesis
        record_trade(
            pipe,
            symbol="DOLTI",
            side="sell",
            quantity=10,
            price=Decimal(110),
            bought_on=date(2026, 11, 23),
        )
        assert json.loads(owned_positions(pipe)[0]["entry_thesis"]) == thesis


def test_later_recommendation_is_not_used_as_historical_buy_reason(pipe):
    board = {
        "requested_date": "2026-11-20",
        "market_date": "2026-11-19",
        "buys": {
            "month": [
                {
                    "symbol": "DOLTI",
                    "horizon_days": 22,
                    "rationale": ["Later evidence."],
                    "confidence": {"value": 0.8},
                }
            ]
        },
    }
    with pipe.storage._tx() as conn:
        conn.execute(
            "INSERT INTO decision_runs(id,generated_at,payload) VALUES(?,?,?)",
            ("late", "now", json.dumps(board)),
        )
    thesis = json.loads(purchase(pipe, origin="late")["entry_thesis"])
    assert thesis["confidence"] is None and thesis["origin"] is None
    assert "after the purchase" in thesis["rationale"][0]


def test_exit_is_remembered_until_explicit_plan_review_and_events_do_not_duplicate(pipe):
    p = purchase(pipe)
    day = date(2026, 11, 19)
    advice = evaluate(pipe, p, [day], quote=89)
    board = {
        "holdings": [{"symbol": "DOLTI", **advice}],
        "market_date": day.isoformat(),
        "generated_at": "2026-11-19T15:00:00Z",
    }
    for _ in range(4):
        with pipe.storage._tx() as conn:
            record_advice_history(conn, board)
    assert (
        pipe.storage._conn.execute("SELECT COUNT(*) FROM holding_advice_events").fetchone()[0] == 1
    )
    p = owned_positions(pipe)[0]
    advice = evaluate(pipe, p, [day, date(2026, 11, 22)], [STRONG, STRONG])
    assert advice["action"] == "sell" and "confirmed on 2026-11-19" in advice["reason"]
    with freeze_time("2026-11-22"):
        set_position_plan(pipe, symbol="DOLTI", quantity=100, stop=90, target=150, bought_on=ENTRY)
    new = owned_positions(pipe)[0]
    assert evaluate(pipe, new, [date(2026, 11, 22)], [STRONG])["action"] == "hold"


def test_closed_position_has_reentry_cooldown_instead_of_immediate_rebuy(pipe):
    with freeze_time("2026-11-20"):
        record_trade(
            pipe, symbol="AAA", side="buy", quantity=10, price=Decimal(100), bought_on=ENTRY
        )
        record_trade(
            pipe,
            symbol="AAA",
            side="sell",
            quantity=10,
            price=Decimal(200),
            bought_on=date(2026, 11, 19),
        )
        board = publish_decisions(pipe)
    assert any(p["symbol"] == "AAA" for p in board["recent_exits"])
    assert all(p["symbol"] != "AAA" for group in board["buys"].values() for p in group)


def test_book_value_deterioration_explains_the_failing_financial_condition(pipe):
    from nepse_trader.advisor.fundamentals import assess_fundamentals
    from nepse_trader.models import FundamentalData

    p = purchase(pipe)
    day = date(2026, 11, 22)
    bar = PriceBar(symbol="DOLTI", business_date=day, close=100, source=SourceName.MANUAL)
    assessment = assess_fundamentals(
        FundamentalData(symbol="DOLTI", eps=10, book_value=-1),
        quote=100,
        snapshot_date=day,
        today=day,
    )
    advice = holding_advice(
        pipe,
        p,
        [bar],
        [STRONG],
        quote=100,
        quality=0.95,
        expected=day,
        completed=day,
        today=day,
        fundamental_report=assessment,
    )
    assert advice["action"] == "review" and "book value -1.00" in advice["reason"]


def test_changed_holding_period_keeps_source_reason_with_original_confidence_horizon(pipe):
    from nepse_trader.advisor.entry_plan import entry_plan

    board = {
        "requested_date": ENTRY.isoformat(),
        "market_date": ENTRY.isoformat(),
        "buys": {
            "month": [
                {
                    "symbol": "DOLTI",
                    "horizon_days": 22,
                    "rationale": ["Original monthly setup."],
                    "confidence": {"value": 0.72},
                }
            ]
        },
    }
    with pipe.storage._tx() as conn:
        conn.execute(
            "INSERT INTO decision_runs(id,generated_at,payload) VALUES(?,?,?)",
            ("original", "now", json.dumps(board)),
        )
    entry = entry_plan(
        pipe.storage,
        symbol="DOLTI",
        quantity=10,
        price=100,
        bought_on=ENTRY,
        stop=90,
        target=150,
        horizon_days=3,
        origin_decision_id="original",
        origin_horizon="month",
    )
    assert entry["rationale"][0] == "Original monthly setup."
    assert entry["confidence_horizon_days"] == 22 and entry["horizon_days"] == 3
    assert "you selected a 3-session" in entry["rationale"][1]


def test_expensive_fundamentals_lower_holding_evidence_and_are_explained(pipe):
    from nepse_trader.advisor.fundamentals import assess_fundamentals
    from nepse_trader.models import FundamentalData

    p = purchase(pipe)
    day = date(2026, 11, 22)
    bar = PriceBar(symbol="DOLTI", business_date=day, close=100, source=SourceName.MANUAL)
    common = dict(quote=100, quality=0.95, expected=day, completed=day, today=day)
    good = assess_fundamentals(
        FundamentalData(symbol="DOLTI", eps=10, book_value=100),
        quote=100,
        snapshot_date=day,
        today=day,
    )
    pricey = assess_fundamentals(
        FundamentalData(symbol="DOLTI", eps=1, book_value=10),
        quote=100,
        snapshot_date=day,
        today=day,
    )
    supported = holding_advice(pipe, p, [bar], [STRONG], fundamental_report=good, **common)
    expensive = holding_advice(pipe, p, [bar], [STRONG], fundamental_report=pricey, **common)
    assert expensive["action"] == "hold"
    assert expensive["confidence"]["value"] < supported["confidence"]["value"]
    assert "valuation raises caution" in expensive["reason"]
