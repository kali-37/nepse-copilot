"""Chronological, cost-aware training and held-out validation of stock forecasts.

This module trains a deliberately transparent logistic baseline. Its estimated
event is a profitable *modeled* trade conditional on the declared entry policy,
not a target hit or a guaranteed broker fill. No fundamentals are historical
features: their publication periods are not sufficiently verified yet.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from itertools import accumulate, groupby
from random import Random
from statistics import fmean

from nepse_trader.advisor.decision_signals import ChartState, chart_states
from nepse_trader.advisor.track_record import evaluate_recommendation
from nepse_trader.analysis.costs import CostEngine
from nepse_trader.calendar import add_trading_days, is_trading_day, next_trading_day, session_policy
from nepse_trader.models import CorporateAction, PriceBar

MODEL_VERSION = "nepse-logistic-v2"
FEATURE_LOOKBACK = 50
FEATURE_NAMES = (
    "close_vs_ma20",
    "ma20_vs_ma50",
    "momentum_5_observations",
    "rsi_centered",
    "atr_fraction",
    "log_volume_ratio",
    "log_average_volume",
    "return_1_observation",
)
EVENT = "net_profitable_modeled_trade_given_entry"
_BOOTSTRAP_REPLICATES = 400
_RELIABILITY_BINS = 10
LIMITATIONS = [
    "Probabilities concern a simulated 100-share trade, not verified broker execution.",
    "Unfilled zones, missing sessions and known corporate actions are disclosed exclusions.",
    "Spread, queue position, slippage, market impact and unrecorded actions are not verified.",
    "Date-block intervals account for shared market dates and overlapping horizons. They cannot establish independence across market regimes.",
    "Historical fundamentals are excluded; current financial evidence must gate advice separately.",
    "Held-out validation is historical research, not a prospective trading track record.",
    "The available classified-security universe does not establish complete delisting or survivorship coverage.",
    "Historical fee changes are not fully versioned; labels use the fingerprinted configured fee schedule.",
    "Repeated evaluations on overlapping holdouts are not new independent validations.",
]


class ModelValidationError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class ModelExample:
    symbol: str
    observed_on: date
    label_end: date
    features: tuple[float, ...]
    label: int
    net_return_pct: float
    benchmark_return_pct: float
    rule_strength: float


@dataclass(frozen=True)
class TrainingDataset:
    examples: tuple[ModelExample, ...]
    horizon_days: int
    completed_through: date
    sampling: dict[str, int]
    policy_fingerprint: str
    attempted_dates: tuple[date, ...] = ()


@dataclass(frozen=True)
class ValidationConfig:
    train_fraction: float = 0.6
    calibration_fraction: float = 0.2
    epochs: int = 160
    learning_rate: float = 0.05
    l2: float = 0.1
    minimum_train_samples: int = 400
    minimum_calibration_samples: int = 150
    minimum_test_samples: int = 150
    minimum_class_samples: int = 25
    minimum_test_dates: int = 40
    minimum_test_blocks: int = 5
    minimum_selected_samples: int = 30
    minimum_selected_dates: int = 10
    selection_threshold: float = 0.6
    maximum_test_ece: float = 0.12
    minimum_relative_brier_improvement: float = 0.01
    minimum_test_auc: float = 0.55
    maximum_ood_fraction: float = 0.1


def _fingerprint(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def _features(state: ChartState, previous_close: float) -> tuple[float, ...]:
    return (
        state.close / state.ma20 - 1,
        state.ma20 / state.ma50 - 1,
        state.momentum,
        state.rsi / 100 - 0.5,
        state.atr / state.close,
        math.log1p(state.volume_ratio),
        math.log1p(state.average_volume),
        state.close / previous_close - 1,
    )


def _feature_state(window: list[PriceBar]) -> ChartState | None:
    """Use the same bounded history to estimate Wilder indicators at inference."""
    if window[-1].volume is None or window[-1].volume <= 0:
        return None
    state = chart_states(window)[-1]
    if state is None or state.volume_samples < 15 or state.average_volume < 1000:
        return None
    if not all(bar.low <= bar.close <= bar.high for bar in window):
        return None
    return state


def label_policy_fingerprint(horizon_days: int, cost_engine: CostEngine | None = None) -> str:
    engine = cost_engine or CostEngine()
    return _fingerprint(
        dict(
            version=MODEL_VERSION,
            horizon=horizon_days,
            features=FEATURE_NAMES,
            feature_lookback=FEATURE_LOOKBACK,
            label=EVENT,
            quantity=100,
            zone_atr=0.2,
            stop_atr=1 if horizon_days == 3 else 2,
            target_atr=1.5 if horizon_days == 3 else 3,
            nonoverlap="scheduled_horizon_with_fixed_symbol_hash_phase",
            execution="raw_next_open_T+2_stop_first",
            calendar=session_policy(),
            costs=engine.model.model_dump(mode="json"),
        )
    )


def build_examples(
    histories: Mapping[str, Sequence[PriceBar]],
    *,
    eligible_symbols: Iterable[str],
    completed_through: date,
    horizon_days: int = 3,
    corporate_actions: Mapping[str, Sequence[CorporateAction]] | None = None,
    cost_engine: CostEngine | None = None,
) -> TrainingDataset:
    """Create non-overlapping calls from raw, past-only features and future labels.

    ``eligible_symbols`` is mandatory: the caller must positively classify stock
    securities and exclude funds. Neither current earnings nor future-adjusted
    prices are inferred here. The horizon is reserved even for an unfilled call,
    so later sample selection cannot depend on whether its outcome was favorable.
    """
    if horizon_days not in (3, 22):
        raise ModelValidationError("unsupported_horizon", "Use a 3- or 22-session horizon.")
    engine = cost_engine or CostEngine()
    counts: Counter = Counter()
    examples = []
    attempted_dates = set()
    allowed = {str(s).strip().upper() for s in eligible_symbols}
    policy = label_policy_fingerprint(horizon_days, engine)
    for symbol in sorted(histories):
        if symbol not in allowed:
            counts["ineligible_symbols"] += 1
            continue
        source = list(histories[symbol])
        if any(b.symbol != symbol for b in source):
            raise ModelValidationError(
                "mixed_symbols", f"History for {symbol} contains another symbol."
            )
        bars = sorted(
            (b for b in source if b.business_date <= completed_through),
            key=lambda b: b.business_date,
        )
        counts["future_rows_excluded"] += len(source) - len(bars)
        if len({b.business_date for b in bars}) != len(bars):
            raise ModelValidationError(
                "duplicate_dates", f"History for {symbol} contains duplicate sessions."
            )
        tape = {b.business_date: b for b in bars}
        bars = [b for b in bars if is_trading_day(b.business_date)]
        counts["non_session_rows_excluded"] += len(tape) - len(bars)
        actions = [a for a in (corporate_actions or {}).get(symbol, ()) if a.symbol == symbol]
        next_after = date.min
        phase = int(hashlib.sha256(symbol.encode()).hexdigest()[:8], 16) % (horizon_days + 1)
        for i in range(FEATURE_LOOKBACK - 1, len(bars)):
            observed = bars[i].business_date
            counts["observed_setups"] += 1
            if i < FEATURE_LOOKBACK - 1 + phase:
                counts["sampling_phase_skipped"] += 1
                continue
            if observed <= next_after:
                counts["overlap_skipped"] += 1
                continue
            window = bars[i - FEATURE_LOOKBACK + 1 : i + 1]
            if any(window[0].business_date <= ca.ex_date <= observed for ca in actions):
                counts["action_in_lookback"] += 1
                continue
            state = _feature_state(window)
            if state is None:
                counts["invalid_features"] += 1
                continue
            entry = next_trading_day(observed + timedelta(days=1))
            deadline = add_trading_days(entry, horizon_days - 1)
            if deadline > completed_through:
                counts["unresolved"] += 1
                continue
            next_after = deadline
            counts["attempted_calls"] += 1
            attempted_dates.add(observed)
            prediction = dict(
                prediction_id=f"research:{symbol}:{observed}",
                symbol=symbol,
                made_on=observed.isoformat(),
                forecast_entry_on=entry.isoformat(),
                deadline=deadline.isoformat(),
                horizon_days=horizon_days,
                entry_low=round(max(0.01, state.close - state.atr * 0.2), 2),
                entry_high=round(state.close + state.atr * 0.2, 2),
                stop=round(
                    max(
                        state.close * 0.9, state.close - state.atr * (1 if horizon_days == 3 else 2)
                    ),
                    2,
                ),
                target_1=round(state.close + state.atr * (1.5 if horizon_days == 3 else 3), 2),
            )
            future = []
            day = entry
            while day <= deadline:
                if day in tape:
                    future.append(tape[day])
                day += timedelta(days=1)
            result = evaluate_recommendation(
                prediction,
                future,
                as_of=completed_through,
                cost_engine=engine,
                corporate_actions=actions,
            )
            if result.net_return_pct is None or result.benchmark_return_pct is None:
                counts[result.outcome.lower()] += 1
                continue
            features = _features(state, window[-2].close)
            if not all(math.isfinite(v) for v in features):
                counts["invalid_features"] += 1
                continue
            examples.append(
                ModelExample(
                    symbol,
                    observed,
                    deadline,
                    features,
                    int(result.net_return_pct > 0),
                    result.net_return_pct,
                    result.benchmark_return_pct,
                    state.strength(horizon_days),
                )
            )
            counts["eligible_calls"] += 1
    return TrainingDataset(
        tuple(sorted(examples, key=lambda e: (e.observed_on, e.symbol))),
        horizon_days,
        completed_through,
        dict(counts),
        policy,
        tuple(sorted(attempted_dates)),
    )


def chronological_split(dataset: TrainingDataset, config: ValidationConfig):
    ordered = sorted(dataset.examples, key=lambda e: (e.observed_on, e.symbol))
    labelled_dates = {e.observed_on for e in ordered}
    attempted_dates = set(dataset.attempted_dates) if dataset.attempted_dates else labelled_dates
    dates = sorted(attempted_dates)
    if (
        len(dates) < 10
        or not labelled_dates <= attempted_dates
        or not 0 < config.train_fraction < 1
        or not 0 < config.calibration_fraction < 1
        or config.train_fraction + config.calibration_fraction >= 1
    ):
        raise ModelValidationError(
            "insufficient_dates",
            "Need enough dates and positive train/calibration/test partitions.",
        )
    calibration_start = dates[int(len(dates) * config.train_fraction)]
    test_start = dates[int(len(dates) * (config.train_fraction + config.calibration_fraction))]
    train = [
        e for e in ordered if e.observed_on < calibration_start and e.label_end < calibration_start
    ]
    calibration = [
        e
        for e in ordered
        if calibration_start <= e.observed_on < test_start and e.label_end < test_start
    ]
    test = [
        e
        for e in ordered
        if test_start <= e.observed_on and e.label_end <= dataset.completed_through
    ]
    purged = len(dataset.examples) - len(train) - len(calibration) - len(test)
    return (
        train,
        calibration,
        test,
        dict(
            calibration_start=calibration_start.isoformat(),
            test_start=test_start.isoformat(),
            anchor_dates=len(dates),
            anchor_dates_fingerprint=_fingerprint([d.isoformat() for d in dates]),
            purged_examples=purged,
            method="global attempted dates before outcome filtering; purge scheduled label intervals before next partition",
        ),
    )


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1 / (1 + math.exp(-value))
    exp = math.exp(value)
    return exp / (1 + exp)


def _scale(features, center, scale):
    return tuple(
        max(-8.0, min(8.0, (v - m) / s)) for v, m, s in zip(features, center, scale, strict=True)
    )


def _fit_logistic(matrix, labels, config):
    weights = [0.0] * len(FEATURE_NAMES)
    base_rate = (sum(labels) + 0.5) / (len(labels) + 1)
    intercept = math.log(base_rate / (1 - base_rate))
    for _ in range(config.epochs):
        gradient = [0.0] * len(weights)
        bias = 0.0
        for features, label in zip(matrix, labels, strict=True):
            error = (
                _sigmoid(intercept + sum(w * x for w, x in zip(weights, features, strict=True)))
                - label
            )
            bias += error
            for j, x in enumerate(features):
                gradient[j] += error * x
        for j in range(len(weights)):
            weights[j] -= config.learning_rate * (
                gradient[j] / len(labels) + config.l2 * weights[j]
            )
        intercept -= config.learning_rate * bias / len(labels)
    return weights, intercept, base_rate


def _fit_calibrator(logits, labels, config):
    slope, offset = 1.0, 0.0
    for _ in range(config.epochs):
        errors = [_sigmoid(slope * x + offset) - y for x, y in zip(logits, labels, strict=True)]
        slope = max(
            0.0,
            slope
            - config.learning_rate
            * (fmean(e * x for e, x in zip(errors, logits, strict=True)) + 0.01 * (slope - 1)),
        )
        offset -= config.learning_rate * fmean(errors)
    return slope, offset


def _probability_bin(probability: float) -> int:
    return min(int(probability * _RELIABILITY_BINS), _RELIABILITY_BINS - 1)


def _metrics(probabilities, examples):
    labels = [e.label for e in examples]
    n = len(labels)
    positives = sum(labels)
    rank_sum = rank = 0
    for _, items in groupby(
        sorted(zip(probabilities, labels, strict=True)), key=lambda item: item[0]
    ):
        group = list(items)
        average_rank = (rank + 1 + rank + len(group)) / 2
        rank_sum += average_rank * sum(y for _, y in group)
        rank += len(group)
    auc = (
        (rank_sum - positives * (positives + 1) / 2) / (positives * (n - positives))
        if 0 < positives < n
        else None
    )
    bins = []
    ece = 0.0
    for i in range(_RELIABILITY_BINS):
        indexes = [j for j, p in enumerate(probabilities) if _probability_bin(p) == i]
        count = len(indexes)
        hits = sum(labels[j] for j in indexes)
        predicted = fmean(probabilities[j] for j in indexes) if count else None
        observed = hits / count if count else None
        if count:
            ece += count / n * abs(predicted - observed)
        bins.append(
            dict(
                lower=i / _RELIABILITY_BINS,
                upper=(i + 1) / _RELIABILITY_BINS,
                samples=count,
                mean_probability=predicted,
                observed_rate=observed,
                interval_low=None,
                interval_high=None,
            )
        )
    return dict(
        samples=n,
        distinct_dates=len({e.observed_on for e in examples}),
        positives=positives,
        auc=auc,
        brier=fmean((p - y) ** 2 for p, y in zip(probabilities, labels, strict=True)),
        log_loss=-fmean(
            y * math.log(max(1e-9, p)) + (1 - y) * math.log(max(1e-9, 1 - p))
            for p, y in zip(probabilities, labels, strict=True)
        ),
        ece=ece,
        profitable_rate=fmean(labels),
        mean_probability=fmean(probabilities),
        reliability=bins,
    )


def _date_block_intervals(
    test: Sequence[ModelExample],
    probabilities: Sequence[float],
    selected: Sequence[bool],
    *,
    training_rate: float,
    calibration_rate: float,
    block_size: int,
    minimum_blocks: int,
) -> dict:
    """Resample adjacent prediction dates together, including all stocks on each date."""
    by_date = {}
    bins_offset = 6
    columns = bins_offset + 2 * _RELIABILITY_BINS
    for example, probability, chosen in zip(test, probabilities, selected, strict=True):
        values = by_date.setdefault(example.observed_on, [0.0] * columns)
        error = (probability - example.label) ** 2
        values[0] += 1
        values[1] += (training_rate - example.label) ** 2 - error
        values[2] += (calibration_rate - example.label) ** 2 - error
        if chosen:
            values[3] += 1
            values[4] += example.net_return_pct
            values[5] += example.net_return_pct - example.benchmark_return_pct
        bin_offset = bins_offset + 2 * _probability_bin(probability)
        values[bin_offset] += 1
        values[bin_offset + 1] += example.label

    dates = sorted(by_date)
    count = len(dates)
    full_blocks = count // block_size
    estimate_columns = [(1, 0), (2, 0), (4, 3), (5, 3)] + [
        (i + 1, i) for i in range(bins_offset, columns, 2)
    ]
    estimates = [[] for _ in estimate_columns]
    if full_blocks >= minimum_blocks:
        days = [by_date[day] for day in dates] * 2
        sums = [list(accumulate(series, initial=0.0)) for series in zip(*days, strict=True)]
        rng = Random(1729)
        lengths = [min(block_size, count - i) for i in range(0, count, block_size)]
        for _ in range(_BOOTSTRAP_REPLICATES):
            starts = [rng.randrange(count) for _ in lengths]
            blocks = [(s, s + n) for s, n in zip(starts, lengths, strict=True)]
            totals = [sum(series[end] - series[start] for start, end in blocks) for series in sums]
            for (num, den), values in zip(estimate_columns, estimates, strict=True):
                if totals[den] > 0:
                    values.append(totals[num] / totals[den])

    def interval(values):
        if len(values) < 0.95 * _BOOTSTRAP_REPLICATES:
            return dict(lower=None, upper=None)
        values.sort()
        last = len(values) - 1
        return dict(lower=values[int(0.025 * last)], upper=values[math.ceil(0.975 * last)])

    train, calibration, net, excess, *reliability = (interval(sample) for sample in estimates)
    return dict(
        method="95% circular moving-block bootstrap over chronological prediction dates",
        block_dates=block_size,
        full_blocks=full_blocks,
        replicates=_BOOTSTRAP_REPLICATES if full_blocks >= minimum_blocks else 0,
        brier_improvement_over_train=train,
        brier_improvement_over_calibration=calibration,
        selected_net_return_pct=net,
        selected_excess_return_pct=excess,
        reliability=reliability,
    )


def _period(examples):
    return dict(
        start=min(e.observed_on for e in examples).isoformat(),
        end=max(e.observed_on for e in examples).isoformat(),
        label_end=max(e.label_end for e in examples).isoformat(),
        samples=len(examples),
        distinct_dates=len({e.observed_on for e in examples}),
    )


def _return_summary(examples):
    if not examples:
        return dict(
            samples=0, mean_net_return_pct=None, profitable_rate=None, mean_excess_return_pct=None
        )
    return dict(
        samples=len(examples),
        mean_net_return_pct=fmean(e.net_return_pct for e in examples),
        profitable_rate=fmean(e.label for e in examples),
        mean_excess_return_pct=fmean(e.net_return_pct - e.benchmark_return_pct for e in examples),
    )


def fit_validated_model(
    dataset: TrainingDataset, *, config: ValidationConfig | None = None
) -> dict:
    config = config or ValidationConfig()
    if dataset.horizon_days not in (3, 22):
        raise ModelValidationError("unsupported_horizon", "Use a 3- or 22-session horizon.")
    if (
        config.epochs <= 0
        or not 0 < config.learning_rate <= 1
        or not (math.isfinite(config.l2) and config.l2 >= 0)
        or not 0 < config.selection_threshold < 1
        or not 0 <= config.minimum_relative_brier_improvement < 1
        or not all(
            0 <= value <= 1
            for value in (
                config.maximum_test_ece,
                config.minimum_test_auc,
                config.maximum_ood_fraction,
            )
        )
        or min(
            config.minimum_train_samples,
            config.minimum_calibration_samples,
            config.minimum_test_samples,
            config.minimum_class_samples,
            config.minimum_test_dates,
            config.minimum_test_blocks,
            config.minimum_selected_samples,
            config.minimum_selected_dates,
        )
        < 1
    ):
        raise ModelValidationError("invalid_optimizer", "Invalid fixed optimizer settings.")
    last_end = {}
    for e in sorted(dataset.examples, key=lambda item: (item.symbol, item.observed_on)):
        expected_end = add_trading_days(
            next_trading_day(e.observed_on + timedelta(days=1)), dataset.horizon_days - 1
        )
        if (
            len(e.features) != len(FEATURE_NAMES)
            or e.label not in (0, 1)
            or e.label != int(e.net_return_pct > 0)
            or e.label_end <= e.observed_on
            or e.label_end != expected_end
            or e.label_end > dataset.completed_through
            or not is_trading_day(e.observed_on)
            or not 0 <= e.rule_strength <= 1
            or not all(
                math.isfinite(v) for v in (*e.features, e.net_return_pct, e.benchmark_return_pct)
            )
        ):
            raise ModelValidationError(
                "invalid_example", "Examples require finite causal features and valid dated labels."
            )
        if e.observed_on <= last_end.get(e.symbol, date.min):
            raise ModelValidationError(
                "overlapping_examples", "Each stock's evaluated label intervals must not overlap."
            )
        last_end[e.symbol] = e.label_end
    train, calibration, test, split = chronological_split(dataset, config)
    training_symbols = {e.symbol for e in train}
    split["new_symbols_excluded"] = sum(
        e.symbol not in training_symbols for e in calibration + test
    )
    calibration = [e for e in calibration if e.symbol in training_symbols]
    test = [e for e in test if e.symbol in training_symbols]
    failures = []
    for name, examples, fit_floor, promotion_minimum in (
        ("Training", train, len(FEATURE_NAMES) + 2, config.minimum_train_samples),
        ("Calibration", calibration, 4, config.minimum_calibration_samples),
        ("Test", test, 4, config.minimum_test_samples),
    ):
        total = len(examples)
        profitable = sum(e.label for e in examples)
        minority = min(profitable, total - profitable)
        if total < fit_floor or minority == 0:
            raise ModelValidationError(
                f"insufficient_{name.lower()}",
                f"{name} needs at least {fit_floor} samples and both outcome classes to evaluate.",
            )
        if total < promotion_minimum or minority < config.minimum_class_samples:
            failures.append(
                f"{name} has {total} samples and {minority} in the smaller outcome class. "
                f"Activation requires {promotion_minimum} samples and "
                f"{config.minimum_class_samples} per outcome class."
            )
    center = [fmean(e.features[j] for e in train) for j in range(len(FEATURE_NAMES))]
    scale = [
        math.sqrt(fmean((e.features[j] - center[j]) ** 2 for e in train)) or 1.0
        for j in range(len(FEATURE_NAMES))
    ]
    matrix = [_scale(e.features, center, scale) for e in train]
    weights, intercept, base_rate = _fit_logistic(matrix, [e.label for e in train], config)

    def logits(examples):
        return [
            intercept
            + sum(w * x for w, x in zip(weights, _scale(e.features, center, scale), strict=True))
            for e in examples
        ]

    calibration_logits = logits(calibration)
    slope, offset = _fit_calibrator(calibration_logits, [e.label for e in calibration], config)
    test_logits = logits(test)
    raw = [_sigmoid(z) for z in test_logits]
    probabilities = [min(0.99, max(0.01, _sigmoid(slope * z + offset))) for z in test_logits]
    metrics = _metrics(probabilities, test)
    baseline = _metrics([base_rate] * len(test), test)
    calibration_base_rate = fmean(e.label for e in calibration)
    calibration_baseline = _metrics([calibration_base_rate] * len(test), test)
    out_of_domain = [
        max(abs((v - m) / s) for v, m, s in zip(e.features, center, scale, strict=True)) > 6
        for e in test
    ]
    selected_mask = [
        not outlier and p >= config.selection_threshold
        for p, outlier in zip(probabilities, out_of_domain, strict=True)
    ]
    selected = [e for e, chosen in zip(test, selected_mask, strict=True) if chosen]
    selected_returns = _return_summary(selected)
    rules = _return_summary([e for e in test if e.rule_strength >= 0.6])
    ood = fmean(out_of_domain)
    interval = _date_block_intervals(
        test,
        probabilities,
        selected_mask,
        training_rate=base_rate,
        calibration_rate=calibration_base_rate,
        block_size=dataset.horizon_days + 1,
        minimum_blocks=config.minimum_test_blocks,
    )
    for bucket, bounds in zip(metrics["reliability"], interval.pop("reliability"), strict=True):
        bucket.update(interval_low=bounds["lower"], interval_high=bounds["upper"])
    if metrics["distinct_dates"] < config.minimum_test_dates:
        failures.append("Too few distinct held-out market dates.")
    if interval["full_blocks"] < config.minimum_test_blocks:
        failures.append("Too few chronological date blocks to measure held-out uncertainty.")
    elif any(
        interval[key]["lower"] is None or interval[key]["lower"] <= 0
        for key in ("brier_improvement_over_train", "brier_improvement_over_calibration")
    ):
        failures.append(
            "Date-block intervals do not establish a positive Brier improvement over both baselines."
        )
    if metrics["brier"] > baseline["brier"] * (1 - config.minimum_relative_brier_improvement):
        failures.append(
            "Held-out Brier score does not beat the frozen training base-rate baseline."
        )
    if metrics["brier"] > calibration_baseline["brier"] * (
        1 - config.minimum_relative_brier_improvement
    ):
        failures.append(
            "Held-out Brier score does not beat the frozen calibration base-rate baseline."
        )
    if metrics["log_loss"] > baseline["log_loss"]:
        failures.append("Held-out log loss is worse than the frozen base-rate baseline.")
    if metrics["log_loss"] > calibration_baseline["log_loss"]:
        failures.append(
            "Held-out log loss is worse than the frozen calibration base-rate baseline."
        )
    if metrics["auc"] is None or metrics["auc"] < config.minimum_test_auc:
        failures.append("Held-out discrimination AUC is below the fixed minimum.")
    if metrics["ece"] > config.maximum_test_ece:
        failures.append("Held-out calibration error exceeds the fixed limit.")
    if ood > config.maximum_ood_fraction:
        failures.append("Too many held-out features lie outside the training domain.")
    if len(selected) < config.minimum_selected_samples:
        failures.append("Too few trades pass the fixed probability threshold.")
    elif len({e.observed_on for e in selected}) < config.minimum_selected_dates:
        failures.append("Selected held-out trades are too concentrated in a few market dates.")
    if selected and (
        selected_returns["mean_net_return_pct"] <= 0
        or selected_returns["mean_excess_return_pct"] < 0
    ):
        failures.append(
            "Selected held-out trades lack positive cost-aware return or matched-hold excess return."
        )
    if selected and interval["replicates"]:
        net = interval["selected_net_return_pct"]["lower"]
        excess = interval["selected_excess_return_pct"]["lower"]
        if net is None or net <= 0 or excess is None or excess < 0:
            failures.append(
                "Date-block intervals do not support positive selected returns against costs and matched hold."
            )
    chart_comparable = rules["samples"] >= config.minimum_selected_samples
    if (
        selected
        and chart_comparable
        and selected_returns["mean_net_return_pct"] < rules["mean_net_return_pct"]
    ):
        failures.append(
            "Selected held-out mean net return is below the sufficiently sized chart-rule cohort."
        )
    normalized = [
        dict(
            symbol=e.symbol,
            observed_on=e.observed_on.isoformat(),
            label_end=e.label_end.isoformat(),
            features=e.features,
            label=e.label,
            net_return=e.net_return_pct,
            benchmark=e.benchmark_return_pct,
            strength=e.rule_strength,
        )
        for e in sorted(dataset.examples, key=lambda item: (item.observed_on, item.symbol))
    ]
    artifact = dict(
        version=MODEL_VERSION,
        event=EVENT,
        horizon_days=dataset.horizon_days,
        feature_names=list(FEATURE_NAMES),
        feature_fingerprint=_fingerprint(FEATURE_NAMES),
        dataset_fingerprint=_fingerprint(normalized),
        policy_fingerprint=dataset.policy_fingerprint,
        completed_through=dataset.completed_through.isoformat(),
        trained_at=datetime.now(UTC).isoformat(),
        training_symbols=sorted(training_symbols),
        config=asdict(config),
        sampling=dataset.sampling,
        scaler=dict(center=center, scale=scale),
        classifier=dict(weights=weights, intercept=intercept),
        calibration=dict(
            method="Platt, calibration partition only",
            slope=slope,
            offset=offset,
            base_rate=calibration_base_rate,
        ),
        boundaries=dict(
            train=_period(train), calibration=_period(calibration), test=_period(test), **split
        ),
        test_metrics=dict(
            calibrated=metrics,
            raw=_metrics(raw, test),
            base_rate=baseline,
            calibration_base_rate=calibration_baseline,
            fixed_threshold=config.selection_threshold,
            model_selected=selected_returns,
            chart_rule_baseline=rules,
            chart_baseline_comparable=chart_comparable,
            model_selected_coverage=len(selected) / len(test),
            chart_rule_coverage=rules["samples"] / len(test),
            all_eligible_policy=_return_summary(test),
            ood_fraction=ood,
            matched_hold_mean_return_pct=fmean(e.benchmark_return_pct for e in test),
            date_block_uncertainty=interval,
        ),
        test_prediction_fingerprint=_fingerprint(
            [
                [e.symbol, e.observed_on.isoformat(), p, e.label, e.net_return_pct]
                for e, p in zip(test, probabilities, strict=True)
            ]
        ),
        promotion_gate=dict(
            passed=not failures,
            reasons=failures,
            note="Passing historical gates permits opt-in advisory research; it does not prove a live trading edge.",
        ),
        limitations=LIMITATIONS,
    )
    artifact["model_id"] = (
        MODEL_VERSION
        + ":"
        + _fingerprint(
            {
                k: artifact[k]
                for k in (
                    "dataset_fingerprint",
                    "policy_fingerprint",
                    "config",
                    "completed_through",
                    "sampling",
                    "boundaries",
                )
            }
        )[:24]
    )
    artifact["artifact_fingerprint"] = _fingerprint(artifact)
    return artifact


def verify_model_artifact(artifact: dict) -> None:
    try:
        content = {k: v for k, v in artifact.items() if k != "artifact_fingerprint"}
        vectors = [
            artifact["scaler"]["center"],
            artifact["scaler"]["scale"],
            artifact["classifier"]["weights"],
        ]
        parameters = [v for vector in vectors for v in vector] + [
            artifact["classifier"]["intercept"],
            artifact["calibration"]["slope"],
            artifact["calibration"]["offset"],
        ]
        valid = (
            artifact["version"] == MODEL_VERSION
            and artifact["event"] == EVENT
            and artifact["feature_names"] == list(FEATURE_NAMES)
            and artifact["feature_fingerprint"] == _fingerprint(FEATURE_NAMES)
            and artifact["artifact_fingerprint"] == _fingerprint(content)
            and all(len(vector) == len(FEATURE_NAMES) for vector in vectors)
            and all(math.isfinite(value) for value in parameters)
            and min(artifact["scaler"]["scale"]) > 0
            and artifact["calibration"]["slope"] >= 0
            and artifact["horizon_days"] in (3, 22)
            and isinstance(artifact["promotion_gate"]["passed"], bool)
            and isinstance(artifact["training_symbols"], list)
            and bool(artifact["training_symbols"])
            and bool(date.fromisoformat(artifact["completed_through"]))
        )
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise ModelValidationError(
            "invalid_artifact", "Model schema, parameters or artifact fingerprint is invalid."
        )


def predict_probability(
    artifact: dict,
    bars: Sequence[PriceBar],
    *,
    as_of: date,
    require_promotion: bool = True,
    corporate_actions: Sequence[CorporateAction] = (),
    cost_engine: CostEngine | None = None,
) -> dict:
    verify_model_artifact(artifact)
    if artifact["policy_fingerprint"] != label_policy_fingerprint(
        artifact["horizon_days"], cost_engine
    ):
        raise ModelValidationError(
            "policy_changed",
            "Current fee or label policy differs from model validation; retraining is required.",
        )
    if require_promotion and not artifact["promotion_gate"]["passed"]:
        raise ModelValidationError(
            "unvalidated_model", "Candidate failed held-out gates; it cannot influence buy advice."
        )
    completed = date.fromisoformat(artifact["completed_through"])
    if as_of < completed or (as_of - completed).days > 90:
        raise ModelValidationError(
            "model_date", "Model is stale or the feature date precedes completed validation."
        )
    tape = sorted(
        (b for b in bars if b.business_date <= as_of and is_trading_day(b.business_date)),
        key=lambda b: b.business_date,
    )[-FEATURE_LOOKBACK:]
    if not tape or tape[-1].business_date != as_of or len(tape) < FEATURE_LOOKBACK:
        raise ModelValidationError(
            "stale_features",
            "Require 50 observations and a usable quote for the requested completed session.",
        )
    symbol = tape[-1].symbol
    if any(
        ca.symbol == symbol and tape[0].business_date <= ca.ex_date <= as_of
        for ca in corporate_actions
    ):
        raise ModelValidationError(
            "corporate_action",
            "Recent corporate action invalidates the model's raw-price feature window.",
        )
    if symbol not in artifact["training_symbols"] or any(b.symbol != symbol for b in tape):
        raise ModelValidationError(
            "unknown_security", "The security was not represented in model training."
        )
    if len({b.business_date for b in tape}) != len(tape):
        raise ModelValidationError(
            "duplicate_dates", "Current history contains duplicate sessions."
        )
    state = _feature_state(tape)
    if state is None:
        raise ModelValidationError(
            "invalid_features", "Current price/volume evidence is insufficient for this model."
        )
    features = _features(state, tape[-2].close)
    if not all(math.isfinite(v) for v in features):
        raise ModelValidationError(
            "invalid_features", "Current features contain non-finite values."
        )
    center, scale = artifact["scaler"]["center"], artifact["scaler"]["scale"]
    if max(abs((v - m) / s) for v, m, s in zip(features, center, scale, strict=True)) > 6:
        raise ModelValidationError(
            "out_of_domain", "Current features exceed the model's supported training domain."
        )
    params = artifact["classifier"]
    logit = params["intercept"] + sum(
        w * x for w, x in zip(params["weights"], _scale(features, center, scale), strict=True)
    )
    probability = min(
        0.99,
        max(
            0.01,
            _sigmoid(artifact["calibration"]["slope"] * logit + artifact["calibration"]["offset"]),
        ),
    )
    return dict(
        probability=round(probability, 4),
        event=EVENT,
        horizon_days=artifact["horizon_days"],
        model_id=artifact["model_id"],
        as_of=as_of.isoformat(),
        eligible_for_advisory=artifact["promotion_gate"]["passed"],
        label="Validated model estimate"
        if artifact["promotion_gate"]["passed"]
        else "Research-only estimate",
        limitations=LIMITATIONS,
    )
