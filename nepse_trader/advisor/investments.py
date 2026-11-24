"""A limited valuation/risk watchlist, never a promise of deposit-like safety."""

from __future__ import annotations

import math
from datetime import timedelta

from nepse_trader.advisor.decision_signals import reliable_volume
from nepse_trader.analysis import quant
from nepse_trader.analysis.costs import CostEngine
from nepse_trader.models import OrderSide


def investment_candidate(
    symbol, bars, state, quality, snapshot, *, snapshot_date, today, owned=False
):
    if (
        state is None
        or snapshot is None
        or quality < 0.8
        or state.average_volume < 10000
        or not reliable_volume(bars, 18)
    ):
        return None
    if not snapshot_date or (today - snapshot_date).days > 90:
        return None
    if any(
        v is None or not math.isfinite(v) or v <= 0 for v in (snapshot.eps, snapshot.book_value)
    ):
        return None
    pe, pbv = state.close / snapshot.eps, state.close / snapshot.book_value
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
    engine = CostEngine()
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
        f"Reported EPS is positive: NPR {snapshot.eps:.2f}, snapshot {snapshot_date}.",
        f"Current quote implies P/E {pe:.1f} and price/book {pbv:.2f} within the screen limits.",
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
        snapshot_date=snapshot_date.isoformat(),
        history_from=window[0].business_date.isoformat(),
        history_to=window[-1].business_date.isoformat(),
        historical_net_annual_return=round(annual, 2),
        max_drawdown=round(drawdown, 2),
        annual_volatility=round(volatility, 2),
        pe=round(pe, 2),
        pbv=round(pbv, 2),
        eps=snapshot.eps,
        declared_dividend_pct=snapshot.dividend_pct,
        score=round(score, 3),
        chart=[dict(date=b.business_date.isoformat(), close=b.close) for b in window[-45:]],
        confidence=dict(
            value=round(score, 3),
            label="Screen evidence",
            basis="Valuation, historical drawdown/volatility, liquidity and source quality; not a future return probability.",
        ),
        limitations="Cash dividends are excluded; a declared dividend percent is not a confirmed market cash yield. Unconfirmed corporate actions are excluded. Financial strength beyond EPS/book value is not verified.",
    )
