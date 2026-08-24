"""Nested, horoscope-shaped investment prescriptions.

The four doses are different holding horizons over one capital pool.  They are
not four independent portfolios: a card is assigned to exactly one horizon and
the allocation fractions are checked before anything is persisted.  This keeps
the headline expected PnL honest and prevents accidental double counting.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from nepse_trader.advisor.confidence import (
    DEFAULT_PRIOR,
    Confidence,
    market,
    penalise,
)
from nepse_trader.analysis.costs import CostEngine, _to_money
from nepse_trader.calendar import add_trading_days
from nepse_trader.models import OrderSide

# Trading-day horizons are part of the public contract.  Keep insertion order:
# it is also the report order and the deterministic tie-break order.
DOSE_HORIZONS: dict[str, int] = {"day": 3, "week": 10, "month": 22, "year": 250}
DOSE_ALLOCATION: dict[str, float] = {"day": 0.10, "week": 0.20, "month": 0.30, "year": 0.40}
_DOSE_ORDER = tuple(DOSE_HORIZONS)
_PENALTIES = {"day": 1.00, "week": 0.90, "month": 0.78, "year": 0.60}
_FORBIDDEN = re.compile(r"guaranteed?|sure|risk[- ]?free", re.IGNORECASE)


class DoseError(ValueError):
    """Raised when a dose invariant would be violated."""


def _decimal(value: object, default: Decimal = Decimal("0")) -> Decimal:
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default


def _money(value: object) -> Decimal:
    return _decimal(value).quantize(Decimal("0.01"))


def _date(value: date | str | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _safe_text(value: object) -> str:
    """Remove prohibited certainty language from user/AI prose."""
    text = str(value or "")
    return _FORBIDDEN.sub("uncertain", text)


def _card_value(card: object, name: str, default: object = None) -> object:
    if isinstance(card, Mapping):
        return card.get(name, default)
    return getattr(card, name, default)


def _card_horizon(card: object) -> str:
    """Map a card to one and only one configured horizon.

    An explicit ``horizon`` wins.  Otherwise the card's trading-day horizon is
    rounded upward to the first configured horizon; values outside the range
    are clamped to the nearest edge.  Thus even a malformed/zero-day card gets
    an auditable assignment instead of being dropped.
    """
    explicit = str(_card_value(card, "horizon", "") or "").strip().lower()
    if explicit in DOSE_HORIZONS:
        return explicit
    try:
        days = int(_card_value(card, "horizon_days", 0) or 0)
    except (TypeError, ValueError):
        days = 0
    for name, limit in DOSE_HORIZONS.items():
        if days <= limit:
            return name
    return "year"


def partition_cards(cards: Iterable[object]) -> dict[str, list[object]]:
    """Partition cards once, preserving order within each dose.

    The returned lists contain the original objects, not copies.  A caller can
    therefore audit identity as well as symbol membership.  Repeated entries in
    the input are treated as repeated cards and each occurrence is assigned once.
    """
    result = {name: [] for name in _DOSE_ORDER}
    for card in cards:
        result[_card_horizon(card)].append(card)
    return result


def _confidence_for_card(card: object, supplied: object | None) -> Confidence:
    if supplied is not None:
        if callable(supplied):
            value = supplied(card)
        elif isinstance(supplied, Mapping):
            symbol = str(_card_value(card, "symbol", "")).upper()
            horizon = _card_horizon(card)
            value = supplied.get(symbol, supplied.get(horizon, supplied.get("default")))
            if value is None:
                value = supplied
        else:
            method = getattr(supplied, "for_card", None) or getattr(supplied, "confidence_for", None)
            value = method(card) if callable(method) else supplied
    else:
        value = _card_value(card, "confidence", None)
        if value is None:
            # Conviction is an ordinal, not a probability.  It is only a useful
            # conservative fallback when no explicit confidence is available.
            conviction = _decimal(_card_value(card, "conviction", 0))
            value = min(0.79, max(DEFAULT_PRIOR, float(conviction / Decimal("5"))))
    if isinstance(value, Confidence):
        return value
    if isinstance(value, Mapping):
        value = value.get("value", DEFAULT_PRIOR)
    return market(float(value), "card confidence")


def _dose_confidence(
    cards: Sequence[object],
    horizon: str,
    confidence_for: object | None,
    base: Confidence | float | None,
) -> Confidence:
    if base is not None:
        root = base if isinstance(base, Confidence) else market(float(base), "supplied forecast confidence")
    elif cards:
        # Weakest card governs the dose; averaging would conceal a weak leg.
        root = min((_confidence_for_card(c, confidence_for) for c in cards), key=lambda c: c.value)
    else:
        root = market(DEFAULT_PRIOR, "no cards; house prior")
    return penalise(root, _PENALTIES[horizon], f"{horizon} horizon haircut")


def _sum_card_field(cards: Sequence[object], name: str) -> Decimal:
    return sum((_money(_card_value(card, name, 0)) for card in cards), Decimal("0"))


@dataclass
class Dose:
    """One horizon's disjoint subset of plan cards and expected arithmetic."""

    horizon: str
    horizon_days: int
    allocation_pct: float
    allocated_capital: Decimal
    cards: list[object] = field(default_factory=list)
    deployed_capital: Decimal = Decimal("0.00")
    expected_gross_pnl: Decimal = Decimal("0.00")
    expected_net_pnl: Decimal = Decimal("0.00")
    expected_return_pct: Decimal = Decimal("0.00")
    expected_costs: Decimal = Decimal("0.00")
    expected_tax: Decimal = Decimal("0.00")
    confidence: Confidence = field(default_factory=lambda: market(DEFAULT_PRIOR, "house prior"))
    earliest_sell_date: date | None = None
    reading: str = ""
    run_date: date | None = None
    warnings: list[str] = field(default_factory=list)
    guidance: list[str] = field(default_factory=list)

    @property
    def symbols(self) -> list[str]:
        return [str(_card_value(card, "symbol", "")) for card in self.cards]

    @property
    def card_count(self) -> int:
        return len(self.cards)

    @property
    def period(self) -> str:
        return self.horizon

    @property
    def label(self) -> str:
        return f"{self.horizon.title()} dose"

    @property
    def window_ends(self) -> date | None:
        return add_trading_days(self.run_date, self.horizon_days) if self.run_date else None

    @property
    def capital_allocated(self) -> Decimal:
        return self.allocated_capital

    @property
    def capital_deployed(self) -> Decimal:
        return self.deployed_capital

    @property
    def expected_return_percent(self) -> float:
        return float(self.expected_return_pct)

    @property
    def headline(self) -> str:
        return self.reading

    def as_dict(self) -> dict[str, Any]:
        return {
            "horizon": self.horizon,
            "horizon_days": self.horizon_days,
            "allocation_pct": self.allocation_pct,
            "allocated_capital": float(self.allocated_capital),
            "deployed_capital": float(self.deployed_capital),
            "symbols": list(self.symbols),
            "card_count": self.card_count,
            "cards": [c.as_dict() if hasattr(c, "as_dict") else dict(c) for c in self.cards],
            "expected_gross_pnl": float(self.expected_gross_pnl),
            "expected_net_pnl": float(self.expected_net_pnl),
            "expected_return_pct": float(self.expected_return_pct),
            "expected_costs": float(self.expected_costs),
            "expected_tax": float(self.expected_tax),
            "confidence": self.confidence.as_dict(),
            "earliest_sell_date": self.earliest_sell_date.isoformat()
            if self.earliest_sell_date
            else None,
            "reading": self.reading,
            "period": self.period,
            "label": self.label,
            "window_ends": self.window_ends.isoformat() if self.window_ends else None,
            "capital_allocated": float(self.capital_allocated),
            "capital_deployed": float(self.capital_deployed),
            "expected_return_percent": self.expected_return_percent,
            "headline": self.headline,
            "guidance": list(self.guidance),
            "warnings": list(self.warnings),
        }


@dataclass
class DoseRun:
    """All four nested doses over one capital pool."""

    run_date: date
    capital: Decimal
    doses: list[Dose]
    mode: str = "normal"
    banner: str = ""
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    run_id: int | None = None

    @property
    def deployed_capital(self) -> Decimal:
        return sum((d.deployed_capital for d in self.doses), Decimal("0.00"))

    @property
    def expected_net_pnl(self) -> Decimal:
        return sum((d.expected_net_pnl for d in self.doses), Decimal("0.00"))

    @property
    def expected_gross_pnl(self) -> Decimal:
        return sum((d.expected_gross_pnl for d in self.doses), Decimal("0.00"))

    @property
    def confidence(self) -> Confidence:
        if not self.doses:
            return market(0.0, "no doses")
        return min((d.confidence for d in self.doses), key=lambda c: c.value)

    @property
    def cards(self) -> list[object]:
        return [card for dose in self.doses for card in dose.cards]

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "run_date": self.run_date.isoformat(),
            "mode": self.mode,
            "capital": float(self.capital),
            "deployed_capital": float(self.deployed_capital),
            "expected_gross_pnl": float(self.expected_gross_pnl),
            "expected_net_pnl": float(self.expected_net_pnl),
            "confidence": self.confidence.as_dict(),
            "banner": self.banner,
            "generated_at": self.generated_at.isoformat(),
            "doses": [d.as_dict() for d in self.doses],
        }


@dataclass
class DoseReport:
    """Compatibility/reporting view of the four nested doses."""

    run_date: date
    equity: Decimal
    doses: list[Dose]
    total_expected_net_pnl: Decimal
    total_capital_deployed: Decimal
    cash_untouched: Decimal
    confidence: Confidence
    headline: str
    disclaimer: str
    warnings: list[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    run_id: int | None = None

    def by_period(self, period: str) -> Dose | None:
        period = str(period).lower()
        return next((dose for dose in self.doses if dose.period == period), None)

    # These aliases intentionally mirror ``DoseRun``.  The API and the first
    # frontend prototype consumed the run-shaped object; keeping the aliases
    # means the stricter budgeted report can be introduced without a breaking
    # response-shape change.
    @property
    def capital(self) -> Decimal:
        return self.equity

    @property
    def deployed_capital(self) -> Decimal:
        return self.total_capital_deployed

    @property
    def expected_net_pnl(self) -> Decimal:
        return self.total_expected_net_pnl

    @property
    def expected_gross_pnl(self) -> Decimal:
        return sum((d.expected_gross_pnl for d in self.doses), Decimal("0.00"))

    @property
    def mode(self) -> str:
        return "normal"

    @property
    def banner(self) -> str:
        return self.disclaimer

    @property
    def cards(self) -> list[object]:
        return [card for dose in self.doses for card in dose.cards]

    @property
    def guidance(self) -> list[str]:
        return [item for dose in self.doses for item in dose.guidance]

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "run_date": self.run_date.isoformat(),
            "mode": self.mode,
            "capital": float(self.equity),
            "equity": float(self.equity),
            "deployed_capital": float(self.total_capital_deployed),
            "expected_gross_pnl": float(self.expected_gross_pnl),
            "expected_net_pnl": float(self.total_expected_net_pnl),
            "doses": [dose.as_dict() for dose in self.doses],
            "total_expected_net_pnl": float(self.total_expected_net_pnl),
            "total_capital_deployed": float(self.total_capital_deployed),
            "cash_untouched": float(self.cash_untouched),
            "confidence": self.confidence.as_dict(),
            "headline": self.headline,
            "disclaimer": self.disclaimer,
            "banner": self.banner,
            "warnings": list(self.warnings),
            "guidance": list(self.guidance),
            "generated_at": self.generated_at.isoformat(),
        }


def _reading(dose: Dose) -> str:
    net = f"NPR {dose.expected_net_pnl:,.2f}"
    if dose.allocated_capital:
        return (
            f"{dose.horizon.title()} dose: allocate NPR {dose.allocated_capital:,.2f}; "
            f"{dose.card_count} card(s), estimated net outcome {net} over "
            f"about {dose.horizon_days} trading days. This is an uncertain estimate; "
            "losses remain possible and the position should be reviewed."
        )
    return (
        f"{dose.horizon.title()} dose: no allocation selected; no cards currently "
        f"fit the {dose.horizon_days}-trading-day horizon."
    )


def build_dose_run(
    cards: Sequence[object] | None = None,
    *,
    capital: float | Decimal = 0,
    run_date: date | str | None = None,
    allocations: Mapping[str, float] | None = None,
    mode: str = "normal",
    confidence: Confidence | float | None = None,
    confidence_for: Callable[[object], Confidence | float] | Confidence | float | None = None,
    readings: Mapping[str, str] | None = None,
    banner: str = "",
    run_id: int | None = None,
    _groups: Mapping[str, Sequence[object]] | None = None,
    **aliases: object,
) -> DoseRun:
    """Build the four dose cards from a disjoint card partition.

    ``equity``/``today`` are accepted as friendly aliases for ``capital`` and
    ``run_date`` so callers can pass the same settings used by the rashifal
    composer.
    """
    if capital == 0 and aliases.get("equity") is not None:
        capital = aliases["equity"]  # type: ignore[assignment]
    if run_date is None:
        run_date = aliases.get("today")  # type: ignore[assignment]
    day = _date(run_date) or date.today()
    cap = _money(capital)
    if cap < 0:
        raise DoseError("capital cannot be negative")
    alloc = _validated_allocations(allocations)

    # ``_groups`` is an internal hand-off for the budgeted builder.  It keeps
    # that public path's partition operation exactly once while preserving the
    # historical standalone API (which still partitions its own input).
    groups = (
        {horizon: list(_groups.get(horizon, ())) for horizon in _DOSE_ORDER}
        if _groups is not None
        else partition_cards(cards or [])
    )
    doses: list[Dose] = []
    previous_confidence: Confidence | None = None
    for horizon in _DOSE_ORDER:
        assigned = groups[horizon]
        allocated = _money(cap * _decimal(alloc[horizon]))
        deployed = sum(
            (_money(_card_value(card, "entry_high", _card_value(card, "reference_price", 0)))
             * int(_card_value(card, "quantity", 0) or 0) for card in assigned),
            Decimal("0.00"),
        )
        gross = _sum_card_field(assigned, "gross_pnl")
        net = _sum_card_field(assigned, "net_pnl")
        entry_cost = _sum_card_field(assigned, "entry_cost")
        exit_cost = _sum_card_field(assigned, "exit_cost")
        tax = _sum_card_field(assigned, "capital_gains_tax")
        earliest: date | None = None
        for card in assigned:
            value = _date(_card_value(card, "earliest_sell_date"))
            if value is not None and (earliest is None or value < earliest):
                earliest = value
        ret = (net / allocated * Decimal("100")) if allocated else Decimal("0")
        dose_confidence = _dose_confidence(assigned, horizon, confidence_for, confidence)
        if previous_confidence is not None and dose_confidence.value > previous_confidence.value:
            dose_confidence = market(
                previous_confidence.value,
                f"{dose_confidence.basis}; capped by shorter-horizon confidence",
            )
        previous_confidence = dose_confidence
        dose = Dose(
            horizon=horizon,
            horizon_days=DOSE_HORIZONS[horizon],
            allocation_pct=float(alloc[horizon]),
            allocated_capital=allocated,
            cards=list(assigned),
            deployed_capital=deployed,
            expected_gross_pnl=gross,
            expected_net_pnl=net,
            expected_return_pct=ret.quantize(Decimal("0.01")),
            expected_costs=entry_cost + exit_cost,
            expected_tax=tax,
            confidence=dose_confidence,
            earliest_sell_date=earliest,
            reading=_safe_text((readings or {}).get(horizon, "")) or "",
            run_date=day,
        )
        if not dose.reading:
            dose.reading = _reading(dose)
        doses.append(dose)

    return DoseRun(
        run_date=day,
        capital=cap,
        doses=doses,
        mode=mode,
        banner=_safe_text(banner),
        run_id=run_id,
    )


def _validated_allocations(allocation: Mapping[str, float] | None) -> dict[str, float]:
    """Validate the one shared-capital allocation map used by ``build_doses``."""
    raw = dict(DOSE_ALLOCATION if allocation is None else allocation)
    unknown = set(raw) - set(DOSE_HORIZONS)
    missing = set(DOSE_HORIZONS) - set(raw)
    if unknown or missing:
        raise DoseError(
            f"allocations must contain exactly {', '.join(_DOSE_ORDER)}; "
            f"unknown={sorted(unknown)}, missing={sorted(missing)}"
        )

    result: dict[str, float] = {}
    for horizon in _DOSE_ORDER:
        try:
            value = Decimal(str(raw[horizon]))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise DoseError(f"allocation for {horizon} must be numeric") from exc
        if not value.is_finite() or value < 0:
            raise DoseError("allocation fractions cannot be negative")
        result[horizon] = float(value)

    total = sum(result.values())
    if total > 1.0 + 1e-9:
        raise DoseError(f"dose allocations sum to {total:.6f}; maximum is 1.0")
    return result


def _report_as_run(report: DoseReport) -> DoseRun:
    """Adapt a budgeted report to the persisted ``dose_runs`` contract."""
    return DoseRun(
        run_date=report.run_date,
        capital=report.equity,
        doses=report.doses,
        mode=report.mode,
        banner=report.banner,
        generated_at=report.generated_at,
        run_id=report.run_id,
    )


def _entry_price(card: object) -> Decimal:
    value = _card_value(card, "entry_high", None)
    if value is None:
        value = _card_value(card, "reference_price", 0)
    return max(Decimal("0.00"), _money(value))


def _quantity(card: object) -> int:
    try:
        return max(0, int(Decimal(str(_card_value(card, "quantity", 0) or 0))))
    except (InvalidOperation, TypeError, ValueError):
        return 0


def _entry_cost(card: object, engine: CostEngine) -> Decimal:
    """Return a card's buy-side cost, deriving it when the card lacks one."""
    value = _card_value(card, "entry_cost", None)
    if value is not None and str(value).strip():
        return max(Decimal("0.00"), _money(value))

    price, quantity = _entry_price(card), _quantity(card)
    if price <= 0 or quantity <= 0:
        return Decimal("0.00")
    buy = engine.compute(OrderSide.BUY, price, quantity)
    return _to_money(buy.net_amount - buy.gross_amount)


def _entry_outlay(card: object, engine: CostEngine) -> Decimal:
    """All cash needed to open a card: shares plus the actual buy-side fee."""
    price, quantity = _entry_price(card), _quantity(card)
    if price <= 0 or quantity <= 0:
        return Decimal("0.00")
    return _to_money(price * quantity + _entry_cost(card, engine))


def _priority(card: object, confidence_source: object | None, index: int) -> tuple[float, float, float, str, int]:
    """Sort strongest cards first, with a stable final input-order tiebreak."""
    confidence = _confidence_for_card(card, confidence_source)
    conviction = _decimal(_card_value(card, "conviction", 0))
    net = _money(_card_value(card, "net_pnl", 0))
    symbol = str(_card_value(card, "symbol", "")).upper()
    return (-confidence.value, -float(conviction), -float(net), symbol, index)


def _select_affordable_cards(
    cards: Sequence[object],
    *,
    horizon: str,
    dose_budget: Decimal,
    total_remaining: Decimal,
    confidence_source: object | None,
    engine: CostEngine,
) -> tuple[list[object], list[str], Decimal]:
    """Keep the strongest cards that fit, reporting every omitted card."""
    ranked = sorted(
        enumerate(cards),
        key=lambda item: _priority(item[1], confidence_source, item[0]),
    )
    selected_indices: set[int] = set()
    warnings: list[str] = []
    deployed = Decimal("0.00")

    for index, card in ranked:
        symbol = str(_card_value(card, "symbol", "unnamed card")).upper()
        if _quantity(card) <= 0 or _entry_price(card) <= 0:
            warnings.append(
                f"{symbol}: omitted from {horizon} dose; entry price and quantity "
                "must both be positive."
            )
            continue
        outlay = _entry_outlay(card, engine)
        remaining_dose = dose_budget - deployed
        # The global pool is already reduced by prior horizons.  Do not
        # subtract this dose's local spend a second time; that would reject a
        # perfectly affordable second card and falsely report it as omitted.
        available = min(remaining_dose, total_remaining)
        if outlay <= available:
            selected_indices.add(index)
            deployed = _to_money(deployed + outlay)
            continue

        warnings.append(
            f"{symbol}: omitted from {horizon} dose; all-in entry NPR {outlay:,.2f} "
            f"exceeds remaining NPR {max(Decimal('0.00'), available):,.2f}."
        )

    # Keep the report's cards in the caller's order, rather than its internal
    # priority order. Ranking decides what fits; input order remains easier to
    # compare with the original prescription.
    selected = [card for index, card in enumerate(cards) if index in selected_indices]
    return selected, warnings, deployed


def _queue_items(sell_queue: Iterable[object] | Mapping[str, object] | None) -> list[object]:
    if sell_queue is None:
        return []
    if isinstance(sell_queue, Mapping):
        result: list[object] = []
        for symbol, item in sell_queue.items():
            if isinstance(item, Mapping):
                result.append({"symbol": symbol, **item})
            elif hasattr(item, "symbol"):
                result.append(item)
            else:
                result.append({"symbol": symbol, "quantity": item})
        return result
    return list(sell_queue)


def _guidance_horizon(item: object, doses: Sequence[Dose]) -> str:
    explicit = str(_card_value(item, "horizon", "") or "").strip().lower()
    if explicit in DOSE_HORIZONS:
        return explicit
    try:
        days = int(_card_value(item, "horizon_days", 0) or 0)
    except (TypeError, ValueError):
        days = 0
    if days > 0:
        return _card_horizon({"horizon_days": days})

    symbol = str(_card_value(item, "symbol", "")).upper()
    for dose in doses:
        if symbol and symbol in dose.symbols:
            return dose.horizon
    # An unassigned exit is urgent information, so keep it in the shortest
    # dose instead of hiding it behind an investment horizon it does not have.
    return "day"


def _add_sell_guidance(
    doses: Sequence[Dose], sell_queue: Iterable[object] | Mapping[str, object] | None
) -> None:
    by_horizon = {dose.horizon: dose for dose in doses}
    for item in _queue_items(sell_queue):
        horizon = _guidance_horizon(item, doses)
        dose = by_horizon[horizon]
        symbol = str(_card_value(item, "symbol", "position")).upper()
        quantity = _quantity(item)
        reason = _safe_text(_card_value(item, "reason", ""))
        earliest = _date(_card_value(item, "earliest_sell_date", None))
        text = f"Exit {symbol}"
        if quantity:
            text += f" ({quantity} shares)"
        if reason:
            text += f": {reason}"
        if earliest:
            text += f" Earliest sell date: {earliest.isoformat()}."
        dose.guidance.append(text)


def build_doses(
    *,
    cards: Sequence[object],
    equity: float | Decimal,
    run_date: date | str,
    sell_queue: Iterable[object] | Mapping[str, object] | None = None,
    confidence_source: Callable[[object], Confidence | float] | Confidence | float | None = None,
    allocation: Mapping[str, float] | None = None,
    cost_engine: CostEngine | None = None,
) -> DoseReport:
    """Build a budgeted four-horizon prescription over one capital pool.

    Unlike :func:`build_dose_run`, this is the beginner-facing entry point.  It
    treats a card's entry cost as real cash, selects the highest-confidence/
    highest-conviction cards that fit each allocation, and makes every omitted
    card visible in the resulting warnings.  No caller can accidentally turn
    four horizon cards into four independent piles of capital.
    """
    day = _date(run_date)
    if day is None:
        raise DoseError("run_date is required")
    capital = _money(equity)
    if capital < 0:
        raise DoseError("equity cannot be negative")
    allocations = _validated_allocations(allocation)
    engine = cost_engine or CostEngine()

    groups = partition_cards(cards)
    selected_groups: dict[str, list[object]] = {}
    warnings: list[str] = []
    total_remaining = capital
    for horizon in _DOSE_ORDER:
        budget = _money(capital * _decimal(allocations[horizon]))
        selected, omitted, deployed = _select_affordable_cards(
            groups[horizon],
            horizon=horizon,
            dose_budget=budget,
            total_remaining=total_remaining,
            confidence_source=confidence_source,
            engine=engine,
        )
        selected_groups[horizon] = selected
        warnings.extend(omitted)
        total_remaining = max(Decimal("0.00"), _to_money(total_remaining - deployed))

    selected_cards = [card for horizon in _DOSE_ORDER for card in selected_groups[horizon]]
    run = build_dose_run(
        selected_cards,
        capital=capital,
        run_date=day,
        allocations=allocations,
        confidence_for=confidence_source,
        _groups=selected_groups,
    )
    for dose in run.doses:
        entry_costs = sum((_entry_cost(card, engine) for card in dose.cards), Decimal("0.00"))
        dose.deployed_capital = sum(
            (_entry_outlay(card, engine) for card in dose.cards), Decimal("0.00")
        )
        dose.deployed_capital = _to_money(dose.deployed_capital)
        dose.expected_costs = _to_money(entry_costs + _sum_card_field(dose.cards, "exit_cost"))
        dose.warnings.extend(
            warning for warning in warnings if f" {dose.horizon} dose;" in warning
        )
        # Regenerate after all-in deployment has been computed, so the prose
        # and the tabular number cannot contradict one another.
        dose.reading = _reading(dose)

    _add_sell_guidance(run.doses, sell_queue)
    deployed = _to_money(sum((dose.deployed_capital for dose in run.doses), Decimal("0.00")))
    if deployed > capital:
        # This should be unreachable because selection applies both per-dose
        # and whole-pool caps. Keeping a hard assertion turns a future rounding
        # regression into a visible error instead of an overfunded suggestion.
        raise DoseError("selected doses exceed available equity")

    cash = _to_money(capital - deployed)
    total_net = _to_money(sum((dose.expected_net_pnl for dose in run.doses), Decimal("0.00")))
    selected_count = sum(dose.card_count for dose in run.doses)
    headline = (
        f"NPR {deployed:,.2f} of NPR {capital:,.2f} is assigned across four horizons "
        f"({selected_count} card(s)); estimated net outcome NPR {total_net:,.2f}."
    )
    disclaimer = (
        "This is an uncertain price-and-cost estimate, not a promise. Losses, gaps, "
        "liquidity and fees can change the outcome; review each manual order."
    )
    return DoseReport(
        run_date=day,
        equity=capital,
        doses=run.doses,
        total_expected_net_pnl=total_net,
        total_capital_deployed=deployed,
        cash_untouched=cash,
        confidence=run.confidence,
        headline=_safe_text(headline),
        disclaimer=_safe_text(disclaimer),
        warnings=warnings,
    )


# Friendly aliases used by CLI/API callers and by early prototypes.
build_prescription = build_dose_run
partition = partition_cards


def render_doses(result: DoseRun | DoseReport | Mapping[str, Any]) -> str:
    """Render all four horizons as safe beginner-facing prose."""
    data = (
        result.as_dict()
        if isinstance(result, (DoseRun, DoseReport))
        else dict(result)
    )
    capital = data.get("capital", data.get("equity", 0))
    lines = [
        f"Investment doses for {data.get('run_date', '')} (capital NPR {float(capital):,.2f})",
        "These are estimates from the deterministic plan engine, not promises; prices can move against you.",
    ]
    if data.get("headline"):
        lines.append(_safe_text(data["headline"]))
    if data.get("disclaimer"):
        lines.append(_safe_text(data["disclaimer"]))
    for warning in data.get("warnings", []) or []:
        lines.append(f"Warning: {_safe_text(warning)}")
    for guidance in data.get("guidance", []) or []:
        lines.append(f"Guidance: {_safe_text(guidance)}")
    doses = data.get("doses", []) or []
    by_horizon = {str(d.get("horizon")): d for d in doses if isinstance(d, Mapping)}
    for horizon in _DOSE_ORDER:
        d = by_horizon.get(horizon, {"horizon": horizon, "horizon_days": DOSE_HORIZONS[horizon]})
        reading = _safe_text(d.get("reading", ""))
        conf = d.get("confidence", {}) or {}
        value = conf.get("value", 0.0) if isinstance(conf, Mapping) else conf
        lines.append(
            f"\n{horizon.upper()} ({DOSE_HORIZONS[horizon]} trading days): "
            f"allocation {float(d.get('allocation_pct', 0.0)) * 100:.1f}%, "
            f"estimated net NPR {float(d.get('expected_net_pnl', 0.0)):,.2f}, "
            f"confidence {float(value):.2f}."
        )
        if reading:
            lines.append(reading)
    rendered = "\n".join(lines)
    # Defensive final pass: even a future renderer change cannot leak a banned
    # certainty claim into the user-facing report.
    return _FORBIDDEN.sub("uncertain", rendered)


def save_doses(
    conn: sqlite3.Connection,
    result: DoseRun | DoseReport,
    *,
    run_id: int | None = None,
) -> int:
    """Persist one dose run and exactly four child rows atomically."""
    persisted = _report_as_run(result) if isinstance(result, DoseReport) else result
    parent_run_id = run_id if run_id is not None else persisted.run_id
    with conn:
        cur = conn.execute(
            """
            INSERT INTO dose_runs
                (run_id, run_date, mode, capital, deployed_capital,
                 expected_net_pnl, confidence, confidence_band, banner, generated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                parent_run_id,
                persisted.run_date.isoformat(),
                persisted.mode,
                float(persisted.capital),
                float(persisted.deployed_capital),
                float(persisted.expected_net_pnl),
                persisted.confidence.value,
                persisted.confidence.band,
                persisted.banner or None,
                persisted.generated_at.isoformat(),
            ),
        )
        dose_run_id = int(cur.lastrowid)
        for dose in persisted.doses:
            conn.execute(
                """
                INSERT INTO doses
                    (dose_run_id, horizon, horizon_days, allocation_pct,
                     allocated_capital, deployed_capital, symbols, card_count,
                     expected_gross_pnl, expected_net_pnl, expected_return_pct,
                     expected_costs, expected_tax, confidence, confidence_band,
                     confidence_basis, earliest_sell_date, reading)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    dose_run_id,
                    dose.horizon,
                    dose.horizon_days,
                    dose.allocation_pct,
                    float(dose.allocated_capital),
                    float(dose.deployed_capital),
                    ",".join(dose.symbols),
                    dose.card_count,
                    float(dose.expected_gross_pnl),
                    float(dose.expected_net_pnl),
                    float(dose.expected_return_pct),
                    float(dose.expected_costs),
                    float(dose.expected_tax),
                    dose.confidence.value,
                    dose.confidence.band,
                    dose.confidence.basis,
                    dose.earliest_sell_date.isoformat() if dose.earliest_sell_date else None,
                    dose.reading,
                ),
            )
    persisted.run_id = dose_run_id
    if isinstance(result, DoseReport):
        result.run_id = dose_run_id
    return dose_run_id


def latest_dose_run(conn: sqlite3.Connection) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM dose_runs ORDER BY generated_at DESC, id DESC LIMIT 1").fetchone()
    if row is None:
        return None
    out = dict(row)
    out["doses"] = [
        dict(r)
        for r in conn.execute("SELECT * FROM doses WHERE dose_run_id=? ORDER BY id", (row["id"],)).fetchall()
    ]
    return out


def dose_history(conn: sqlite3.Connection, *, limit: int = 30) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM dose_runs ORDER BY generated_at DESC, id DESC LIMIT ?", (max(1, int(limit)),)
    ).fetchall()
    return [dict(r) for r in rows]


__all__ = [
    "DOSE_ALLOCATION",
    "DOSE_HORIZONS",
    "Dose",
    "DoseError",
    "DoseReport",
    "DoseRun",
    "build_dose_run",
    "build_doses",
    "build_prescription",
    "dose_history",
    "latest_dose_run",
    "partition",
    "partition_cards",
    "render_doses",
    "save_doses",
]
