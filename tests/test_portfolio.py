"""Tests for the paper-trading portfolio ledger (no network).

These exercise the WAC accounting, fee/CGT cash impacts, FIFO holding-period
selection, validation edge cases, and the duck-typed storage hook. All cost math
is delegated to the real CostEngine loaded from config/cost_model.yaml, so the
assertions recompute expected values from CostEngine rather than hard-coding
brittle constants.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from nepse_trader.analysis.costs import CostEngine
from nepse_trader.models import OrderSide, PaperTrade, Position
from nepse_trader.trading.portfolio import PaperPortfolio


@pytest.fixture
def engine() -> CostEngine:
    return CostEngine()


class _RecordingStorage:
    """Duck-typed storage stub capturing persisted trades."""

    def __init__(self) -> None:
        self.recorded: list[PaperTrade] = []

    def insert_paper_trade(self, trade: PaperTrade) -> None:
        self.recorded.append(trade)


# --------------------------------------------------------------------------- buy
def test_buy_reduces_cash_by_gross_plus_fees_and_sets_wac(engine: CostEngine) -> None:
    pf = PaperPortfolio(initial_cash=100_000.0, cost_engine=engine)
    bd = engine.compute(OrderSide.BUY, 500.0, 100)

    trade = pf.buy("nabil", 500.0, 100, date(2024, 1, 10))

    assert isinstance(trade, PaperTrade)
    assert trade.side is OrderSide.BUY
    # symbol auto-uppercased by the ledger and the model.
    assert trade.symbol == "NABIL"
    # Cash drops by exactly gross + all buy-side fees (= net_amount).
    assert pf.cash == Decimal("100000.00") - bd.net_amount
    assert bd.net_amount == bd.gross_amount + bd.total_fees

    pos = pf.positions["NABIL"]
    assert pos.quantity == 100
    # avg_cost is the per-share effective buy cost INCLUDING fees (2dp).
    assert pos.avg_cost == engine.effective_buy_cost_per_share(500.0, 100)


def test_buy_weighted_average_cost_across_two_buys(engine: CostEngine) -> None:
    pf = PaperPortfolio(initial_cash=1_000_000.0, cost_engine=engine)

    pf.buy("HDL", 100.0, 100, date(2024, 1, 1))
    pf.buy("HDL", 200.0, 100, date(2024, 2, 1))

    pos = pf.positions["HDL"]
    assert pos.quantity == 200
    # Average cost is display-rounded; inventory retains the exact paid basis.
    assert pos.avg_cost == Decimal("150.81")
    assert pos.cost_basis == sum(trade.net_amount for trade in pf.trades)


def test_buy_insufficient_funds_raises(engine: CostEngine) -> None:
    pf = PaperPortfolio(initial_cash=1_000.0, cost_engine=engine)
    with pytest.raises(ValueError, match="insufficient funds"):
        pf.buy("NABIL", 500.0, 100, date(2024, 1, 10))
    # Nothing mutated on failure.
    assert pf.cash == 1_000.0
    assert pf.positions == {}
    assert pf.trades == []


# -------------------------------------------------------------------------- sell
def test_oversell_raises(engine: CostEngine) -> None:
    pf = PaperPortfolio(initial_cash=100_000.0, cost_engine=engine)
    pf.buy("NABIL", 500.0, 10, date(2024, 1, 10))
    with pytest.raises(ValueError, match="only 10 held"):
        pf.sell("NABIL", 510.0, 11, date(2024, 1, 20))


def test_sell_not_held_raises(engine: CostEngine) -> None:
    pf = PaperPortfolio(initial_cash=100_000.0, cost_engine=engine)
    with pytest.raises(ValueError, match="only 0 held"):
        pf.sell("GHOST", 100.0, 1, date(2024, 1, 1))


def test_buy_then_sell_higher_realized_pnl_positive_after_fees_and_cgt(
    engine: CostEngine,
) -> None:
    pf = PaperPortfolio(initial_cash=100_000.0, cost_engine=engine)
    pf.buy("NABIL", 500.0, 100, date(2024, 1, 10))
    cash_after_buy = pf.cash

    trade = pf.sell("NABIL", 650.0, 100, date(2024, 6, 10))
    # CGT must have been applied on a real gain.
    assert trade.cgt > 0
    # Cash increases by the sell net_amount (proceeds - fees - CGT).
    assert pf.cash > cash_after_buy
    assert pf.realized_pnl > 0
    # Fully exited -> position popped.
    assert "NABIL" not in pf.positions
    assert pf.holdings() == []


def test_sell_at_loss_has_no_cgt_and_negative_pnl(engine: CostEngine) -> None:
    pf = PaperPortfolio(initial_cash=100_000.0, cost_engine=engine)
    pf.buy("NABIL", 500.0, 100, date(2024, 1, 10))
    trade = pf.sell("NABIL", 400.0, 100, date(2024, 2, 10))
    assert trade.cgt == Decimal("0.00")
    assert pf.realized_pnl < 0


# ------------------------------------------------------------ FIFO holding period
def test_fifo_partial_sell_uses_oldest_lot_for_long_term_cgt(engine: CostEngine) -> None:
    pf = PaperPortfolio(initial_cash=1_000_000.0, cost_engine=engine)
    # Two buys on very different dates; the OLDEST lot is > 365 days before sale.
    pf.buy("SCB", 100.0, 100, date(2022, 1, 1))  # oldest lot
    pf.buy("SCB", 100.0, 100, date(2024, 1, 1))
    sell_date = date(2024, 3, 1)

    # Partial sell of 50 shares consumes only the oldest (2022) lot -> long-term.
    oldest_holding_days = (sell_date - date(2022, 1, 1)).days
    assert oldest_holding_days > 365

    basis_50 = round(engine.compute(OrderSide.BUY, 100.0, 100).net_amount / 2, 2)
    expected_sell = engine.compute(
        OrderSide.SELL,
        200.0,
        50,
        buy_cost_basis=basis_50,
        holding_days=oldest_holding_days,
        investor="individual",
    )
    short_term_sell = engine.compute(
        OrderSide.SELL,
        200.0,
        50,
        buy_cost_basis=basis_50,
        holding_days=10,
        investor="individual",
    )
    # Long-term CGT (5%) must be strictly less than short-term (7.5%) on this gain.
    assert expected_sell.cgt < short_term_sell.cgt

    trade = pf.sell("SCB", 200.0, 50, sell_date)
    assert float(trade.cgt) == pytest.approx(float(expected_sell.cgt))

    # 150 shares remain (50 from the 2022 lot + 100 from 2024 lot).
    assert pf.positions["SCB"].quantity == 150


def test_fifo_sell_spanning_two_lots_uses_oldest_lot_date(engine: CostEngine) -> None:
    pf = PaperPortfolio(initial_cash=1_000_000.0, cost_engine=engine)
    pf.buy("SCB", 100.0, 100, date(2022, 1, 1))  # oldest
    pf.buy("SCB", 100.0, 100, date(2024, 1, 1))
    sell_date = date(2024, 3, 1)

    buy_basis = engine.compute(OrderSide.BUY, 100.0, 100).net_amount
    basis_150 = buy_basis + round(buy_basis / 2, 2)
    # Holding period is measured from the OLDEST contributing lot (2022).
    expected = engine.compute(
        OrderSide.SELL,
        200.0,
        150,
        buy_cost_basis=basis_150,
        holding_days=(sell_date - date(2022, 1, 1)).days,
        investor="individual",
    )
    trade = pf.sell("SCB", 200.0, 150, sell_date)
    assert float(trade.cgt) == pytest.approx(float(expected.cgt))
    assert pf.positions["SCB"].quantity == 50


# ----------------------------------------------------------------- storage hook
def test_storage_stub_records_each_fill(engine: CostEngine) -> None:
    storage = _RecordingStorage()
    pf = PaperPortfolio(initial_cash=100_000.0, cost_engine=engine, storage=storage)
    pf.buy("NABIL", 500.0, 10, date(2024, 1, 10))
    pf.sell("NABIL", 520.0, 10, date(2024, 1, 20))
    assert len(storage.recorded) == 2
    assert [t.side for t in storage.recorded] == [OrderSide.BUY, OrderSide.SELL]
    assert storage.recorded is not pf.trades
    assert [t.trade_id for t in storage.recorded] == [t.trade_id for t in pf.trades]


# --------------------------------------------------------------------- edge cases
@pytest.mark.parametrize("qty", [0, -5])
def test_buy_non_positive_quantity_raises(engine: CostEngine, qty: int) -> None:
    pf = PaperPortfolio(cost_engine=engine)
    with pytest.raises(ValueError):
        pf.buy("NABIL", 500.0, qty, date(2024, 1, 1))


@pytest.mark.parametrize("px", [0.0, -10.0])
def test_buy_non_positive_price_raises(engine: CostEngine, px: float) -> None:
    pf = PaperPortfolio(cost_engine=engine)
    with pytest.raises(ValueError):
        pf.buy("NABIL", px, 10, date(2024, 1, 1))


def test_sell_non_positive_quantity_raises(engine: CostEngine) -> None:
    pf = PaperPortfolio(cost_engine=engine)
    pf.buy("NABIL", 500.0, 10, date(2024, 1, 1))
    with pytest.raises(ValueError):
        pf.sell("NABIL", 500.0, 0, date(2024, 1, 2))


def test_empty_symbol_raises(engine: CostEngine) -> None:
    pf = PaperPortfolio(cost_engine=engine)
    with pytest.raises(ValueError):
        pf.buy("   ", 500.0, 10, date(2024, 1, 1))


# ------------------------------------------------------------------ valuations
def test_valuations_and_summary(engine: CostEngine) -> None:
    pf = PaperPortfolio(initial_cash=100_000.0, cost_engine=engine)
    pf.buy("NABIL", 500.0, 10, date(2024, 1, 10))
    prices = {"NABIL": 600.0}

    assert pf.market_value(prices) == pytest.approx(6_000.0)
    assert float(pf.equity(prices)) == pytest.approx(round(float(pf.cash) + 6_000.0, 2))

    assert pf.unrealized_pnl(prices) == pf.equity(prices) - pf.initial_cash

    # holdings returns Position objects; to_dict / summary are structured.
    assert all(isinstance(p, Position) for p in pf.holdings())
    d = pf.to_dict()
    assert d["trades"] == 1 and d["cash"] == pf.cash
    assert isinstance(pf.summary(), str)
    assert isinstance(pf.summary(prices), str)
    # Missing price for a held symbol is simply skipped (no crash).
    assert pf.market_value({}) == 0.0


def test_cash_rounded_to_2dp(engine: CostEngine) -> None:
    pf = PaperPortfolio(initial_cash=100_000.0, cost_engine=engine)
    pf.buy("NABIL", 333.33, 7, date(2024, 1, 10))
    assert float(pf.cash) == round(float(pf.cash), 2)
