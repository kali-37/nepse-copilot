"""Focused tests for nested, disjoint dose prescriptions."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from nepse_trader.advisor.confidence import market
from nepse_trader.advisor.doses import (
    DOSE_ALLOCATION,
    DOSE_HORIZONS,
    DoseError,
    DoseReport,
    build_dose_run,
    build_doses,
    latest_dose_run,
    partition_cards,
    render_doses,
    save_doses,
)
from nepse_trader.advisor.plan import PlanCard
from nepse_trader.storage.db import Storage


def _card(symbol: str, horizon_days: int, pnl: str) -> PlanCard:
    return PlanCard(
        symbol=symbol,
        action="accumulate",
        reference_price=100.0,
        entry_low=99.0,
        entry_high=101.0,
        stop=90.0,
        targets=[120.0],
        quantity=10,
        horizon_days=horizon_days,
        earliest_sell_date=date(2026, 8, 20),
        conviction=4,
        rationale="test",
        gross_pnl=Decimal(pnl) + Decimal("20"),
        net_pnl=Decimal(pnl),
        entry_cost=Decimal("4"),
        exit_cost=Decimal("6"),
        capital_gains_tax=Decimal("10"),
    )


@pytest.fixture
def cards():
    return [
        _card("DAY", 3, "10"),
        _card("WEEK", 10, "20"),
        _card("MONTH", 22, "30"),
        _card("YEAR", 250, "40"),
    ]


def test_constants_and_card_partition_are_exact(cards):
    assert DOSE_HORIZONS == {"day": 3, "week": 10, "month": 22, "year": 250}
    assert sum(DOSE_ALLOCATION.values()) <= 1.0
    groups = partition_cards(cards)
    assert [card.symbol for card in groups["day"]] == ["DAY"]
    assert [card.symbol for card in groups["week"]] == ["WEEK"]
    assert [card.symbol for card in groups["month"]] == ["MONTH"]
    assert [card.symbol for card in groups["year"]] == ["YEAR"]
    assert {id(card) for cards_ in groups.values() for card in cards_} == {id(card) for card in cards}


def test_doses_are_disjoint_have_monotonic_confidence_and_honest_headline(cards):
    result = build_dose_run(
        cards,
        capital=100_000,
        run_date=date(2026, 8, 3),
        confidence=market(0.8, "history"),
    )
    assert len(result.doses) == 4
    assert sum(d.allocation_pct for d in result.doses) <= 1.0
    assert [d.horizon for d in result.doses] == list(DOSE_HORIZONS)
    assert [card.symbol for card in result.cards] == [card.symbol for card in cards]
    assert sum(d.expected_net_pnl for d in result.doses) == result.expected_net_pnl == Decimal("100.00")
    values = [dose.confidence.value for dose in result.doses]
    assert values == sorted(values, reverse=True)


def test_empty_horizons_are_rendered_and_prohibited_claims_are_removed(cards):
    result = build_dose_run(
        cards[:1],
        capital=10_000,
        run_date=date(2026, 8, 3),
        readings={"day": "This is guaranteed and risk-free, for sure."},
    )
    text = render_doses(result).lower()
    for forbidden in ("guarantee", "guaranteed", "sure", "risk-free"):
        assert forbidden not in text
    assert all(dose.horizon.upper() in render_doses(result) for dose in result.doses)


def test_invalid_allocations_are_rejected(cards):
    with pytest.raises(DoseError, match="maximum is 1.0"):
        build_dose_run(cards, capital=100, allocations={name: 0.3 for name in DOSE_HORIZONS})
    with pytest.raises(DoseError, match="exactly"):
        build_dose_run(cards, capital=100, allocations={"day": 1.0})


def test_persistence_writes_exactly_one_row_per_horizon(tmp_path, cards):
    storage = Storage(tmp_path / "doses.db")
    try:
        result = build_dose_run(cards, capital=100_000, run_date=date(2026, 8, 3))
        dose_run_id = save_doses(storage._conn, result)
        rows = storage._conn.execute(
            "SELECT * FROM doses WHERE dose_run_id=? ORDER BY id", (dose_run_id,)
        ).fetchall()
        assert len(rows) == 4
        assert {row["horizon"] for row in rows} == set(DOSE_HORIZONS)
        assert latest_dose_run(storage._conn)["id"] == dose_run_id
        with pytest.raises(sqlite3.IntegrityError):
            storage._conn.execute(
                "INSERT INTO doses (dose_run_id,horizon) VALUES (?,?)", (dose_run_id, "day")
            )
    finally:
        storage.close()


def test_budgeted_builder_uses_all_in_costs_and_omits_weaker_cards():
    # One day-dose card costs NPR 1,014 including the buy-side fee.  The
    # allocation is deliberately NPR 1,100, so only one of the two cards fits.
    strong = _card("STRONG", 3, "30")
    weak = _card("WEAK", 3, "5")
    strong.confidence = market(0.8, "history")
    weak.confidence = market(0.4, "history")

    report = build_doses(
        cards=[weak, strong],
        equity=11_000,
        run_date=date(2026, 8, 3),
    )

    day = report.by_period("DAY")
    assert isinstance(report, DoseReport)
    assert day is not None
    assert day.symbols == ["STRONG"]
    assert report.total_capital_deployed == Decimal("1014.00")
    assert report.total_capital_deployed <= report.equity
    assert any("WEAK" in warning for warning in report.warnings)


def test_budgeted_builder_preserves_trading_windows_and_sell_guidance():
    card = _card("NABIL", 3, "10")
    queue = [{
        "symbol": "NABIL",
        "quantity": 10,
        "reason": "target reached",
        "earliest_sell_date": date(2026, 8, 10),
    }]
    report = build_doses(
        cards=[card],
        equity=20_000,
        run_date=date(2026, 8, 3),
        sell_queue=queue,
    )

    assert report.by_period("MONTH") is not None
    assert report.by_period("DAY").window_ends == date(2026, 8, 6)
    assert any("NABIL" in line for line in report.by_period("DAY").guidance)
    text = render_doses(report).lower()
    assert all(word not in text for word in ("guarantee", "guaranteed", "sure", "risk-free"))


def test_budgeted_builder_derives_missing_entry_cost_from_cost_engine():
    card = _card("NOFEE", 3, "10")
    card.entry_cost = None
    report = build_doses(cards=[card], equity=20_000, run_date=date(2026, 8, 3))
    assert report.total_capital_deployed > Decimal("1010.00")
