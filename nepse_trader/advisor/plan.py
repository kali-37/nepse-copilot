"""Deterministic plan cards: the numbers behind the daily prescription.

Every figure a user could act on originates here — entry zone, stop, targets,
quantity, horizon, settlement date, and expected PnL net of both transaction
costs and capital gains tax. Nothing in this module talks to the network or to
an LLM, which is what makes Normal mode a complete product rather than a
degraded one.

Three design choices worth stating:

* **An entry zone, not a price.** A single number invites a limit order that
  never fills. The zone is ATR-scaled around the last close, so it widens with
  volatility rather than being a fixed percentage.
* **The stop is clamped to the circuit.** ``stop_loss_price`` already does this:
  a stop further than 10% below entry is unreachable in one session on NEPSE,
  so quoting one would be a lie about the risk taken.
* **A card is either complete or absent.** Without an ATR there is no honest
  stop, and without a stop there is no honest position size — so the symbol is
  reported as :class:`Skipped` with a reason instead of getting a card built on
  guesses.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from nepse_trader.advisor.confidence import DEFAULT_PRIOR, Confidence, market
from nepse_trader.analysis import indicators
from nepse_trader.analysis.costs import CostEngine, _to_money
from nepse_trader.analysis.risk import size_position, stop_loss_price, take_profit_price
from nepse_trader.calendar import add_trading_days
from nepse_trader.models import OrderSide, PriceBar, Signal, SignalAction

# NEPSE settles two trading days after the trade.
SETTLEMENT_TRADING_DAYS = 2

# The engine's own vocabulary, deliberately identical to the AI layer's STANCES
# so a note and a card can never disagree about what was recommended.
ACCUMULATE = "accumulate"
HOLD = "hold"
REDUCE = "reduce"
AVOID = "avoid"

_ATR_PERIOD = 14
_MIN_BARS = _ATR_PERIOD + 6  # enough history for an ATR plus a little context


@dataclass
class Skipped:
    """A symbol that could not be given an honest card, and why.

    Surfaced rather than silently dropped: "no card for NABIL" is information,
    and hiding it would make an incomplete report look complete.
    """

    symbol: str
    reason: str


@dataclass
class PlanCard:
    """One symbol's prescription. Every field here is engine-computed."""

    symbol: str
    action: str
    reference_price: float
    entry_low: float
    entry_high: float
    stop: float
    targets: list[float]
    quantity: int
    horizon_days: int
    earliest_sell_date: date
    conviction: int
    rationale: str
    confidence: Confidence = field(
        default_factory=lambda: market(
            DEFAULT_PRIOR,
            "no resolved comparable predictions; house prior",
        )
    )
    # Expected outcome at target_1, net of the full Nepal cost stack.
    gross_pnl: Decimal = Decimal("0.00")
    net_pnl: Decimal = Decimal("0.00")
    entry_cost: Decimal = Decimal("0.00")
    exit_cost: Decimal = Decimal("0.00")
    capital_gains_tax: Decimal = Decimal("0.00")
    # Filled in by the AI layer in AI mode; never read by the engine.
    note: str = ""
    signals: list[str] = field(default_factory=list)

    @property
    def target_1(self) -> float | None:
        return self.targets[0] if self.targets else None

    @property
    def target_2(self) -> float | None:
        return self.targets[1] if len(self.targets) > 1 else None

    @property
    def risk_per_share(self) -> float:
        return round(self.entry_high - self.stop, 2)

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "action": self.action,
            "reference_price": self.reference_price,
            "entry_low": self.entry_low,
            "entry_high": self.entry_high,
            "stop": self.stop,
            "targets": list(self.targets),
            "quantity": self.quantity,
            "horizon_days": self.horizon_days,
            "earliest_sell_date": self.earliest_sell_date.isoformat(),
            "conviction": self.conviction,
            "rationale": self.rationale,
            "confidence": self.confidence.as_dict(),
            "gross_pnl": float(self.gross_pnl),
            "net_pnl": float(self.net_pnl),
            "entry_cost": float(self.entry_cost),
            "exit_cost": float(self.exit_cost),
            "capital_gains_tax": float(self.capital_gains_tax),
            "note": self.note,
            "signals": list(self.signals),
        }


def _latest_atr(bars: list[PriceBar]) -> float | None:
    """Wilder ATR over the reconciled history, or None if it can't be computed."""
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    closes = [b.close for b in bars]
    if any(v is None for v in highs + lows + closes):
        return None
    series = indicators.atr(highs, lows, closes, period=_ATR_PERIOD)
    for value in reversed(series):
        if value is not None:
            return float(value)
    return None


def _decide(signals: list[Signal]) -> tuple[str, int, list[str]]:
    """Turn the strategy panel's votes into an action, conviction and reasons.

    Conviction is the 1–5 ordinal the AI layer also uses, derived from how many
    strategies agree and how strongly. It is a vote count, not a probability —
    presenting it as one would overstate what a nine-strategy panel knows.
    """
    buys = [s for s in signals if s.action is SignalAction.BUY]
    sells = [s for s in signals if s.action is SignalAction.SELL]
    reasons = [f"{s.strategy}:{s.action.value.lower()}" for s in signals if s.action is not SignalAction.HOLD]

    if not signals:
        return HOLD, 1, reasons

    if len(buys) > len(sells):
        strength = sum(s.strength for s in buys) / len(buys)
        conviction = min(5, max(1, len(buys) + (1 if strength >= 0.6 else 0)))
        return ACCUMULATE, conviction, reasons
    if len(sells) > len(buys):
        strength = sum(s.strength for s in sells) / len(sells)
        conviction = min(5, max(1, len(sells) + (1 if strength >= 0.6 else 0)))
        return REDUCE, conviction, reasons
    if buys and sells:
        # A split panel is a real answer: nobody has an edge here today.
        return HOLD, 2, reasons
    return HOLD, 1, reasons


def _expected_outcome(
    engine: CostEngine,
    *,
    entry: float,
    exit_price: float,
    quantity: int,
    holding_days: int,
) -> dict[str, Decimal]:
    """PnL at *exit_price*, net of entry costs, exit costs and CGT.

    The gross figure is what a naive spreadsheet shows; the net figure is what
    lands in the bank. On small NEPSE lots the gap is large enough to flip a
    plausible-looking trade negative, which is the whole reason this is computed
    up front rather than at exit.
    """
    buy = engine.compute(OrderSide.BUY, entry, quantity)
    basis = buy.net_amount
    sell = engine.compute(
        OrderSide.SELL,
        exit_price,
        quantity,
        buy_cost_basis=basis,
        holding_days=holding_days,
    )
    gross = _to_money(Decimal(str(exit_price)) * quantity - Decimal(str(entry)) * quantity)
    return {
        "gross_pnl": gross,
        "net_pnl": _to_money(sell.net_amount - basis),
        "entry_cost": _to_money(buy.net_amount - buy.gross_amount),
        "exit_cost": _to_money(sell.total_fees - sell.cgt),
        "capital_gains_tax": sell.cgt,
    }


def build_plan_card(
    symbol: str,
    bars: list[PriceBar],
    signals: list[Signal],
    *,
    equity: float,
    today: date | None = None,
    cost_engine: CostEngine | None = None,
    risk_per_trade_pct: float = 2.0,
    lot_size: int = 10,
    horizon_days: int = 10,
    atr_multiple: float = 2.0,
    risk_reward: float = 2.0,
    confidence: Confidence | float | None = None,
    confidence_for: Callable[..., Confidence | float] | None = None,
) -> PlanCard | Skipped:
    """Build one symbol's card, or explain why it can't be built.

    *today* defaults to the last bar's date rather than the wall clock, so a
    report generated on a holiday still settles from the session it describes.
    """
    if len(bars) < _MIN_BARS:
        return Skipped(symbol, f"only {len(bars)} bars; need {_MIN_BARS} for an ATR-based stop")

    last = bars[-1]
    if last.close is None or last.close <= 0:
        return Skipped(symbol, "latest bar has no usable close")

    price = float(last.close)
    atr = _latest_atr(bars)
    if atr is None or atr <= 0:
        return Skipped(symbol, "ATR unavailable (incomplete high/low/close history)")

    action, conviction, reasons = _decide(signals)
    trade_date = today or last.business_date

    if confidence_for is not None:
        confidence = confidence_for(
            symbol=symbol,
            action=action,
            horizon_days=horizon_days,
            conviction=conviction,
        )
    if isinstance(confidence, Confidence):
        forecast_confidence = market(
            confidence.value,
            confidence.basis,
            sample_size=confidence.sample_size,
        )
    elif confidence is not None:
        forecast_confidence = market(float(confidence), "caller-supplied forecast confidence")
    else:
        forecast_confidence = market(
            DEFAULT_PRIOR,
            "no resolved comparable predictions; house prior",
        )

    stop = stop_loss_price(price, atr=atr, atr_multiple=atr_multiple)
    if stop is None:
        return Skipped(symbol, "no stop could be computed")

    # The zone spans a quarter-ATR either side of the close: wide enough to fill,
    # tight enough that the stop distance still means something.
    half = atr * 0.25
    entry_low = round(price - half, 2)
    entry_high = round(price + half, 2)

    target_1 = take_profit_price(price, risk_reward=risk_reward, atr=atr, atr_multiple=atr_multiple)
    targets = [t for t in (target_1,) if t is not None]
    if target_1 is not None:
        second = round(price + (target_1 - price) * 1.75, 2)
        targets.append(second)

    quantity = size_position(
        equity,
        entry_high,
        risk_per_trade_pct=risk_per_trade_pct,
        lot_size=lot_size,
        atr=atr,
        atr_multiple=atr_multiple,
    )
    if action == ACCUMULATE and quantity <= 0:
        return Skipped(
            symbol,
            f"risk budget of {risk_per_trade_pct}% on equity {equity:,.0f} buys less than one lot",
        )

    engine = cost_engine or CostEngine()
    outcome = (
        _expected_outcome(
            engine,
            entry=entry_high,
            exit_price=targets[0],
            quantity=quantity,
            holding_days=horizon_days,
        )
        if quantity > 0 and targets
        else {}
    )

    rationale = "; ".join(reasons) if reasons else "no strategy fired; carried as hold"

    return PlanCard(
        symbol=symbol,
        action=action,
        reference_price=round(price, 2),
        entry_low=entry_low,
        entry_high=entry_high,
        stop=stop,
        targets=targets,
        quantity=quantity,
        horizon_days=horizon_days,
        earliest_sell_date=add_trading_days(trade_date, SETTLEMENT_TRADING_DAYS),
        conviction=conviction,
        rationale=rationale,
        confidence=forecast_confidence,
        signals=reasons,
        **outcome,
    )


def build_plan_cards(
    symbols: list[str],
    bars_for: object,
    signals_for: object,
    *,
    equity: float,
    today: date | None = None,
    cost_engine: CostEngine | None = None,
    **kwargs,
) -> tuple[list[PlanCard], list[Skipped]]:
    """Build cards for *symbols*, returning the cards and the skips separately.

    *bars_for* and *signals_for* are callables taking a symbol — injected rather
    than reached for, so the engine can be tested without a pipeline and a DB.
    """
    cards: list[PlanCard] = []
    skipped: list[Skipped] = []
    engine = cost_engine or CostEngine()
    for symbol in symbols:
        result = build_plan_card(
            symbol,
            list(bars_for(symbol)),
            list(signals_for(symbol)),
            equity=equity,
            today=today,
            cost_engine=engine,
            **kwargs,
        )
        if isinstance(result, Skipped):
            skipped.append(result)
        else:
            cards.append(result)
    return cards, skipped
