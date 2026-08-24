from __future__ import annotations

from datetime import date
from decimal import Decimal

from nepse_trader.advisor.auction import (
    BID,
    SKIP,
    auction_advice_history,
    build_auction_advice,
    save_auction_advice,
)
from nepse_trader.analysis.costs import CostEngine
from nepse_trader.models import OrderSide


def test_auction_advice_is_fee_aware_and_can_skip() -> None:
    advice = build_auction_advice(
        "NABIL",
        auction_date=date(2026, 8, 23),
        units=100,
        min_bid_price=100,
        market_price=100,
        expected_exit_price=100,
        horizon_days=10,
    )
    assert advice.verdict == SKIP
    assert advice.recommended_bid >= advice.min_bid_price
    assert advice.expected_net_pnl <= Decimal("0")


def test_auction_net_pnl_matches_cost_engine() -> None:
    advice = build_auction_advice(
        "NABIL",
        auction_date=date(2026, 8, 23),
        units=100,
        min_bid_price=100,
        market_price=100,
        expected_exit_price=130,
        horizon_days=10,
    )
    engine = CostEngine()
    buy = engine.compute(OrderSide.BUY, advice.recommended_bid, advice.quantity)
    sell = engine.compute(
        OrderSide.SELL,
        advice.expected_exit_price,
        advice.quantity,
        buy_cost_basis=buy.net_amount,
        holding_days=advice.horizon_days,
    )
    assert advice.expected_net_pnl == sell.net_amount - buy.net_amount
    assert advice.walk_away_price >= advice.recommended_bid
    assert advice.breakeven_price > advice.recommended_bid


def test_auction_settlement_is_a_trading_date() -> None:
    advice = build_auction_advice(
        "NABIL",
        auction_date=date(2026, 8, 20),  # Thursday
        units=10,
        min_bid_price=100,
        market_price=120,
        expected_exit_price=140,
        horizon_days=1,
    )
    assert advice.earliest_sell_date > advice.auction_date
    assert advice.earliest_sell_date.weekday() not in {4, 5}


def test_auction_advice_can_be_saved_and_listed_without_placing_a_bid(tmp_path) -> None:
    import sqlite3

    from nepse_trader.storage.migrations import run_pending

    conn = sqlite3.connect(tmp_path / "auction.db")
    conn.row_factory = sqlite3.Row
    run_pending(conn)
    advice = build_auction_advice(
        "NABIL",
        auction_date=date(2026, 8, 23),
        units=100,
        min_bid_price=100,
        market_price=100,
        expected_exit_price=130,
    )
    first = save_auction_advice(conn, advice)
    conn.commit()
    second = save_auction_advice(conn, advice)
    conn.commit()
    assert first == second
    rows = auction_advice_history(conn, symbol="NABIL")
    assert len(rows) == 1
    assert rows[0]["verdict"] == BID
