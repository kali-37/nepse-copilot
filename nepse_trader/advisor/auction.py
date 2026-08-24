"""Fee-aware, advice-only guidance for NEPSE auction bids.

The auction module computes a ceiling a human can use when entering a manual
bid.  It has no HTTP, MeroShare, ASBA or order-placement dependency: it cannot
submit a bid.  Its job is strictly to show the cost stack that an apparently
cheap auction lot needs to overcome before it can produce a net gain.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from nepse_trader.advisor.confidence import Confidence, market
from nepse_trader.analysis.costs import CostEngine, _to_money
from nepse_trader.calendar import add_trading_days
from nepse_trader.models import OrderSide

BID = "bid"
SKIP = "skip"

# Auction lots are not automatically more liquid than the normal board.  The
# builder therefore leaves a buffer below the fee-neutral bid instead of telling
# a user to bid away every rupee of expected upside.
DEFAULT_EDGE_BUFFER_PCT = 0.10


def _round_price(value: float) -> float:
    """Round displayed prices to paisa without introducing binary drift."""

    return float(_to_money(Decimal(str(value))))


def _as_date(value: date | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _advice_id(
    *,
    symbol: str,
    auction_date: date,
    units: int,
    min_bid_price: float,
    market_price: float,
    expected_exit_price: float,
    quantity: int,
    horizon_days: int,
    edge_buffer_pct: float,
) -> str:
    """A stable id makes repeated advice runs upsert rather than duplicate."""

    natural_key = "|".join(
        (
            symbol,
            auction_date.isoformat(),
            str(units),
            f"{min_bid_price:.2f}",
            f"{market_price:.2f}",
            f"{expected_exit_price:.2f}",
            str(quantity),
            str(horizon_days),
            f"{edge_buffer_pct:.6f}",
        )
    )
    return f"auction:{hashlib.sha256(natural_key.encode()).hexdigest()[:24]}"


def _net_pnl(
    engine: CostEngine,
    *,
    bid_price: float,
    exit_price: float,
    quantity: int,
    holding_days: int,
) -> Decimal:
    buy = engine.compute(OrderSide.BUY, bid_price, quantity)
    sell = engine.compute(
        OrderSide.SELL,
        exit_price,
        quantity,
        buy_cost_basis=buy.net_amount,
        holding_days=holding_days,
    )
    return _to_money(sell.net_amount - buy.net_amount)


def _break_even_bid(
    engine: CostEngine,
    *,
    exit_price: float,
    quantity: int,
    holding_days: int,
) -> float:
    """Largest buy price that does not lose money after the entire cost stack.

    Fees and tax slabs make this a monotonic but piecewise function, so binary
    search is clearer and safer than trying to reverse every slab algebraically.
    It resolves to paisa; the maximum returned bid has non-negative net PnL.
    """

    if exit_price <= 0 or quantity <= 0:
        return 0.0
    low = Decimal("0.00")
    high = _to_money(exit_price)
    paisa = Decimal("0.01")
    while high - low > paisa:
        mid = _to_money((low + high) / Decimal("2"))
        pnl = _net_pnl(
            engine,
            bid_price=float(mid),
            exit_price=exit_price,
            quantity=quantity,
            holding_days=holding_days,
        )
        if pnl >= 0:
            low = mid
        else:
            high = mid
    # `low` can land on a midpoint rounded upward across a fee boundary.  Walk
    # back a paisa until the contract is exact, rather than displaying a fake
    # break-even due to decimal quantisation.
    while low > 0 and _net_pnl(
        engine,
        bid_price=float(low),
        exit_price=exit_price,
        quantity=quantity,
        holding_days=holding_days,
    ) < 0:
        low -= paisa
    return _round_price(float(low))


@dataclass(frozen=True)
class AuctionAdvice:
    """A manual auction-bid prescription, never a bid instruction to a broker."""

    advice_id: str
    symbol: str
    auction_date: date
    units: int
    min_bid_price: float
    market_price: float
    recommended_bid: float
    max_sensible_bid: float
    walk_away_price: float
    breakeven_price: float
    quantity: int
    outlay: Decimal
    expected_exit_price: float
    expected_gross_pnl: Decimal
    expected_net_pnl: Decimal
    expected_return_pct: float
    horizon_days: int
    earliest_sell_date: date
    confidence: Confidence
    verdict: str
    rationale: str

    @property
    def confidence_band(self) -> str:
        return self.confidence.band

    @property
    def confidence_basis(self) -> str:
        return self.confidence.basis

    def as_dict(self) -> dict[str, object]:
        return {
            "advice_id": self.advice_id,
            "symbol": self.symbol,
            "auction_date": self.auction_date.isoformat(),
            "units": self.units,
            "min_bid_price": self.min_bid_price,
            "market_price": self.market_price,
            "recommended_bid": self.recommended_bid,
            "max_sensible_bid": self.max_sensible_bid,
            "walk_away_price": self.walk_away_price,
            "breakeven_price": self.breakeven_price,
            "quantity": self.quantity,
            "outlay": float(self.outlay),
            "expected_exit_price": self.expected_exit_price,
            "expected_gross_pnl": float(self.expected_gross_pnl),
            "expected_net_pnl": float(self.expected_net_pnl),
            "expected_return_pct": self.expected_return_pct,
            "horizon_days": self.horizon_days,
            "earliest_sell_date": self.earliest_sell_date.isoformat(),
            "confidence": self.confidence.value,
            "confidence_band": self.confidence.band,
            "confidence_basis": self.confidence.basis,
            "verdict": self.verdict,
            "rationale": self.rationale,
        }


def build_auction_advice(
    symbol: str,
    *,
    auction_date: date | str,
    units: int,
    min_bid_price: float,
    market_price: float,
    expected_exit_price: float | None = None,
    horizon_days: int = 10,
    quantity: int | None = None,
    confidence: Confidence | float | None = None,
    edge_buffer_pct: float = DEFAULT_EDGE_BUFFER_PCT,
    cost_engine: CostEngine | None = None,
    advice_id: str | None = None,
) -> AuctionAdvice:
    """Build deterministic, fee-aware advice for a manually entered auction bid.

    ``expected_exit_price`` is deliberately an input, not an invented forecast:
    callers should pass the deterministic plan target or an explicit researched
    assumption.  The recommended bid is the lower of the auction minimum and a
    buffered fee-neutral ceiling when the lot has positive expected net edge.
    If the auction minimum is already above that ceiling, the verdict is
    ``skip``.  No function here can place, submit, or transmit a bid.
    """

    symbol = str(symbol).strip().upper()
    auction_day = _as_date(auction_date)
    if not symbol:
        raise ValueError("symbol must be non-empty")
    if units <= 0:
        raise ValueError("units must be positive")
    if min_bid_price <= 0:
        raise ValueError("min_bid_price must be positive")
    if market_price <= 0:
        raise ValueError("market_price must be positive")
    if horizon_days < 0:
        raise ValueError("horizon_days cannot be negative")
    if not 0.0 <= edge_buffer_pct < 1.0:
        raise ValueError("edge_buffer_pct must be in [0, 1)")

    qty = int(quantity if quantity is not None else units)
    if qty <= 0:
        raise ValueError("quantity must be positive")
    if qty > units:
        raise ValueError("quantity cannot exceed auction units")
    exit_price = float(expected_exit_price if expected_exit_price is not None else market_price)
    if exit_price <= 0:
        raise ValueError("expected_exit_price must be positive")

    engine = cost_engine or CostEngine()
    breakeven_bid = _break_even_bid(
        engine,
        exit_price=exit_price,
        quantity=qty,
        holding_days=horizon_days,
    )
    # Keep a visible buffer under net breakeven.  This is a risk haircut, not a
    # claim about auction demand, and fees remain included because it starts
    # from the full CostEngine break-even calculation.
    buffered_ceiling = _round_price(breakeven_bid * (1.0 - edge_buffer_pct))
    max_sensible = max(0.0, buffered_ceiling)
    # The fee-neutral bid is the factual point where the assumed exit loses
    # money.  The smaller ``max_sensible_bid`` preserves an explicit margin for
    # auction competition and execution uncertainty.
    walk_away = breakeven_bid
    recommended = _round_price(min_bid_price)
    expected_net = _net_pnl(
        engine,
        bid_price=recommended,
        exit_price=exit_price,
        quantity=qty,
        holding_days=horizon_days,
    )
    buy = engine.compute(OrderSide.BUY, recommended, qty)
    gross = _to_money(
        (Decimal(str(exit_price)) - Decimal(str(recommended))) * Decimal(str(qty))
    )
    expected_return = (
        round(float(expected_net / buy.net_amount * Decimal("100")), 4)
        if buy.net_amount
        else 0.0
    )
    # The recommendation must respect the advertised conservative haircut, not
    # merely the fee-neutral boundary. ``walk_away`` remains useful context, but
    # bidding between the two would silently discard the stated safety margin.
    feasible = recommended <= max_sensible and expected_net > 0
    verdict = BID if feasible else SKIP

    if confidence is None:
        # A price forecast cannot be certain.  The fee arithmetic itself is
        # separately auditable at 1.0, but it must not lift the market forecast.
        base_confidence = market(
            0.45,
            "no auction-specific track record; house prior, with fee arithmetic checked",
        )
    elif isinstance(confidence, Confidence):
        base_confidence = market(confidence.value, confidence.basis)
    else:
        base_confidence = market(float(confidence), "caller-supplied market confidence")

    if verdict == BID:
        rationale = (
            f"Manual bid only: {recommended:.2f} is at the auction minimum and below the "
            f"conservative maximum {max_sensible:.2f}; the fee-neutral walk-away bid is "
            f"{walk_away:.2f}. Expected exit {exit_price:.2f} leaves NPR {expected_net:.2f} "
            f"after broker, SEBON, DP and CGT charges."
        )
    else:
        rationale = (
            f"Skip: the auction minimum {recommended:.2f} is above the conservative "
            f"maximum {max_sensible:.2f} (fee-neutral walk-away {walk_away:.2f}) or leaves no positive net edge at the "
            f"assumed exit {exit_price:.2f}. No bid is placed by this software."
        )

    return AuctionAdvice(
        advice_id=advice_id
        or _advice_id(
            symbol=symbol,
            auction_date=auction_day,
            units=units,
            min_bid_price=min_bid_price,
            market_price=market_price,
            expected_exit_price=exit_price,
            quantity=qty,
            horizon_days=horizon_days,
            edge_buffer_pct=edge_buffer_pct,
        ),
        symbol=symbol,
        auction_date=auction_day,
        units=units,
        min_bid_price=_round_price(min_bid_price),
        market_price=_round_price(market_price),
        recommended_bid=recommended,
        max_sensible_bid=max_sensible,
        walk_away_price=walk_away,
        # This is the *market exit price* needed to break even at the selected
        # bid, solved below for display rather than confusing it with bid ceiling.
        breakeven_price=_break_even_exit_price(
            engine,
            bid_price=recommended,
            quantity=qty,
            holding_days=horizon_days,
        ),
        quantity=qty,
        outlay=buy.net_amount,
        expected_exit_price=_round_price(exit_price),
        expected_gross_pnl=gross,
        expected_net_pnl=expected_net,
        expected_return_pct=expected_return,
        horizon_days=horizon_days,
        earliest_sell_date=add_trading_days(auction_day, 2),
        confidence=base_confidence,
        verdict=verdict,
        rationale=rationale,
    )


def _break_even_exit_price(
    engine: CostEngine,
    *,
    bid_price: float,
    quantity: int,
    holding_days: int,
) -> float:
    """Lowest exit price whose full-cost net PnL is non-negative."""

    if bid_price <= 0 or quantity <= 0:
        return 0.0
    low = Decimal("0.00")
    high = _to_money(Decimal(str(bid_price)) * Decimal("2"))
    while _net_pnl(
        engine,
        bid_price=bid_price,
        exit_price=float(high),
        quantity=quantity,
        holding_days=holding_days,
    ) < 0:
        high *= 2
    paisa = Decimal("0.01")
    while high - low > paisa:
        mid = _to_money((low + high) / Decimal("2"))
        if _net_pnl(
            engine,
            bid_price=bid_price,
            exit_price=float(mid),
            quantity=quantity,
            holding_days=holding_days,
        ) >= 0:
            high = mid
        else:
            low = mid
    while _net_pnl(
        engine,
        bid_price=bid_price,
        exit_price=float(high),
        quantity=quantity,
        holding_days=holding_days,
    ) < 0:
        high += paisa
    return _round_price(float(high))


def advise_auction(*args: object, **kwargs: object) -> AuctionAdvice:
    """Compatibility alias for :func:`build_auction_advice`."""

    return build_auction_advice(*args, **kwargs)  # type: ignore[arg-type]


def _plan_value(plan: object, name: str, default: Any = None) -> Any:
    if isinstance(plan, dict):
        return plan.get(name, default)
    return getattr(plan, name, default)


def advise_from_plan(
    plan: object,
    *,
    auction_date: date,
    units: int,
    min_bid_price: float,
    market_price: float | None = None,
    confidence: Confidence | float | None = None,
    cost_engine: CostEngine | None = None,
    **kwargs: object,
) -> AuctionAdvice:
    """Build auction advice from a deterministic plan card or its JSON form.

    This is a convenience bridge only.  It reads the plan's first target as the
    explicit exit assumption and never transmits data to an auction system.
    """

    symbol = _plan_value(plan, "symbol", "")
    target = _plan_value(plan, "target_1")
    if target is None:
        targets = _plan_value(plan, "targets", []) or []
        target = targets[0] if targets else None
    reference = _plan_value(plan, "reference_price")
    if market_price is None:
        market_price = reference
    if target is None or market_price is None:
        raise ValueError("plan must include reference_price and a first target")
    return build_auction_advice(
        str(symbol),
        auction_date=auction_date,
        units=units,
        min_bid_price=min_bid_price,
        market_price=float(market_price),
        expected_exit_price=float(target),
        horizon_days=int(_plan_value(plan, "horizon_days", 10) or 10),
        confidence=confidence,
        cost_engine=cost_engine,
        **kwargs,
    )


def save_auction_advice(conn: object, advice: AuctionAdvice) -> int:
    """Persist one manual auction recommendation using parameterized SQL.

    The caller owns the surrounding transaction and commit.  Saving advice is
    intentionally distinct from taking action: this function only inserts into
    ``auction_advice`` and has no network or broker dependency.
    """

    cursor = conn.execute(
        """INSERT INTO auction_advice (
                advice_id, symbol, auction_date, units, min_bid_price, market_price,
                recommended_bid, max_sensible_bid, walk_away_price, breakeven_price,
                quantity, outlay, expected_exit_price, expected_gross_pnl,
                expected_net_pnl, expected_return_pct, horizon_days, earliest_sell_date,
                confidence, confidence_band, confidence_basis, verdict, rationale, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(advice_id) DO UPDATE SET
                symbol=excluded.symbol, auction_date=excluded.auction_date,
                units=excluded.units, min_bid_price=excluded.min_bid_price,
                market_price=excluded.market_price, recommended_bid=excluded.recommended_bid,
                max_sensible_bid=excluded.max_sensible_bid,
                walk_away_price=excluded.walk_away_price,
                breakeven_price=excluded.breakeven_price, quantity=excluded.quantity,
                outlay=excluded.outlay, expected_exit_price=excluded.expected_exit_price,
                expected_gross_pnl=excluded.expected_gross_pnl,
                expected_net_pnl=excluded.expected_net_pnl,
                expected_return_pct=excluded.expected_return_pct,
                horizon_days=excluded.horizon_days,
                earliest_sell_date=excluded.earliest_sell_date,
                confidence=excluded.confidence,
                confidence_band=excluded.confidence_band,
                confidence_basis=excluded.confidence_basis,
                verdict=excluded.verdict, rationale=excluded.rationale""",
        (
            advice.advice_id,
            advice.symbol,
            advice.auction_date.isoformat(),
            advice.units,
            advice.min_bid_price,
            advice.market_price,
            advice.recommended_bid,
            advice.max_sensible_bid,
            advice.walk_away_price,
            advice.breakeven_price,
            advice.quantity,
            float(advice.outlay),
            advice.expected_exit_price,
            float(advice.expected_gross_pnl),
            float(advice.expected_net_pnl),
            advice.expected_return_pct,
            advice.horizon_days,
            advice.earliest_sell_date.isoformat(),
            advice.confidence.value,
            advice.confidence.band,
            advice.confidence.basis,
            advice.verdict,
            advice.rationale,
            datetime.now(UTC).isoformat(),
        ),
    )
    return int(cursor.lastrowid or 0)


def auction_advice_history(
    conn: object,
    *,
    symbol: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return saved recommendations newest first, optionally for one symbol."""

    cap = max(1, int(limit))
    if symbol:
        rows = conn.execute(
            """SELECT * FROM auction_advice WHERE symbol=?
               ORDER BY auction_date DESC, id DESC LIMIT ?""",
            (symbol.strip().upper(), cap),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM auction_advice ORDER BY auction_date DESC, id DESC LIMIT ?",
            (cap,),
        ).fetchall()
    return [dict(row) for row in rows]


def latest_auction_advice(conn: object, *, symbol: str | None = None) -> dict[str, Any] | None:
    """Return the most recently persisted recommendation, if any."""

    rows = auction_advice_history(conn, symbol=symbol, limit=1)
    return rows[0] if rows else None


__all__ = [
    "BID",
    "SKIP",
    "DEFAULT_EDGE_BUFFER_PCT",
    "AuctionAdvice",
    "build_auction_advice",
    "advise_auction",
    "advise_from_plan",
    "save_auction_advice",
    "auction_advice_history",
    "latest_auction_advice",
]
