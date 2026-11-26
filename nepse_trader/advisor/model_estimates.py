"""Attach an activated model's separate benchmark estimate to shortlisted ideas."""

from __future__ import annotations

from datetime import date, timedelta

from nepse_trader.analysis.model_validation import (
    FEATURE_LOOKBACK,
    ModelValidationError,
    predict_probability,
)
from nepse_trader.calendar import next_trading_day
from nepse_trader.storage.research import active_models


def attach_model_estimates(
    pipe,
    ideas: dict[str, list[dict]],
    *,
    today: date,
    observed: date | None,
    completed: date,
    entry_on: date,
) -> None:
    if (
        observed is None
        or observed != completed
        or entry_on != next_trading_day(observed + timedelta(days=1))
        or not any(ideas.values())
    ):
        return
    models = active_models(pipe.storage, eligible_on=today)
    for candidates in ideas.values():
        for idea in candidates:
            artifact = models.get(idea["horizon_days"])
            if artifact is None:
                continue
            symbol = idea["symbol"]
            try:
                estimate = predict_probability(
                    artifact,
                    pipe.reconciled_bars(
                        symbol, adjusted=False, as_of=observed, limit=FEATURE_LOOKBACK
                    ),
                    as_of=observed,
                    corporate_actions=pipe.storage.corporate_actions(symbol),
                    cost_engine=pipe.cost_engine,
                )
            except ModelValidationError:
                # Stale or out-of-domain inputs have no supported probability.
                continue
            idea["model_estimate"] = estimate
