"""Offline model evaluation and advisory activation."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from nepse_trader.storage.research import (
    deploy_model,
    disable_model,
    list_models,
    model_record,
    save_model,
)

router = APIRouter(prefix="/api/research/models", tags=["model-validation"])
_NEPAL = ZoneInfo("Asia/Kathmandu")
_STOCK_SECTORS = {
    "commercial banks",
    "development bank limited",
    "finance",
    "microfinance",
    "hydro power",
    "life insurance",
    "non-life insurance",
    "hotels and tourism",
    "manufacturing and processing",
    "investment",
    "tradings",
    "others",
}


class TrainingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    horizon_days: Literal[3, 22] = 3
    max_symbols: int = Field(150, ge=10, le=200)
    max_sessions: int = Field(1000, ge=200, le=2000)


def model_summary(artifact: dict) -> dict:
    metrics = artifact["test_metrics"]
    calibrated, baseline = metrics["calibrated"], metrics["base_rate"]
    selected = metrics["model_selected"]
    sampling = artifact["sampling"]
    attempts = sampling.get("attempted_calls", 0)
    bounds = artifact["boundaries"]
    return {
        "gate": artifact["promotion_gate"],
        "metrics": {
            "test_samples": calibrated["samples"],
            "test_dates": calibrated["distinct_dates"],
            "brier_score": calibrated["brier"],
            "baseline_brier_score": baseline["brier"],
            "log_loss": calibrated["log_loss"],
            "baseline_log_loss": baseline["log_loss"],
            "ece": calibrated["ece"],
            "auc": calibrated["auc"],
            "selected_trades": selected["samples"],
            "mean_net_return": selected["mean_net_return_pct"],
            "coverage": sampling.get("eligible_calls", 0) / attempts if attempts else 0,
        },
        "boundaries": {
            "train_end": bounds["train"]["end"],
            "calibration_end": bounds["calibration"]["end"],
            "test_end": bounds["test"]["label_end"],
        },
        "event": artifact["event"],
        "limitations": artifact["limitations"],
        "diagnostics": {
            "reliability": calibrated["reliability"],
            "sampling": sampling,
            "partitions": {key: bounds[key] for key in ("train", "calibration", "test")},
            "raw": metrics["raw"],
            "chart_rule_baseline": metrics["chart_rule_baseline"],
            "calibration_base_rate": metrics["calibration_base_rate"],
            "matched_hold_mean_return_pct": metrics["matched_hold_mean_return_pct"],
            "date_block_uncertainty": metrics.get("date_block_uncertainty"),
            "dataset_fingerprint": artifact["dataset_fingerprint"],
            "policy_fingerprint": artifact["policy_fingerprint"],
        },
    }


def train_model_job(ctx) -> dict:
    from nepse_trader.advisor.decision_state import market_date, session_dates
    from nepse_trader.advisor.fundamentals import is_mutual_fund
    from nepse_trader.analysis.model_validation import build_examples, fit_validated_model
    from nepse_trader.calendar import previous_trading_day
    from nepse_trader.pipeline import DailyPipeline

    params = TrainingRequest.model_validate(ctx.params)
    today = datetime.now(_NEPAL).date()
    cutoff = (
        today
        if session_dates(today)[2] == "after_close"
        else previous_trading_day(today - timedelta(days=1))
    )
    pipe = DailyPipeline(ctx.settings, ctx.storage, clients=[])
    with ctx.stage("data") as stage:
        # Keep the universe, prices and actions on one WAL snapshot while reading.
        conn = ctx.storage._conn
        conn.execute("BEGIN")
        try:
            completed = market_date(ctx.storage, cutoff)
            if completed is None:
                raise ValueError("Download and reconcile market history before evaluating a model.")
            snapshots = ctx.storage.fundamentals(as_of=today)
            names = sorted(
                symbol
                for symbol, facts in snapshots.items()
                if facts.sector.casefold().strip() in _STOCK_SECTORS and not is_mutual_fund(facts)
            )[: params.max_symbols]
            if not names:
                raise ValueError("Download company sector data to identify eligible stocks.")
            histories, actions = {}, {}
            for index, symbol in enumerate(names, 1):
                ctx.progress(index, len(names), symbol)
                histories[symbol] = pipe.reconciled_bars(
                    symbol, adjusted=False, as_of=completed, limit=params.max_sessions
                )
                actions[symbol] = ctx.storage.corporate_actions(symbol)
        finally:
            conn.rollback()
        stage.detail = f"{len(names)} classified stocks, latest completed prices {completed}"
    with ctx.stage("examples") as stage:
        dataset = build_examples(
            histories,
            eligible_symbols=names,
            completed_through=completed,
            horizon_days=params.horizon_days,
            corporate_actions=actions,
            cost_engine=pipe.cost_engine,
        )
        stage.detail = f"{len(dataset.examples)} eligible labeled trades"
    with ctx.stage("fit") as stage:
        artifact = fit_validated_model(dataset)
        stage.detail = "Completed training, calibration and held-out testing"
    with ctx.stage("save") as stage:
        summary = save_model(ctx.storage, artifact, model_summary(artifact))
        stage.detail = (
            "Passed historical validation"
            if summary["gate"]["passed"]
            else "Held-out validation blocked activation"
        )
    return {"model": summary}


@router.get("")
def models():
    from nepse_trader.web.api import _storage

    return list_models(_storage())


@router.get("/{model_id}")
def model_details(model_id: str):
    from nepse_trader.web.api import _storage

    try:
        return model_record(_storage(), model_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/{model_id}/activate")
def activate_model(model_id: str):
    from nepse_trader.web.api import _storage

    try:
        return deploy_model(_storage(), model_id, today=datetime.now(_NEPAL).date())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.delete("/active/{horizon_days}")
def deactivate_model(horizon_days: int):
    from nepse_trader.web.api import _storage

    if horizon_days not in (3, 22):
        raise HTTPException(400, "Use a 3- or 22-session horizon.")
    disable_model(_storage(), horizon_days)
    return {"disabled": True}
