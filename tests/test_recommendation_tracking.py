"""Forward-published research calls never become hindsight performance claims."""

import json
from datetime import date

import pytest
from freezegun import freeze_time
from test_decision_board import pipe as base_pipe

from nepse_trader.advisor.journal import record_score
from nepse_trader.advisor.outcomes import score_prediction
from nepse_trader.advisor.track_record import (
    ENGINE_VERSION,
    evaluate_recommendation,
    performance_report,
    record_recommendations,
    score_recommendations,
)
from nepse_trader.analysis.costs import CostEngine
from nepse_trader.models import (
    CorporateAction,
    CorporateActionType,
    OrderSide,
    PriceBar,
    SourceName,
)

MADE = date(2026, 11, 18)
ENTRY, SECOND, DEADLINE = date(2026, 11, 19), date(2026, 11, 22), date(2026, 11, 23)


@pytest.fixture
def pipe(tmp_path):
    yield from base_pipe.__wrapped__(tmp_path)


def board():
    return dict(
        requested_date=MADE.isoformat(),
        market_date=MADE.isoformat(),
        stale=False,
        generated_at="2026-11-18T10:00:00+00:00",
        buys={
            "day": [
                dict(
                    symbol="TEST",
                    horizon_days=3,
                    reference_price=100,
                    entry_low=99,
                    entry_high=101,
                    stop=95,
                    target=110,
                    rationale=["Original reason"],
                    fundamental_report={"eps": 10},
                    confidence={"value": 0.7, "basis": "Original evidence"},
                )
            ],
            "month": [],
        },
    )


def prediction(pipe):
    with freeze_time("2026-11-18"):
        with pipe.storage._tx() as conn:
            record_recommendations(conn, board())
    return dict(
        pipe.storage._conn.execute(
            "SELECT * FROM predictions WHERE kind=?", (ENGINE_VERSION,)
        ).fetchone()
    )


def bar(day, *, open=100, high=101, low=99, close=100):
    return PriceBar(
        symbol="TEST",
        business_date=day,
        open=open,
        high=high,
        low=low,
        close=close,
        source=SourceName.MANUAL,
    )


def test_first_publication_is_permanent_and_repeated_refresh_does_not_rewrite_it(pipe):
    original = prediction(pipe)
    changed = board()
    changed["buys"]["day"][0].update(
        target=120, confidence={"value": 0.95, "basis": "Later evidence"}
    )
    with freeze_time("2026-11-18"), pipe.storage._tx() as conn:
        record_recommendations(conn, changed)
        conn.execute("DELETE FROM decision_runs")
    current = pipe.storage._conn.execute(
        "SELECT * FROM predictions WHERE kind=?", (ENGINE_VERSION,)
    ).fetchall()
    assert len(current) == 1 and dict(current[0]) == original
    assert json.loads(current[0]["rationale"])["reasons"] == ["Original reason"]


@pytest.mark.parametrize("stale", [False, True])
def test_historical_or_stale_boards_cannot_fabricate_a_prospective_track_record(pipe, stale):
    old = board()
    old["stale"] = stale
    with freeze_time("2026-11-25"), pipe.storage._tx() as conn:
        record_recommendations(conn, old)
    assert performance_report(pipe.storage)["total"] == 0


def test_scoring_uses_actual_future_open_and_waits_for_t_plus_two(pipe):
    p = prediction(pipe)
    tape = [bar(ENTRY, high=112), bar(SECOND, high=112), bar(DEADLINE, high=108, close=105)]
    r = evaluate_recommendation(p, tape, as_of=DEADLINE)
    assert r.outcome == "EXPIRED_UP" and r.entry_price == 100 and r.hit == 0
    buy = CostEngine().compute(OrderSide.BUY, 100, 100)
    sell = CostEngine().compute(
        OrderSide.SELL, 105, 100, buy_cost_basis=buy.net_amount, holding_days=4
    )
    assert r.realized_net_pnl == sell.net_amount - buy.net_amount
    assert r.benchmark_return_pct == r.net_return_pct


@pytest.mark.parametrize(
    "last,expected,exit_price",
    [
        (bar(DEADLINE, high=112, low=94, close=105), "STOP_HIT", 95),
        (bar(DEADLINE, open=90, high=94, low=88, close=92), "STOP_HIT", 90),
        (bar(DEADLINE, high=112, close=108), "TARGET_HIT", 110),
    ],
)
def test_ambiguous_candles_gaps_and_targets_are_conservative(pipe, last, expected, exit_price):
    r = evaluate_recommendation(prediction(pipe), [bar(ENTRY), bar(SECOND), last], as_of=DEADLINE)
    assert r.outcome == expected and r.realized_exit_price == exit_price


def test_missing_intermediate_session_cannot_be_ignored_to_claim_a_target_hit(pipe):
    r = evaluate_recommendation(
        prediction(pipe), [bar(ENTRY), bar(DEADLINE, high=112)], as_of=DEADLINE
    )
    assert r.outcome == "NO_DATA" and r.hit is None and r.net_return_pct is None


def test_entry_outside_saved_zone_is_disclosed_as_unfilled(pipe):
    r = evaluate_recommendation(prediction(pipe), [bar(ENTRY, open=103, high=104)], as_of=ENTRY)
    assert r.outcome == "NOT_ENTERED" and r.hit is None and r.realized_net_pnl is None


def test_future_or_incomplete_horizon_is_not_an_outcome(pipe):
    p = prediction(pipe)
    tape = [bar(ENTRY), bar(SECOND), bar(DEADLINE, high=112)]
    assert evaluate_recommendation(p, tape, as_of=MADE).outcome == "UNRESOLVED"
    r = evaluate_recommendation(p, tape, as_of=SECOND)
    assert r.outcome == "UNRESOLVED" and r.net_return_pct is None


def test_known_corporate_action_excludes_fixed_price_prediction(pipe):
    action = CorporateAction(
        symbol="TEST",
        ex_date=SECOND,
        action_type=CorporateActionType.BONUS,
        ratio_numerator=1,
        ratio_denominator=1,
        factor=0.5,
        source=SourceName.MANUAL,
    )
    r = evaluate_recommendation(
        prediction(pipe),
        [bar(ENTRY), bar(SECOND), bar(DEADLINE)],
        as_of=DEADLINE,
        corporate_actions=[action],
    )
    assert r.outcome == "EXCLUDED" and r.net_return_pct is None


def test_existing_journal_scoring_path_persists_benchmark_metrics_without_mixing_calibration(pipe):
    p = prediction(pipe)
    r = score_prediction(
        p, [bar(ENTRY), bar(SECOND), bar(DEADLINE, high=112, close=108)], as_of=DEADLINE
    )
    record_score(pipe.storage._conn, p["prediction_id"], r)
    row = pipe.storage._conn.execute(
        "SELECT * FROM predictions WHERE prediction_id=?", (p["prediction_id"],)
    ).fetchone()
    assert row["evaluation_entry_price"] == 100 and row["evaluation_net_return"] > 0
    assert row["evaluation_benchmark_return"] < row["evaluation_net_return"]
    assert pipe.storage._conn.execute("SELECT COUNT(*) FROM calibration").fetchone()[0] == 0
    report = performance_report(pipe.storage)
    bucket = next(b for b in report["buckets"] if b["samples"])
    assert bucket["profitable_rate"] == 1 and bucket["interval_low"] < 0.7
    assert report["status"] == "collecting_evidence"


def test_small_price_gain_after_fees_is_not_counted_as_profitable(pipe):
    p = prediction(pipe)
    r = evaluate_recommendation(
        p, [bar(ENTRY), bar(SECOND), bar(DEADLINE, close=100.01)], as_of=DEADLINE
    )
    record_score(pipe.storage._conn, p["prediction_id"], r)
    assert r.outcome == "EXPIRED_UP" and r.net_return_pct < 0
    bucket = next(b for b in performance_report(pipe.storage)["buckets"] if b["samples"])
    assert bucket["profitable_rate"] == 0


def test_bounded_scoring_rotates_past_missing_data_instead_of_starving_new_calls(pipe):
    p = prediction(pipe)
    with freeze_time("2026-11-18"), pipe.storage._tx() as conn:
        newer = board()
        newer["buys"]["day"][0]["symbol"] = "OTHER"
        record_recommendations(conn, newer)
    with freeze_time("2026-11-24"):
        first = score_recommendations(pipe, completed=DEADLINE, limit=1)
        second = score_recommendations(pipe, completed=DEADLINE, limit=1)
    assert first["checked"] == second["checked"] == 1
    rows = pipe.storage._conn.execute(
        "SELECT evaluation_checked_at FROM predictions WHERE kind=?", (ENGINE_VERSION,)
    ).fetchall()
    assert all(r[0] for r in rows)
    assert p["quantity"] == 100


@pytest.mark.parametrize(
    "made,stamp,expected_entry,expected_deadline",
    [
        ("2026-11-20", "2026-11-20T10:00:00+00:00", "2026-11-22", "2026-11-24"),
        ("2026-11-18", "2026-11-18T03:00:00+00:00", "2026-11-18", "2026-11-22"),
    ],
)
def test_first_future_open_and_horizon_are_frozen_at_publication(
    pipe, made, stamp, expected_entry, expected_deadline
):
    b = board()
    b.update(requested_date=made, generated_at=stamp)
    with freeze_time(made), pipe.storage._tx() as conn:
        record_recommendations(conn, b)
    row = pipe.storage._conn.execute(
        "SELECT * FROM predictions WHERE kind=?", (ENGINE_VERSION,)
    ).fetchone()
    assert row["forecast_entry_on"] == expected_entry
    assert row["deadline"] == expected_deadline


def test_delayed_scoring_does_not_exclude_a_prediction_that_exited_before_corporate_action(pipe):
    p = prediction(pipe)
    p["deadline"] = "2026-12-17"
    action = CorporateAction(
        symbol="TEST",
        ex_date=date(2026, 11, 26),
        action_type=CorporateActionType.BONUS,
        ratio_numerator=1,
        ratio_denominator=1,
        factor=0.5,
        source=SourceName.MANUAL,
    )
    tape = [bar(ENTRY), bar(SECOND), bar(DEADLINE, low=94)]
    immediate = evaluate_recommendation(p, tape, as_of=DEADLINE, corporate_actions=[action])
    delayed = evaluate_recommendation(p, tape, as_of=date(2026, 11, 30), corporate_actions=[action])
    assert immediate.outcome == delayed.outcome == "STOP_HIT"
    assert immediate.realized_net_pnl == delayed.realized_net_pnl


def test_generic_journal_api_cannot_terminally_score_dashboard_forecasts(pipe):
    from fastapi.testclient import TestClient

    from nepse_trader.web.api import _state, app

    p = prediction(pipe)
    _state.update(storage=pipe.storage, settings=pipe.settings)
    with TestClient(app) as client:
        assert client.post("/api/journal/score", json={}).json() == []
        response = client.post("/api/journal/score", json={"prediction_id": p["prediction_id"]})
        assert response.status_code == 404 and "Refresh today" in response.json()["detail"]
        report = client.get("/api/decisions/performance").json()
        assert report["total"] == 1 and report["resolved"] == 0
        assert (
            pipe.storage._conn.execute(
                "SELECT status FROM predictions WHERE kind=?", (ENGINE_VERSION,)
            ).fetchone()[0]
            == "open"
        )
    _state.clear()
