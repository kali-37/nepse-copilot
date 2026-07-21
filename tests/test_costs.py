"""Tests for the Nepal cost & tax engine.

The headline test reproduces the researched worked example end to end:
BUY 100 @ 1000 then SELL 100 @ 1200 (individual, short-term).
"""

from __future__ import annotations

from decimal import Decimal

from nepse_trader.analysis.costs import CostEngine
from nepse_trader.config import CommissionSlab, CostModel
from nepse_trader.models import OrderSide


def _engine() -> CostEngine:
    model = CostModel(
        broker_commission_slabs=[
            CommissionSlab(min_amount=0, max_amount=50000, rate_percent=0.36),
            CommissionSlab(min_amount=50000, max_amount=500000, rate_percent=0.33),
            CommissionSlab(min_amount=500000, max_amount=2000000, rate_percent=0.31),
            CommissionSlab(min_amount=2000000, max_amount=10000000, rate_percent=0.27),
            CommissionSlab(min_amount=10000000, max_amount=None, rate_percent=0.24),
        ],
        broker_min_commission=10.0,
        sebon_fee_percent=0.015,
        dp_charge_per_scrip=25.0,
        cgt_short_percent=7.5,
        cgt_long_percent=5.0,
        cgt_institutional_percent=10.0,
    )
    return CostEngine(model)


def test_commission_rate_slabs():
    eng = _engine()
    assert eng.commission_rate(10_000) == Decimal("0.36")
    assert eng.commission_rate(100_000) == Decimal("0.33")
    assert eng.commission_rate(1_000_000) == Decimal("0.31")
    assert eng.commission_rate(5_000_000) == Decimal("0.27")
    assert eng.commission_rate(20_000_000) == Decimal("0.24")


def test_commission_rate_boundary_belongs_to_lower_tier():
    # The official schedule charges a boundary amount at the LOWER tier's
    # (higher) rate: exactly Rs 50,000 -> 0.36%, not 0.33%.
    eng = _engine()
    assert eng.commission_rate(50_000) == Decimal("0.36")
    assert eng.commission_rate(50_000.01) == Decimal("0.33")
    assert eng.commission_rate(500_000) == Decimal("0.33")
    assert eng.commission_rate(2_000_000) == Decimal("0.31")
    assert eng.commission_rate(10_000_000) == Decimal("0.27")
    assert eng.commission_rate(10_000_000.01) == Decimal("0.24")


def test_min_commission_floor():
    eng = _engine()
    # gross 100 -> 0.36% = 0.36, floored to Rs 10.
    assert eng.broker_commission(100) == Decimal("10.00")


def test_buy_breakdown_matches_worked_example():
    eng = _engine()
    bd = eng.compute(OrderSide.BUY, price=1000, quantity=100)
    assert bd.gross_amount == Decimal("100000.00")
    assert bd.broker_commission == Decimal("330.00")  # 0.33%
    assert bd.sebon_fee == Decimal("15.00")  # 0.015%
    assert bd.dp_charge == Decimal("25.00")
    assert bd.cgt == Decimal("0.00")
    assert bd.net_amount == Decimal("100370.00")
    assert bd.total_fees == Decimal("370.00")


def test_sell_breakdown_with_cgt_matches_worked_example():
    eng = _engine()
    buy = eng.compute(OrderSide.BUY, 1000, 100)
    sell = eng.compute(OrderSide.SELL, 1200, 100, buy_cost_basis=buy.net_amount, holding_days=30)
    assert sell.gross_amount == Decimal("120000.00")
    assert sell.broker_commission == Decimal("396.00")  # 0.33% of 120,000
    assert sell.sebon_fee == Decimal("18.00")
    assert sell.dp_charge == Decimal("25.00")
    # gain = (120000 - 396 - 18 - 25) - 100370 = 119561 - 100370 = 19191
    expected_cgt = Decimal(str(round(19_191 * 0.075, 2)))  # 1439.33
    assert sell.cgt == expected_cgt
    assert sell.net_amount == Decimal("119561.00") - expected_cgt


def test_long_term_rate_applies_after_365_days():
    eng = _engine()
    buy = eng.compute(OrderSide.BUY, 1000, 100)
    short = eng.compute(OrderSide.SELL, 1200, 100, buy_cost_basis=buy.net_amount, holding_days=100)
    long = eng.compute(OrderSide.SELL, 1200, 100, buy_cost_basis=buy.net_amount, holding_days=400)
    assert float(long.cgt) < float(short.cgt)  # 5% < 7.5%


def test_cgt_boundary_exactly_365_days_is_short_term():
    # IRD rule: short-term is held <= 365 days; long-term requires > 365 days.
    # A sale on exactly the 365th day must still be taxed at 7.5%.
    eng = _engine()
    buy = eng.compute(OrderSide.BUY, 1000, 100)
    at_365 = eng.compute(OrderSide.SELL, 1200, 100, buy_cost_basis=buy.net_amount, holding_days=365)
    at_366 = eng.compute(OrderSide.SELL, 1200, 100, buy_cost_basis=buy.net_amount, holding_days=366)
    assert at_365.cgt == Decimal("1439.33")  # short-term (7.5%, half-up)
    assert at_366.cgt == Decimal("959.55")  # long-term (5%)


def test_institutional_rate():
    eng = _engine()
    buy = eng.compute(OrderSide.BUY, 1000, 100)
    inst = eng.compute(
        OrderSide.SELL,
        1200,
        100,
        buy_cost_basis=buy.net_amount,
        holding_days=30,
        investor="institutional",
    )
    gain = Decimal(str(120_000 - 396 - 18 - 25)) - buy.net_amount
    assert inst.cgt == (gain * Decimal("0.10")).quantize(Decimal("0.01"))


def test_no_cgt_on_loss():
    eng = _engine()
    buy = eng.compute(OrderSide.BUY, 1000, 100)
    sell = eng.compute(OrderSide.SELL, 800, 100, buy_cost_basis=buy.net_amount, holding_days=30)
    assert sell.cgt == Decimal("0.00")


def test_invalid_inputs_raise():
    eng = _engine()
    try:
        eng.compute(OrderSide.BUY, 100, 0)
        raised = False
    except ValueError:
        raised = True
    assert raised
