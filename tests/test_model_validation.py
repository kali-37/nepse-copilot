"""A trained probability requires causal features and genuinely held-out outcomes."""

import copy
import math
from dataclasses import replace
from datetime import date, timedelta

import pytest
from freezegun import freeze_time

from nepse_trader.analysis.costs import CostEngine
from nepse_trader.analysis.model_validation import (
    FEATURE_LOOKBACK,
    FEATURE_NAMES,
    MODEL_VERSION,
    ModelExample,
    ModelValidationError,
    TrainingDataset,
    ValidationConfig,
    build_examples,
    chronological_split,
    fit_validated_model,
    label_policy_fingerprint,
    predict_probability,
    verify_model_artifact,
)
from nepse_trader.calendar import add_trading_days
from nepse_trader.models import CorporateAction, CorporateActionType, PriceBar, SourceName
from nepse_trader.storage.db import Storage
from nepse_trader.storage.research import active_models, deploy_model, disable_model, save_model
from nepse_trader.web.model_research import model_summary


def history(n=360, symbol="STOCK", oscillate=False):
    bars = []
    for i in range(n):
        close = 100 + (0.05 * i if not oscillate else 8 * math.sin(i / 10) + 0.015 * i)
        opened = bars[-1].close if bars else close
        bars.append(
            PriceBar(
                symbol=symbol,
                business_date=add_trading_days(date(2020, 1, 2), i),
                open=opened,
                close=close,
                high=max(close, opened) + 1,
                low=min(close, opened) - 1,
                volume=30000,
                source=SourceName.MANUAL,
            )
        )
    return bars


@pytest.fixture(scope="module")
def dataset():
    rows = []
    for i in range(300):
        for j, symbol in enumerate(("STOCK", "BANK", "OTHER", "FOURTH")):
            day = add_trading_days(date(2020, 1, 2), i * 4 + j)
            label = (i + j) % 2
            sign = 1 if label else -1
            features = (
                sign * 0.03,
                sign * 0.05,
                sign * 0.04,
                sign * 0.2,
                0.015 + 0.002 * math.cos(i),
                0.7 + 0.1 * math.sin(i),
                10.3 + 0.2 * math.sin(i),
                sign * 0.008,
            )
            rows.append(
                ModelExample(
                    symbol,
                    day,
                    add_trading_days(day, 3),
                    features,
                    label,
                    5.0 if label else -3.0,
                    1.0 if label else -0.5,
                    0.8 if label else 0.3,
                )
            )
    return TrainingDataset(
        tuple(rows),
        3,
        max(r.label_end for r in rows),
        {"eligible_calls": len(rows), "attempted_calls": len(rows)},
        label_policy_fingerprint(3),
    )


@pytest.fixture(scope="module")
def artifact(dataset):
    return fit_validated_model(dataset)


def test_global_date_split_keeps_same_day_stocks_together_and_purges_overlapping_labels(dataset):
    train, calibration, test, bounds = chronological_split(dataset, ValidationConfig())
    calibration_start = date.fromisoformat(bounds["calibration_start"])
    test_start = date.fromisoformat(bounds["test_start"])
    assert max(e.label_end for e in train) < calibration_start
    assert max(e.label_end for e in calibration) < test_start
    assert min(e.observed_on for e in test) == test_start
    assert not set(e.observed_on for e in train) & set(e.observed_on for e in calibration)
    assert not set(e.observed_on for e in calibration) & set(e.observed_on for e in test)
    assert bounds["purged_examples"] > 0


def test_missing_outcomes_cannot_move_attempted_date_split_boundaries(dataset):
    attempted_dates = tuple(sorted({e.observed_on for e in dataset.examples}))
    without_outcomes = tuple(e for e in dataset.examples if e.observed_on > attempted_dates[30])
    before = chronological_split(
        replace(dataset, attempted_dates=attempted_dates), ValidationConfig()
    )
    after = chronological_split(
        replace(dataset, attempted_dates=attempted_dates, examples=without_outcomes),
        ValidationConfig(),
    )
    for key in ("calibration_start", "test_start", "anchor_dates_fingerprint"):
        assert before[3][key] == after[3][key]


def test_training_is_real_and_artifact_contains_calibration_and_held_out_baselines(artifact):
    assert artifact["version"] == MODEL_VERSION
    assert any(abs(w) > 0.01 for w in artifact["classifier"]["weights"])
    assert artifact["calibration"]["method"] == "Platt, calibration partition only"
    metrics = artifact["test_metrics"]
    assert metrics["calibrated"]["brier"] < metrics["base_rate"]["brier"]
    assert metrics["calibrated"]["log_loss"] < metrics["base_rate"]["log_loss"]
    assert metrics["calibrated"]["brier"] < metrics["calibration_base_rate"]["brier"]
    assert metrics["calibrated"]["samples"] >= 150
    assert metrics["calibrated"]["auc"] > metrics["base_rate"]["auc"]
    assert metrics["model_selected"]["mean_net_return_pct"] == 5
    assert artifact["promotion_gate"]["passed"]
    assert artifact["config"]["minimum_test_auc"] == 0.55
    verify_model_artifact(artifact)


def test_test_labels_do_not_change_scaler_training_or_calibration(dataset, artifact):
    test_start = date.fromisoformat(artifact["boundaries"]["test_start"])
    rows = tuple(
        replace(e, label=1 - e.label, net_return_pct=5 if e.label == 0 else -3)
        if e.observed_on >= test_start
        else e
        for e in dataset.examples
    )
    changed = fit_validated_model(replace(dataset, examples=rows))
    assert changed["scaler"] == artifact["scaler"]
    assert changed["classifier"] == artifact["classifier"]
    assert changed["calibration"] == artifact["calibration"]
    assert not changed["promotion_gate"]["passed"]
    assert changed["test_prediction_fingerprint"] != artifact["test_prediction_fingerprint"]


def test_calibration_labels_cannot_change_trained_model_weights(dataset, artifact):
    start = date.fromisoformat(artifact["boundaries"]["calibration_start"])
    end = date.fromisoformat(artifact["boundaries"]["test_start"])
    rows = tuple(
        replace(e, label=1 - e.label, net_return_pct=5 if e.label == 0 else -3)
        if start <= e.observed_on < end
        else e
        for e in dataset.examples
    )
    changed = fit_validated_model(replace(dataset, examples=rows))
    assert changed["scaler"] == artifact["scaler"]
    assert changed["classifier"] == artifact["classifier"]
    assert changed["calibration"] != artifact["calibration"]


def test_future_feature_distribution_never_changes_training_standardizer(dataset, artifact):
    start = date.fromisoformat(artifact["boundaries"]["test_start"])
    rows = tuple(
        replace(e, features=tuple(v + 10000 for v in e.features)) if e.observed_on >= start else e
        for e in dataset.examples
    )
    changed = fit_validated_model(replace(dataset, examples=rows))
    assert changed["scaler"] == artifact["scaler"]
    assert changed["classifier"] == artifact["classifier"]
    assert changed["calibration"] == artifact["calibration"]
    assert changed["test_metrics"]["ood_fraction"] == 1
    assert changed["test_metrics"]["model_selected"]["samples"] == 0
    assert not changed["promotion_gate"]["passed"]


def test_reordering_examples_preserves_model_identity_parameters_and_bootstrap(dataset, artifact):
    repeated = fit_validated_model(replace(dataset, examples=tuple(reversed(dataset.examples))))
    for key in ("model_id", "scaler", "classifier", "calibration", "test_metrics"):
        assert repeated[key] == artifact[key]
    bounds = repeated["test_metrics"]["date_block_uncertainty"]
    assert bounds["block_dates"] == artifact["horizon_days"] + 1
    assert bounds["brier_improvement_over_calibration"]["lower"] > 0


def test_chronological_uncertainty_can_reject_positive_mean_excess_return(dataset, artifact):
    start = date.fromisoformat(artifact["boundaries"]["test_start"])
    dates = sorted({e.observed_on for e in dataset.examples if e.observed_on >= start})
    midpoint = dates[len(dates) // 2]
    rows = tuple(
        replace(
            e, benchmark_return_pct=e.net_return_pct + (5 if e.observed_on < midpoint else -5.5)
        )
        if e.observed_on >= start and e.label
        else e
        for e in dataset.examples
    )
    result = fit_validated_model(replace(dataset, examples=rows))
    metrics = result["test_metrics"]
    assert metrics["model_selected"]["mean_excess_return_pct"] > 0
    assert metrics["date_block_uncertainty"]["selected_excess_return_pct"]["lower"] < 0
    assert not result["promotion_gate"]["passed"]
    assert any("Date-block intervals" in reason for reason in result["promotion_gate"]["reasons"])


def test_current_prices_are_not_historical_fundamental_features():
    assert not any(
        word in name for name in FEATURE_NAMES for word in ("eps", "book", "roe", "debt")
    )


def test_future_rows_cannot_change_earlier_feature_vectors():
    bars = history(180, oscillate=True)
    cutoff = bars[-1].business_date
    first = build_examples({"STOCK": bars}, eligible_symbols={"STOCK"}, completed_through=cutoff)
    extra = history(200, oscillate=True)[180:]
    for b in extra:
        b.open *= 10
        b.high *= 10
        b.low *= 10
        b.close *= 10
    second = build_examples(
        {"STOCK": bars + extra}, eligible_symbols={"STOCK"}, completed_through=cutoff
    )
    assert first.examples
    assert first.examples == second.examples
    assert second.sampling["future_rows_excluded"] == 20


def test_builder_discloses_missing_unfilled_and_non_stock_coverage():
    bars = history(180, oscillate=True)
    original = build_examples(
        {"STOCK": bars}, eligible_symbols={"STOCK"}, completed_through=bars[-1].business_date
    )
    first_entry = next(
        i for i, b in enumerate(bars) if b.business_date > original.examples[0].observed_on
    )
    second_entry = next(
        i for i, b in enumerate(bars) if b.business_date > original.examples[1].observed_on
    )
    # Entry-zone gaps and missing sessions must not turn into profitable labels.
    bars[first_entry].open += 20
    bars[first_entry].high = max(bars[first_entry].high, bars[first_entry].open)
    bars[second_entry].low = None
    dataset = build_examples(
        {"STOCK": bars, "FUND": history(180, "FUND")},
        eligible_symbols={"STOCK"},
        completed_through=bars[-1].business_date,
    )
    assert dataset.sampling["ineligible_symbols"] == 1
    assert dataset.sampling.get("not_entered", 0) > 0
    assert dataset.sampling.get("no_data", 0) > 0
    assert all(
        e.symbol == "STOCK" and e.label == int(e.net_return_pct > 0) for e in dataset.examples
    )


def test_known_corporate_actions_are_excluded_from_historical_labels_and_feature_lookback():
    bars = history(180, oscillate=True)
    original = build_examples(
        {"STOCK": bars}, eligible_symbols={"STOCK"}, completed_through=bars[-1].business_date
    )
    action = CorporateAction(
        symbol="STOCK",
        ex_date=original.examples[0].label_end,
        action_type=CorporateActionType.BONUS,
        ratio_numerator=1,
        ratio_denominator=1,
        factor=0.5,
        source=SourceName.MANUAL,
    )
    dataset = build_examples(
        {"STOCK": bars},
        eligible_symbols={"STOCK"},
        completed_through=bars[-1].business_date,
        corporate_actions={"STOCK": [action]},
    )
    assert dataset.sampling.get("action_in_lookback", 0) > 0
    assert dataset.sampling.get("excluded", 0) > 0


def test_missing_and_single_class_training_are_rejected(dataset):
    with pytest.raises(ModelValidationError, match="enough dates"):
        fit_validated_model(replace(dataset, examples=dataset.examples[:4]))
    rows = tuple(replace(e, label=1, net_return_pct=5) for e in dataset.examples)
    with pytest.raises(ModelValidationError, match="both outcome classes"):
        fit_validated_model(replace(dataset, examples=rows))


def test_small_two_class_dataset_saves_research_evidence_but_cannot_activate(dataset, tmp_path):
    small = fit_validated_model(replace(dataset, examples=dataset.examples[:120]))
    assert small["test_metrics"]["calibrated"]["samples"] > 0
    assert not small["promotion_gate"]["passed"]
    assert any(
        "Activation requires 400 samples" in reason for reason in small["promotion_gate"]["reasons"]
    )
    with Storage(tmp_path / "small.db") as storage:
        summary = save_model(storage, small, model_summary(small))
        assert summary["status"] == "rejected"
        assert summary["gate"] == small["promotion_gate"]
        with pytest.raises(ValueError, match="Activation requires 400 samples"):
            deploy_model(storage, small["model_id"], today=dataset.completed_through)


def test_invalid_or_contradictory_labels_are_rejected(dataset):
    rows = list(dataset.examples)
    rows[0] = replace(rows[0], label=1, net_return_pct=-1)
    with pytest.raises(ModelValidationError, match="finite causal features"):
        fit_validated_model(replace(dataset, examples=tuple(rows)))


def test_overlapping_stock_label_intervals_are_rejected(dataset):
    rows = list(dataset.examples)
    first = rows[0]
    overlap = add_trading_days(first.observed_on, 1)
    rows[4] = replace(rows[4], observed_on=overlap, label_end=add_trading_days(overlap, 3))
    with pytest.raises(ModelValidationError, match="must not overlap"):
        fit_validated_model(replace(dataset, examples=tuple(rows)))


def test_prediction_is_distinct_probability_and_rejects_unvalidated_or_corrupt_artifacts(artifact):
    bars = history(1203)
    as_of = date.fromisoformat(artifact["completed_through"])
    assert bars[-1].business_date == as_of
    prediction = predict_probability(artifact, bars, as_of=as_of)
    assert 0 < prediction["probability"] < 1
    assert prediction["event"] == "net_profitable_modeled_trade_given_entry"
    assert "evidence_score" not in prediction
    broken = copy.deepcopy(artifact)
    broken["classifier"]["weights"][0] += 1
    with pytest.raises(ModelValidationError, match="fingerprint"):
        predict_probability(broken, bars, as_of=as_of)


def test_passed_model_deployment_is_explicit_audited_and_idempotent(artifact, tmp_path):
    completed = date.fromisoformat(artifact["completed_through"])
    model_id = artifact["model_id"]
    with freeze_time(completed), Storage(tmp_path / "model.db") as storage:
        candidate = save_model(storage, artifact, model_summary(artifact))
        assert candidate["status"] == "candidate" and candidate["advisory_eligible"]
        assert save_model(storage, artifact, model_summary(artifact)) == candidate
        assert active_models(storage) == {}
        for outside in (completed - timedelta(days=1), completed + timedelta(days=91)):
            with pytest.raises(ValueError, match="outside the deployment window"):
                deploy_model(storage, model_id, today=outside)
        assert deploy_model(storage, model_id, today=completed)["status"] == "active"
        assert deploy_model(storage, model_id, today=completed)["status"] == "active"
        assert active_models(storage)[artifact["horizon_days"]]["model_id"] == model_id
        disable_model(storage, artifact["horizon_days"])
        disable_model(storage, artifact["horizon_days"])
        assert active_models(storage) == {}
        assert [
            row[0]
            for row in storage._conn.execute(
                "SELECT action FROM model_deployment_events ORDER BY id"
            )
        ] == ["activated", "disabled"]


def test_inference_rejects_stale_quotes_and_unseen_security(artifact):
    bars = history(1203)
    as_of = date.fromisoformat(artifact["completed_through"])
    with pytest.raises(ModelValidationError, match="usable quote"):
        predict_probability(artifact, bars[:-1], as_of=as_of)
    with pytest.raises(ModelValidationError, match="not represented"):
        predict_probability(artifact, history(1203, "NEW"), as_of=as_of)


def test_prediction_is_invariant_to_price_history_before_the_bounded_window(artifact):
    bars = history(1203)
    as_of = bars[-1].business_date
    bars[-FEATURE_LOOKBACK - 1].high = 10**8
    assert predict_probability(artifact, bars, as_of=as_of) == predict_probability(
        artifact, bars[-FEATURE_LOOKBACK:], as_of=as_of
    )


def test_prediction_rejects_invalid_volume_and_duplicate_sessions(artifact):
    bars = history(1203)
    as_of = bars[-1].business_date
    with pytest.raises(ModelValidationError, match="duplicate sessions"):
        predict_probability(artifact, bars + bars[-1:], as_of=as_of)
    bars[-1].volume = -1
    with pytest.raises(ModelValidationError, match="price/volume evidence"):
        predict_probability(artifact, bars, as_of=as_of)


def test_inference_rejects_changed_fees_and_recent_corporate_actions(artifact):
    bars = history(1203)
    as_of = date.fromisoformat(artifact["completed_through"])
    engine = CostEngine()
    changed = CostEngine(engine.model.model_copy(update={"dp_charge_per_scrip": 999}))
    with pytest.raises(ModelValidationError, match="retraining is required"):
        predict_probability(artifact, bars, as_of=as_of, cost_engine=changed)
    action = CorporateAction(
        symbol="STOCK",
        ex_date=as_of,
        action_type=CorporateActionType.BONUS,
        ratio_numerator=1,
        ratio_denominator=1,
        factor=0.5,
        source=SourceName.MANUAL,
    )
    with pytest.raises(ModelValidationError, match="corporate action"):
        predict_probability(artifact, bars, as_of=as_of, corporate_actions=[action])


def test_failed_holdout_can_only_produce_research_estimates(dataset, tmp_path):
    start = sorted({e.observed_on for e in dataset.examples})[
        int(len({e.observed_on for e in dataset.examples}) * 0.8)
    ]
    rows = tuple(
        replace(e, label=1 - e.label, net_return_pct=5 if e.label == 0 else -3)
        if e.observed_on >= start
        else e
        for e in dataset.examples
    )
    failed = fit_validated_model(replace(dataset, examples=rows))
    bars = history(1203)
    as_of = date.fromisoformat(failed["completed_through"])
    assert not failed["promotion_gate"]["passed"]
    with pytest.raises(ModelValidationError, match="cannot influence buy advice"):
        predict_probability(failed, bars, as_of=as_of)
    research = predict_probability(failed, bars, as_of=as_of, require_promotion=False)
    assert research["label"] == "Research-only estimate" and not research["eligible_for_advisory"]
    with Storage(tmp_path / "rejected.db") as storage:
        assert save_model(storage, failed, model_summary(failed))["status"] == "rejected"
        with pytest.raises(ValueError, match="Held-out validation blocked activation"):
            deploy_model(storage, failed["model_id"], today=as_of)
        assert active_models(storage) == {}


def test_constant_calibration_cannot_masquerade_as_stock_selection_edge(dataset):
    rows = tuple(replace(e, features=(0.0,) * len(FEATURE_NAMES)) for e in dataset.examples)
    constant = fit_validated_model(replace(dataset, examples=rows))
    assert constant["test_metrics"]["calibrated"]["auc"] == 0.5
    assert not constant["promotion_gate"]["passed"]
    assert any("AUC" in reason for reason in constant["promotion_gate"]["reasons"])
    assert any(
        "calibration base-rate" in reason for reason in constant["promotion_gate"]["reasons"]
    )
