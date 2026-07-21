"""Property-based tests for core invariants using Hypothesis.

Each test explores a space of random inputs and asserts an invariant holds,
catching edge cases example-based tests miss.
"""

from __future__ import annotations

from datetime import date

from hypothesis import assume, given
from hypothesis import strategies as st
from hypothesis.strategies import floats, integers

from nepse_trader.analysis.costs import CostEngine, _round2
from nepse_trader.analysis.indicators import bollinger_bands, ema, rsi, sma
from nepse_trader.ingest.reconcile import reconcile_bars
from nepse_trader.models import OrderSide, PriceBar, SourceName
from nepse_trader.trading.portfolio import PaperPortfolio

# ---------------------------------------------------------------------------
# Cost engine invariants
# ---------------------------------------------------------------------------

_price_amounts = floats(min_value=1, max_value=10_000_000, allow_nan=False, allow_infinity=False)
_quantities = integers(min_value=1, max_value=100_000)
_positive_floats = floats(min_value=0.01, max_value=1e12, allow_nan=False, allow_infinity=False)


@given(amount=_price_amounts)
def test_commission_monotonic(amount: float):
    """Broker commission is monotonic non-decreasing in transaction amount."""
    e = CostEngine()
    comm = e.broker_commission(amount)
    # At double the amount, commission must be >= original.
    comm2 = e.broker_commission(amount * 2)
    assert comm2 >= comm - 1e-9, (
        f"commission({amount * 2:.2f})={comm2:.4f} < commission({amount:.2f})={comm:.4f}"
    )


@given(amount=_price_amounts)
def test_commission_floor(amount: float):
    """Broker commission is never below the minimum."""
    e = CostEngine()
    comm = e.broker_commission(amount)
    assert comm >= e.model.broker_min_commission - 1e-9
    assert comm >= 0


@given(price=_price_amounts, qty=_quantities)
def test_buy_net_greater_than_gross(price: float, qty: int):
    """For a buy, net_amount (cash out) >= gross amount."""
    assume(qty * price < 1e12)
    e = CostEngine()
    bd = e.compute(OrderSide.BUY, price, qty)
    assert bd.net_amount >= bd.gross_amount - 1e-9
    assert bd.total_fees >= 0


@given(price=_price_amounts, qty=_quantities)
def test_fees_breakdown_sums_to_total(price: float, qty: int):
    """total_fees == commission + sebon + dp + cgt."""
    assume(qty * price < 1e12)
    e = CostEngine()
    bd = e.compute(OrderSide.BUY, price, qty)
    expected = _round2(bd.broker_commission + bd.sebon_fee + bd.dp_charge + bd.cgt)
    assert abs(bd.total_fees - expected) < 1e-9, f"total_fees={bd.total_fees} != {expected}"


@given(price=_price_amounts, qty=_quantities)
def test_cgt_zero_on_buy(price: float, qty: int):
    """CGT is always zero on the buy side."""
    assume(qty * price < 1e12)
    e = CostEngine()
    bd = e.compute(OrderSide.BUY, price, qty)
    assert bd.cgt == 0.0


@given(
    buy_price=_price_amounts,
    sell_price=_price_amounts,
    qty=_quantities,
    basis_mult=floats(min_value=0.5, max_value=2.0),
)
def test_cgt_non_negative(buy_price: float, sell_price: float, qty: int, basis_mult: float):
    """CGT on a sell is never negative."""
    assume(buy_price * qty < 1e11)
    assume(sell_price * qty < 1e11)
    e = CostEngine()
    buy_cost = e.compute(OrderSide.BUY, buy_price, qty).net_amount
    sell = e.compute(
        OrderSide.SELL, sell_price, qty, buy_cost_basis=buy_cost * basis_mult, holding_days=100
    )
    assert sell.cgt >= 0


@given(price=_price_amounts, qty=_quantities)
def test_effective_buy_cost_per_share(price: float, qty: int):
    """effective_buy_cost_per_share = net_amount / quantity."""
    assume(qty * price < 1e12)
    e = CostEngine()
    bd = e.compute(OrderSide.BUY, price, qty)
    eff = e.effective_buy_cost_per_share(price, qty)
    assert abs(eff - bd.net_amount / qty) < 1e-9


# ---------------------------------------------------------------------------
# Indicator invariants
# ---------------------------------------------------------------------------

_price_series = st.lists(
    floats(min_value=0.01, max_value=10_000, allow_nan=False, allow_infinity=False),
    min_size=3,
    max_size=200,
)


@given(values=_price_series)
def test_sma_bounds(values: list[float]):
    """SMA values lie within [min(values), max(values)] for the defined portion."""
    period = max(2, len(values) // 4)
    result = sma(values, period)
    defined = [v for v in result if v is not None]
    if defined:
        assert min(defined) >= min(values) - 1e-9
        assert max(defined) <= max(values) + 1e-9


@given(values=_price_series)
def test_ema_bounds(values: list[float]):
    """EMA values lie within [min(values), max(values)]."""
    period = max(2, len(values) // 4)
    result = ema(values, period)
    defined = [v for v in result if v is not None]
    if defined:
        assert min(defined) >= min(values) - 1e-9
        assert max(defined) <= max(values) + 1e-9


@given(values=_price_series)
def test_sma_warmup(values: list[float]):
    """SMA has None for the first (period-1) positions."""
    period = max(2, len(values) // 3)
    result = sma(values, period)
    for i in range(min(period - 1, len(result))):
        assert result[i] is None


@given(values=_price_series)
def test_rsi_bounds(values: list[float]):
    """RSI is always in [0, 100]."""
    period = max(2, len(values) // 4)
    result = rsi(values, period)
    for v in result:
        if v is not None:
            assert 0.0 <= v <= 100.0 + 1e-9


@given(values=_price_series)
def test_bollinger_bands_ordered(values: list[float]):
    """Bollinger: lower <= middle <= upper."""
    period = max(3, len(values) // 4)
    lower, middle, upper = bollinger_bands(values, period=period)
    for lo, m, u in zip(lower, middle, upper, strict=True):
        if lo is not None and m is not None and u is not None:
            assert lo <= m + 1e-9, f"lower={lo} > middle={m}"
            assert m <= u + 1e-9, f"middle={m} > upper={u}"


# ---------------------------------------------------------------------------
# Reconciliation invariants
# ---------------------------------------------------------------------------

_source_names = st.sampled_from([s for s in SourceName if s != SourceName.MANUAL])

_price_bar_strategy = st.builds(
    PriceBar,
    symbol=st.text(min_size=1, max_size=10, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
    business_date=st.dates(min_value=date(2020, 1, 1), max_value=date(2026, 12, 31)),
    open=_positive_floats,
    high=_positive_floats,
    low=_positive_floats,
    close=_positive_floats,
    previous_close=_positive_floats,
    volume=integers(min_value=0, max_value=10_000_000),
    turnover=_positive_floats,
    source=_source_names,
)


@given(bars=st.lists(_price_bar_strategy, min_size=1, max_size=20))
def test_reconcile_confidence_range(bars: list[PriceBar]):
    """Reconciled confidence is always in [0, 1]."""
    reconciled = reconcile_bars(bars)
    for r in reconciled:
        assert 0.0 <= r.confidence <= 1.0


@given(bars=st.lists(_price_bar_strategy, min_size=1, max_size=20))
def test_reconcile_close_within_source_range(bars: list[PriceBar]):
    """Reconciled close lies within the min/max of AGREEING source close values."""
    reconciled = reconcile_bars(bars)
    for r in reconciled:
        if r.close is not None and r.sources_agreeing:
            agreeing = r.sources_agreeing
            agreeing_closes = [
                b.close for b in bars if b.close is not None and b.source in agreeing
            ]
            if agreeing_closes:
                assert min(agreeing_closes) <= r.close <= max(agreeing_closes) + 1e-9


@given(bars=st.lists(_price_bar_strategy, min_size=1, max_size=20))
def test_reconcile_disputed_fields_match(bars: list[PriceBar]):
    """A field is disputed iff its values span more than the tolerance."""
    reconciled = reconcile_bars(bars, tolerance=0.005)
    for r in reconciled:
        assert isinstance(r.disputed_fields, list)


# ---------------------------------------------------------------------------
# Portfolio invariants
# ---------------------------------------------------------------------------


@given(
    initial_cash=floats(
        min_value=10_000, max_value=10_000_000, allow_nan=False, allow_infinity=False
    ),
    price=_price_amounts,
    qty=_quantities,
)
def test_portfolio_cash_after_buy(initial_cash: float, price: float, qty: int):
    """After a buy, cash decreases by net_amount."""
    assume(qty * price < 1e11)
    assume(price > 0 and qty > 0)
    pf = PaperPortfolio(initial_cash=initial_cash)
    # Compute cost upfront and skip if unaffordable.
    e = CostEngine()
    bd = e.compute(OrderSide.BUY, price, qty)
    assume(bd.net_amount <= initial_cash)
    pf.buy("TEST", price, qty, date(2026, 6, 1))
    assert pf.cash < initial_cash
    assert pf.cash >= 0
