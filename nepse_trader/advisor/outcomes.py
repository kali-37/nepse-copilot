"""Score advisor predictions against subsequent market bars.

This module is intentionally deterministic and side-effect free by default.  A
prediction is a row-like object (a ``dict``, ``sqlite3.Row`` or a normal object)
with the fields written by the ``predictions`` migration.  The scorer replays
bars in date order, checks the stop before the target on every bar, and uses the
same :class:`~nepse_trader.analysis.costs.CostEngine` path as the plan engine
for realised PnL.

The narrow meaning of a hit matters: only ``TARGET_HIT`` has ``hit == 1``.
``EXPIRED_UP`` is useful information but is a partial, not a win; unresolved
and missing-data calls carry ``hit is None`` and must not enter calibration.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from nepse_trader.advisor.plan import _expected_outcome
from nepse_trader.analysis.costs import CostEngine, _to_money
from nepse_trader.calendar import add_trading_days
from nepse_trader.models import PriceBar


class Outcome(str, Enum):
    """The terminal state of one prediction."""

    TARGET_HIT = "TARGET_HIT"
    STOP_HIT = "STOP_HIT"
    EXPIRED_UP = "EXPIRED_UP"
    EXPIRED_DOWN = "EXPIRED_DOWN"
    EXPIRED_FLAT = "EXPIRED_FLAT"
    UNRESOLVED = "UNRESOLVED"
    NO_DATA = "NO_DATA"
    NOT_ENTERED = "NOT_ENTERED"
    EXCLUDED = "EXCLUDED"


# String aliases make the public contract convenient for SQLite and callers
# that do not want to import the enum.  Enum members compare equal to these
# strings because Outcome subclasses str.
TARGET_HIT = Outcome.TARGET_HIT.value
STOP_HIT = Outcome.STOP_HIT.value
EXPIRED_UP = Outcome.EXPIRED_UP.value
EXPIRED_DOWN = Outcome.EXPIRED_DOWN.value
EXPIRED_FLAT = Outcome.EXPIRED_FLAT.value
UNRESOLVED = Outcome.UNRESOLVED.value
NO_DATA = Outcome.NO_DATA.value
NOT_ENTERED = Outcome.NOT_ENTERED.value
EXCLUDED = Outcome.EXCLUDED.value

# Names used by a few integrations/documentation drafts.
OutcomeStatus = Outcome
PredictionOutcome = Outcome


_CALIBRATION_OUTCOMES = frozenset(
    {
        TARGET_HIT,
        STOP_HIT,
        EXPIRED_UP,
        EXPIRED_DOWN,
        EXPIRED_FLAT,
    }
)


def _value(obj: object, key: str, default: Any = None) -> Any:
    """Read *key* from mappings, sqlite rows, pydantic models or objects."""

    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    # sqlite3.Row implements ``keys`` and indexed access, but is not a Mapping.
    try:
        keys = obj.keys()  # type: ignore[attr-defined]
    except (AttributeError, TypeError):
        keys = ()
    if key in keys:
        try:
            return obj[key]  # type: ignore[index]
        except (KeyError, IndexError):
            return default
    return getattr(obj, key, default)


def _date(value: object | None) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _number(value: object | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None  # NaN is not a market value.


def _target(prediction: object) -> float | None:
    target = _number(_value(prediction, "target_1"))
    if target is not None:
        return target
    targets = _value(prediction, "targets")
    if isinstance(targets, (list, tuple)) and targets:
        return _number(targets[0])
    return None


def _prediction_symbol(prediction: object) -> str:
    return str(_value(prediction, "symbol", "")).strip().upper()


def _is_short(prediction: object) -> bool:
    action = str(_value(prediction, "action", "")).strip().lower()
    # Advisor cards represent long NEPSE holdings. ``reduce``/``exit``/``sell``
    # describe closing that long, not opening a short; only an explicit
    # ``short`` action uses inverse stop/target semantics for integrations that
    # opt into it deliberately.
    return action == "short"


@dataclass(frozen=True)
class OutcomeResult:
    """A score that can be copied directly into ``predictions``."""

    prediction_id: str = ""
    symbol: str = ""
    outcome: str = NO_DATA
    hit: int | None = None
    resolved_on: date | None = None
    realized_exit_price: float | None = None
    realized_net_pnl: Decimal | None = None
    mfe: float | None = None
    mae: float | None = None
    bars_seen: int = 0
    basis: str = ""
    scored_at: datetime | None = None
    entry_on: date | None = None
    entry_price: float | None = None
    net_return_pct: float | None = None
    benchmark_return_pct: float | None = None

    @property
    def status(self) -> str:
        """Alias used by lifecycle code."""
        return self.outcome

    @property
    def calibration_eligible(self) -> bool:
        return self.outcome in _CALIBRATION_OUTCOMES and self.hit is not None

    @property
    def partial(self) -> bool:
        return self.outcome == EXPIRED_UP

    @property
    def exit_price(self) -> float | None:
        """Short alias used by older journal adapters."""

        return self.realized_exit_price

    @property
    def max_favourable(self) -> float | None:
        return self.mfe

    @property
    def max_adverse(self) -> float | None:
        return self.mae

    def as_dict(self) -> dict[str, object]:
        return {
            "prediction_id": self.prediction_id,
            "symbol": self.symbol,
            "outcome": self.outcome,
            "hit": self.hit,
            "resolved_on": self.resolved_on.isoformat() if self.resolved_on else None,
            "realized_exit_price": self.realized_exit_price,
            "realized_exit": self.realized_exit_price,
            "exit_price": self.realized_exit_price,
            "realized_net_pnl": (
                float(self.realized_net_pnl) if self.realized_net_pnl is not None else None
            ),
            "mfe": self.mfe,
            "mae": self.mae,
            "max_favourable": self.mfe,
            "max_adverse": self.mae,
            "bars_seen": self.bars_seen,
            "basis": self.basis,
            "scored_at": self.scored_at.isoformat() if self.scored_at else None,
            "entry_on": self.entry_on.isoformat() if self.entry_on else None,
            "entry_price": self.entry_price,
            "net_return_pct": self.net_return_pct,
            "benchmark_return_pct": self.benchmark_return_pct,
        }


# A spelling used in early API sketches; retaining it costs nothing and keeps
# integrations source-compatible.
ScoredPrediction = OutcomeResult


def _result(
    prediction: object,
    outcome: str,
    *,
    hit: int | None,
    resolved_on: date | None,
    exit_price: float | None,
    net_pnl: Decimal | None,
    mfe: float | None,
    mae: float | None,
    bars_seen: int,
    basis: str,
    scored_at: datetime | None,
) -> OutcomeResult:
    return OutcomeResult(
        prediction_id=str(_value(prediction, "prediction_id", "")),
        symbol=_prediction_symbol(prediction),
        outcome=outcome,
        hit=hit,
        resolved_on=resolved_on,
        realized_exit_price=exit_price,
        realized_net_pnl=net_pnl,
        mfe=round(mfe, 6) if mfe is not None else None,
        mae=round(mae, 6) if mae is not None else None,
        bars_seen=bars_seen,
        basis=basis,
        scored_at=scored_at,
    )


def _realized_net_pnl(
    prediction: object,
    exit_price: float | None,
    resolved_on: date | None,
    engine: CostEngine,
) -> Decimal | None:
    """Re-use the plan's buy-basis → sell-proceeds accounting path."""

    if exit_price is None or resolved_on is None:
        return None
    quantity_raw = _value(prediction, "quantity", 0)
    try:
        quantity = int(quantity_raw or 0)
    except (TypeError, ValueError):
        quantity = 0
    entry = _number(_value(prediction, "entry_high"))
    if entry is None:
        entry = _number(_value(prediction, "entry_price"))
    if entry is None:
        entry = _number(_value(prediction, "reference_price"))
    if quantity <= 0 or entry is None or entry <= 0 or exit_price <= 0:
        return None

    made_on = _date(_value(prediction, "made_on")) or resolved_on
    holding_days = max(0, (resolved_on - made_on).days)
    # Keep this call structurally identical to advisor.plan::_expected_outcome.
    outcome = _expected_outcome(
        engine,
        entry=entry,
        exit_price=exit_price,
        quantity=quantity,
        holding_days=holding_days,
    )
    return _to_money(outcome["net_pnl"])


def score_prediction(
    prediction: object,
    bars: list[PriceBar] | tuple[PriceBar, ...],
    *,
    cost_engine: CostEngine | None = None,
    as_of: date | datetime | None = None,
    now: datetime | None = None,
) -> OutcomeResult:
    """Replay *bars* and return the deterministic outcome for *prediction*.

    Bars are considered only strictly after ``made_on`` and on or before the
    prediction deadline.  If the available tape has not reached the deadline,
    the call remains ``UNRESOLVED``; an empty/invalid future tape is
    ``NO_DATA``.  A trigger bar that spans both stop and target always exits at
    the stop, the conservative fill mandated by the journal contract.
    """

    if _value(prediction, "kind") == "decision_v1":
        from nepse_trader.advisor.track_record import evaluate_recommendation
        return evaluate_recommendation(prediction, list(bars), as_of=_date(as_of), cost_engine=cost_engine)
    symbol = _prediction_symbol(prediction)
    made_on = _date(_value(prediction, "made_on"))
    if made_on is None:
        made_on = _date(_value(prediction, "business_date"))

    if made_on is None:
        # Without an anchor date we cannot know whether a bar is future data.
        return _result(
            prediction,
            NO_DATA,
            hit=None,
            resolved_on=None,
            exit_price=None,
            net_pnl=None,
            mfe=None,
            mae=None,
            bars_seen=0,
            basis="prediction has no made_on date",
            scored_at=now,
        )

    horizon_raw = _value(prediction, "horizon_days", 0)
    try:
        horizon_days = max(0, int(horizon_raw or 0))
    except (TypeError, ValueError):
        horizon_days = 0
    deadline = _date(_value(prediction, "deadline"))
    if deadline is None:
        deadline = add_trading_days(made_on, horizon_days)
    if deadline < made_on:
        raise ValueError("prediction deadline cannot precede made_on")

    cutoff = _date(as_of)
    if cutoff is None:
        # A mixed-symbol tape is a normal input for batch scoring.  A later bar
        # for another symbol must not make this call look as though its own
        # prediction window has elapsed.
        symbol_dates = [
            _date(b.business_date)
            for b in bars
            if (not symbol or b.symbol.strip().upper() == symbol)
            and _date(b.business_date) is not None
        ]
        cutoff = max(symbol_dates) if symbol_dates else None

    # Symbol and date filtering happen before trigger logic.  Sorting a copy
    # keeps the caller's list untouched and makes out-of-order feeds safe.
    future: list[PriceBar] = []
    for bar in sorted(bars, key=lambda item: item.business_date):
        if symbol and bar.symbol.strip().upper() != symbol:
            continue
        if bar.business_date <= made_on:
            continue
        if cutoff is not None and bar.business_date > cutoff:
            continue
        future.append(bar)

    eligible = [bar for bar in future if bar.business_date <= deadline]
    usable = [
        bar
        for bar in eligible
        if bar.high is not None and bar.low is not None and bar.close is not None
    ]
    if not usable:
        return _result(
            prediction,
            NO_DATA,
            hit=None,
            resolved_on=None,
            exit_price=None,
            net_pnl=None,
            mfe=None,
            mae=None,
            bars_seen=0,
            basis="no usable future bars through the prediction window",
            scored_at=now,
        )

    reference = _number(_value(prediction, "reference_price"))
    if reference is None:
        reference = _number(_value(prediction, "entry_high"))
    stop = _number(_value(prediction, "stop"))
    target = _target(prediction)
    short = _is_short(prediction)
    mfe: float | None = None
    mae: float | None = None
    engine = cost_engine or CostEngine()

    for bar in usable:
        if reference is not None:
            if short:
                favorable = max(0.0, reference - float(bar.low))
                adverse = max(0.0, float(bar.high) - reference)
            else:
                favorable = max(0.0, float(bar.high) - reference)
                adverse = max(0.0, reference - float(bar.low))
            mfe = favorable if mfe is None else max(mfe, favorable)
            mae = adverse if mae is None else max(mae, adverse)

        triggered: str | None = None
        exit_price: float | None = None
        if short:
            # Stop first is deliberately tested before target on a spanning bar.
            if stop is not None and float(bar.high) >= stop:
                triggered, exit_price = STOP_HIT, stop
            elif target is not None and float(bar.low) <= target:
                triggered, exit_price = TARGET_HIT, target
        else:
            if stop is not None and float(bar.low) <= stop:
                triggered, exit_price = STOP_HIT, stop
            elif target is not None and float(bar.high) >= target:
                triggered, exit_price = TARGET_HIT, target

        if triggered is not None:
            return _result(
                prediction,
                triggered,
                hit=1 if triggered == TARGET_HIT else 0,
                resolved_on=bar.business_date,
                exit_price=exit_price,
                net_pnl=_realized_net_pnl(prediction, exit_price, bar.business_date, engine),
                mfe=mfe,
                mae=mae,
                bars_seen=len([b for b in usable if b.business_date <= bar.business_date]),
                basis=(
                    "target reached before stop"
                    if triggered == TARGET_HIT
                    else "stop checked before target on each bar"
                ),
                scored_at=now,
            )

    # The tape must have reached the deadline before a no-trigger call can be
    # called expired.  `cutoff` permits callers replaying only a known prefix to
    # score it as unresolved even when the full list contains later bars.
    reached_deadline = cutoff is not None and cutoff >= deadline
    last = usable[-1]
    if not reached_deadline:
        return _result(
            prediction,
            UNRESOLVED,
            hit=None,
            resolved_on=None,
            exit_price=None,
            net_pnl=None,
            mfe=mfe,
            mae=mae,
            bars_seen=len(usable),
            basis=f"latest usable bar {last.business_date.isoformat()} is before deadline",
            scored_at=now,
        )

    exit_price = float(last.close)
    if reference is None:
        expiry = EXPIRED_FLAT
    elif short:
        if exit_price < reference:
            expiry = EXPIRED_UP
        elif exit_price > reference:
            expiry = EXPIRED_DOWN
        else:
            expiry = EXPIRED_FLAT
    elif exit_price > reference:
        expiry = EXPIRED_UP
    elif exit_price < reference:
        expiry = EXPIRED_DOWN
    else:
        expiry = EXPIRED_FLAT

    return _result(
        prediction,
        expiry,
        hit=0,
        resolved_on=last.business_date,
        exit_price=exit_price,
        net_pnl=_realized_net_pnl(prediction, exit_price, last.business_date, engine),
        mfe=mfe,
        mae=mae,
        bars_seen=len(usable),
        basis="deadline reached without stop or target",
        scored_at=now,
    )


def score_outcome(*args: Any, **kwargs: Any) -> OutcomeResult:
    """Compatibility alias for :func:`score_prediction`."""

    return score_prediction(*args, **kwargs)


def score_predictions(
    predictions: list[object] | tuple[object, ...],
    bars_for: object,
    *,
    cost_engine: CostEngine | None = None,
    as_of: date | datetime | None = None,
) -> list[OutcomeResult]:
    """Score several predictions, accepting either a bar list or a callback.

    ``bars_for`` may be a common iterable of bars or a callable receiving a
    symbol.  The callback form avoids accidentally scoring a symbol against
    another symbol's tape when a database query is used by the journal.
    """

    out: list[OutcomeResult] = []
    common = None if callable(bars_for) else list(bars_for)
    for prediction in predictions:
        bars = bars_for(_prediction_symbol(prediction)) if callable(bars_for) else common
        out.append(score_prediction(prediction, list(bars or []), cost_engine=cost_engine, as_of=as_of))
    return out


def _persist_evaluation(conn, prediction_id, result) -> None:
    entry_on = _date(_value(result, "entry_on"))
    if entry_on is None:
        return
    conn.execute(
        """UPDATE predictions SET evaluation_entry_on=?,evaluation_entry_price=?,
        evaluation_net_return=?,evaluation_benchmark_return=?,evaluation_note=?,
        evaluation_checked_at=? WHERE prediction_id=?""",
        (entry_on.isoformat(), _value(result, "entry_price"), _value(result, "net_return_pct"),
         _value(result, "benchmark_return_pct"), _value(result, "basis"),
         datetime.now(UTC).isoformat(), prediction_id),
    )


def persist_score(conn: object, result: OutcomeResult, *, scored_at: datetime | None = None) -> bool:
    """Update one ``predictions`` row with a score.

    A terminal score advances the journal row to ``scored``.  ``UNRESOLVED``
    and ``NO_DATA`` remain ``open``: they have not supplied an outcome and may
    be re-scored after later ingestion.  The function does not commit, so a
    caller can include it in its own journal transaction.  ``False`` means no
    matching prediction row existed.
    """

    prediction_id = result.prediction_id
    if not prediction_id:
        return False
    stamp = scored_at or result.scored_at or datetime.now(UTC)
    terminal = result.calibration_eligible or result.outcome in {NOT_ENTERED, EXCLUDED}
    cursor = conn.execute(
        """UPDATE predictions
           SET outcome=?, resolved_on=?, realized_exit_price=?, realized_net_pnl=?,
               mfe=?, mae=?, hit=?, bars_seen=?, status=CASE WHEN ? THEN 'scored' ELSE status END,
               scored_at=CASE WHEN ? THEN ? ELSE scored_at END
           WHERE prediction_id=?""",
        (
            result.outcome,
            result.resolved_on.isoformat() if result.resolved_on else None,
            result.realized_exit_price,
            str(result.realized_net_pnl) if result.realized_net_pnl is not None else None,
            result.mfe,
            result.mae,
            result.hit,
            result.bars_seen,
            terminal,
            terminal,
            stamp.isoformat(),
            prediction_id,
        ),
    )
    updated = bool(getattr(cursor, "rowcount", 0))
    if updated:
        _persist_evaluation(conn, prediction_id, result)
    if updated and terminal:
        # Keep the materialised calibration table correct when this lower-level
        # helper is used directly.  Importing lazily avoids a module cycle and
        # keeps the pure scorer independent of SQLite/RAG at import time.
        try:
            from nepse_trader.advisor.journal import _fetch, _refresh_calibration

            row = _fetch(conn, prediction_id)
            _refresh_calibration(conn, int(row["id"]))
        except (ImportError, AttributeError, KeyError, sqlite3.Error):
            # A lightweight test connection may have only the predictions
            # table.  The score itself is still valid; the journal entrypoint
            # owns calibration when its schema is available.
            pass
    return updated


score_and_persist = persist_score


__all__ = [
    "Outcome",
    "OutcomeStatus",
    "PredictionOutcome",
    "OutcomeResult",
    "ScoredPrediction",
    "TARGET_HIT",
    "STOP_HIT",
    "EXPIRED_UP",
    "EXPIRED_DOWN",
    "EXPIRED_FLAT",
    "UNRESOLVED",
    "NO_DATA",
    "NOT_ENTERED",
    "EXCLUDED",
    "score_prediction",
    "score_outcome",
    "score_predictions",
    "persist_score",
    "score_and_persist",
]
