"""A limited valuation/risk watchlist, never a promise of deposit-like safety."""

from __future__ import annotations

import math
from datetime import timedelta

from nepse_trader.advisor.decision_signals import reliable_volume
from nepse_trader.advisor.fundamentals import assess_fundamentals
from nepse_trader.analysis import quant
from nepse_trader.analysis.costs import CostEngine
from nepse_trader.models import OrderSide


def investment_candidate(
    symbol, bars, state, quality, snapshot, *, snapshot_date, today, owned=False, cost_engine=None,
    fundamental_report=None,
):
    if (
        state is None
        or snapshot is None
        or quality < 0.8
        or state.average_volume < 10000
        or not reliable_volume(bars, 18)
    ):
        return None
    fundamentals = fundamental_report or assess_fundamentals(
        snapshot, quote=state.close, snapshot_date=snapshot_date, today=today, symbol=symbol
    )
    if (
        fundamentals["multiplier"] <= 0
        or fundamentals["quality_multiplier"] < 1
        or fundamentals["current_pe"] is None
    ):
        return None
    eps = fundamentals["eps"]
    pe, pbv = state.close / eps, state.close / fundamentals["book_value"]
    if pe > 30 or pbv > 3:
        return None
    window = [b for b in bars if today - timedelta(days=400) <= b.business_date <= today]
    if len(window) < 200 or (window[-1].business_date - window[0].business_date).days < 365:
        return None
    if any(b.close is None or not math.isfinite(b.close) or b.close <= 0 for b in window):
        return None
    prices = [b.close for b in window]
    elapsed = (window[-1].business_date - window[0].business_date).days
    drawdown = quant.max_drawdown(prices)
    volatility = quant.annualized_volatility(
        quant.returns(prices), (len(prices) - 1) * 365 / elapsed
    )
    engine = cost_engine or CostEngine()
    buy = engine.compute(OrderSide.BUY, prices[0], 100)
    sell = engine.compute(
        OrderSide.SELL, prices[-1], 100, buy_cost_basis=buy.net_amount, holding_days=elapsed
    )
    annual = (float(sell.net_amount / buy.net_amount) ** (365 / elapsed) - 1) * 100
    if drawdown > 25 or volatility > 30 or annual <= 0:
        return None
    score = min(
        0.9,
        quality
        * (
            0.5
            + 0.5
            * (
                0.4 * (1 - pe / 30)
                + 0.25 * (1 - drawdown / 25)
                + 0.25 * (1 - volatility / 30)
                + 0.1 * (1 - pbv / 3)
            )
        ),
    )
    reasons = [
        *fundamentals["reasons"],
        f"Historical maximum decline {drawdown:.1f}% and volatility {volatility:.1f}% are below the screen limits.",
    ]
    return dict(
        symbol=symbol,
        company_name=snapshot.company_name,
        sector=snapshot.sector,
        horizon_days=252,
        reference_price=state.close,
        rationale=reasons,
        owned=owned,
        snapshot_date=fundamentals["reporting_period_end"] or fundamentals["snapshot_date"],
        history_from=window[0].business_date.isoformat(),
        history_to=window[-1].business_date.isoformat(),
        historical_net_annual_return=round(annual, 2),
        max_drawdown=round(drawdown, 2),
        annual_volatility=round(volatility, 2),
        pe=round(pe, 2),
        pbv=round(pbv, 2),
        eps=eps,
        declared_dividend_pct=snapshot.dividend_pct,
        score=round(score, 3),
        chart=[dict(date=b.business_date.isoformat(), close=b.close) for b in window[-45:]],
        confidence=dict(
            value=round(score, 3),
            label="Screen evidence",
            basis="Valuation, historical drawdown/volatility, liquidity and source quality; not a future return probability.",
        ),
        limitations="Historical returns exclude cash dividends and unconfirmed corporate actions. Financial coverage varies by issuer.",
    )
