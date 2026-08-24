from __future__ import annotations

import sqlite3
from datetime import date

from nepse_trader.advisor.outcomes import (
    EXPIRED_UP,
    NO_DATA,
    STOP_HIT,
    TARGET_HIT,
    UNRESOLVED,
    persist_score,
    score_prediction,
)
from nepse_trader.analysis.costs import CostEngine
from nepse_trader.models import OrderSide, PriceBar


def _bar(day: date, *, high: float, low: float, close: float) -> PriceBar:
    return PriceBar(
        symbol="NABIL",
        business_date=day,
        high=high,
        low=low,
        close=close,
        source="manual",
    )


def _prediction(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "prediction_id": "p-1",
        "symbol": "NABIL",
        "made_on": date(2026, 8, 23),
        "deadline": date(2026, 8, 27),
        "horizon_days": 3,
        "reference_price": 100.0,
        "entry_high": 100.0,
        "stop": 95.0,
        "target_1": 110.0,
        "quantity": 100,
    }
    value.update(overrides)
    return value


def test_stop_is_checked_before_target_when_one_bar_spans_both() -> None:
    result = score_prediction(
        _prediction(),
        [_bar(date(2026, 8, 24), high=112, low=94, close=100)],
    )
    assert result.outcome == STOP_HIT
    assert result.hit == 0
    assert result.realized_exit_price == 95.0


def test_target_hit_is_the_only_hit() -> None:
    result = score_prediction(
        _prediction(),
        [_bar(date(2026, 8, 24), high=111, low=99, close=108)],
    )
    assert result.outcome == TARGET_HIT
    assert result.hit == 1
    assert result.realized_net_pnl is not None
    buy = CostEngine().compute(OrderSide.BUY, 100, 100)
    sell = CostEngine().compute(
        OrderSide.SELL, 110, 100, buy_cost_basis=buy.net_amount, holding_days=1
    )
    assert result.realized_net_pnl == sell.net_amount - buy.net_amount


def test_expired_up_is_not_a_hit() -> None:
    result = score_prediction(
        _prediction(),
        [
            _bar(date(2026, 8, 24), high=104, low=99, close=103),
            _bar(date(2026, 8, 27), high=108, low=102, close=106),
        ],
    )
    assert result.outcome == EXPIRED_UP
    assert result.hit == 0


def test_no_data_and_pre_deadline_data_are_distinguished() -> None:
    assert score_prediction(_prediction(), []).outcome == NO_DATA
    result = score_prediction(
        _prediction(deadline=date(2026, 9, 1)),
        [_bar(date(2026, 8, 24), high=104, low=99, close=103)],
    )
    assert result.outcome == UNRESOLVED
    assert result.hit is None


def test_other_symbol_bars_do_not_resolve_this_prediction() -> None:
    result = score_prediction(
        _prediction(deadline=date(2026, 9, 1)),
        [
            _bar(date(2026, 8, 24), high=104, low=99, close=103),
            PriceBar(
                symbol="NLIC",
                business_date=date(2026, 9, 2),
                high=120,
                low=100,
                close=110,
                source="manual",
            ),
        ],
    )
    assert result.outcome == UNRESOLVED
    assert result.hit is None


def test_result_is_json_friendly() -> None:
    result = score_prediction(_prediction(), [])
    payload = result.as_dict()
    assert payload["prediction_id"] == "p-1"
    assert payload["outcome"] == NO_DATA


def test_unresolved_and_no_data_are_not_marked_scored() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """CREATE TABLE predictions (
            prediction_id TEXT PRIMARY KEY, outcome TEXT, resolved_on TEXT,
            realized_exit_price REAL, realized_net_pnl REAL, mfe REAL, mae REAL,
            hit INTEGER, bars_seen INTEGER, status TEXT, scored_at TEXT
        )"""
    )
    conn.executemany(
        "INSERT INTO predictions (prediction_id, status) VALUES (?, 'open')",
        [("p-1",), ("p-2",)],
    )

    unresolved = score_prediction(
        _prediction(prediction_id="p-1", deadline=date(2026, 9, 1)),
        [_bar(date(2026, 8, 24), high=104, low=99, close=103)],
    )
    no_data = score_prediction(_prediction(prediction_id="p-2"), [])
    assert persist_score(conn, unresolved)
    assert persist_score(conn, no_data)

    rows = conn.execute(
        "SELECT prediction_id, status, hit FROM predictions ORDER BY prediction_id"
    ).fetchall()
    assert rows == [("p-1", "open", None), ("p-2", "open", None)]
