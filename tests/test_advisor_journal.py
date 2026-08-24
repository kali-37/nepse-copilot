"""Focused tests for the prediction journal lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest

from nepse_trader.advisor.confidence import market
from nepse_trader.advisor.journal import (
    JournalError,
    distill_lesson,
    get_prediction,
    journal_history,
    log_prediction,
    record_review,
    record_score,
    retire_prediction,
    review_queue,
)
from nepse_trader.advisor.plan import PlanCard
from nepse_trader.rag.index import DocumentIndex
from nepse_trader.storage.db import Storage


@dataclass
class _Result:
    outcome: str = "TARGET_HIT"
    hit: int | None = 1
    resolved_on: date | None = date(2026, 8, 20)
    realized_exit_price: float | None = 125.0
    realized_net_pnl: float | None = 200.0
    mfe: float | None = 25.0
    mae: float | None = 4.0
    bars_seen: int = 6


@pytest.fixture
def storage(tmp_path):
    value = Storage(tmp_path / "journal.db")
    yield value
    value.close()


@pytest.fixture
def card() -> PlanCard:
    return PlanCard(
        symbol="NABIL",
        action="accumulate",
        reference_price=100.0,
        entry_low=99.0,
        entry_high=101.0,
        stop=90.0,
        targets=[120.0, 135.0],
        quantity=10,
        horizon_days=10,
        earliest_sell_date=date(2026, 8, 12),
        conviction=4,
        rationale="two strategy votes",
        gross_pnl=Decimal("220.00"),
        net_pnl=Decimal("180.00"),
        entry_cost=Decimal("4.00"),
        exit_cost=Decimal("6.00"),
        capital_gains_tax=Decimal("30.00"),
    )


def _logged(storage, card):
    return log_prediction(
        storage._conn,
        card,
        made_on=date(2026, 8, 3),
        horizon="week",
        confidence=market(0.7, "measured history"),
    )


def test_log_captures_expected_values_and_starts_open(storage, card):
    prediction = _logged(storage, card)
    row = storage._conn.execute(
        "SELECT * FROM predictions WHERE prediction_id=?", (prediction.prediction_id,)
    ).fetchone()
    assert prediction.status == "open"
    assert row["symbol"] == "NABIL"
    assert row["target_1"] == 120.0
    assert row["expected_net_pnl"] == 180.0
    assert row["confidence"] == 0.7
    assert row["deadline"] > row["made_on"]


def test_lifecycle_transitions_are_validated(storage, card):
    prediction = _logged(storage, card)
    with pytest.raises(JournalError, match="only scored"):
        record_review(storage._conn, prediction.prediction_id, "too early")
    with pytest.raises(JournalError, match="only reviewed"):
        distill_lesson(storage._conn, prediction.prediction_id, "too early")
    with pytest.raises(JournalError, match="only reviewed"):
        retire_prediction(storage._conn, prediction.prediction_id)


def test_scored_reviewed_distilled_and_retired_rows_are_auditable(storage, card):
    prediction = _logged(storage, card)
    scored = record_score(storage._conn, prediction.prediction_id, _Result())
    assert scored.status == "scored"
    assert scored.outcome == "TARGET_HIT"
    assert scored.hit == 1
    assert review_queue(storage._conn)[0]["prediction_id"] == prediction.prediction_id

    reviewed = record_review(storage._conn, prediction.prediction_id, "Target hit after breakout.")
    assert reviewed.status == "reviewed"
    with pytest.raises(JournalError, match="before a lesson"):
        retire_prediction(storage._conn, prediction.prediction_id)

    lesson_id = distill_lesson(
        storage._conn,
        prediction.prediction_id,
        "For NABIL, wait for volume confirmation before entering a breakout.",
    )
    lesson = storage._conn.execute(
        "SELECT * FROM prediction_lessons WHERE lesson_id=?", (lesson_id,)
    ).fetchone()
    document = DocumentIndex(storage._conn).get(lesson_id)
    assert lesson["subject"] == "NABIL"
    assert document is not None
    assert "volume confirmation" in document.body

    retired = retire_prediction(storage._conn, prediction.prediction_id)
    assert retired.status == "retired"
    assert review_queue(storage._conn) == []
    preserved = get_prediction(storage._conn, prediction.prediction_id)
    assert preserved.hit == 1
    assert journal_history(storage._conn)[0]["status"] == "retired"


def test_unresolved_scores_stay_open_and_never_enter_calibration(storage, card):
    prediction = _logged(storage, card)
    record_score(
        storage._conn,
        prediction.prediction_id,
        _Result(outcome="UNRESOLVED", hit=None, resolved_on=None, realized_net_pnl=None),
    )
    assert get_prediction(storage._conn, prediction.prediction_id).status == "open"
    assert storage._conn.execute("SELECT * FROM calibration").fetchone() is None


def test_only_open_predictions_can_be_scored(storage, card):
    prediction = _logged(storage, card)
    record_score(storage._conn, prediction.prediction_id, _Result())
    with pytest.raises(JournalError, match="only open"):
        record_score(storage._conn, prediction.prediction_id, _Result())
