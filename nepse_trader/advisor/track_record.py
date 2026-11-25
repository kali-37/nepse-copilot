"""Prospective, versioned recommendation evidence; no retrospective win claims."""

from __future__ import annotations

import json
import math
from datetime import date, datetime, time, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from nepse_trader.advisor.confidence import market, wilson_lower_bound
from nepse_trader.advisor.journal import log_prediction
from nepse_trader.advisor.outcomes import (
    EXCLUDED,
    EXPIRED_DOWN,
    EXPIRED_FLAT,
    EXPIRED_UP,
    NO_DATA,
    NOT_ENTERED,
    STOP_HIT,
    TARGET_HIT,
    UNRESOLVED,
    OutcomeResult,
    persist_score,
)
from nepse_trader.analysis.costs import CostEngine
from nepse_trader.calendar import add_trading_days, is_trading_day, next_trading_day
from nepse_trader.models import OrderSide

ENGINE_VERSION = "decision_v1"
METHOD = (
    "First published idea per symbol, horizon and market session. Fixed 100-share "
    "research benchmark enters at the first trading session's open after publication "
    "(today for pre-open publication), only inside "
    "the saved entry zone. Stops and targets remain fixed, exits wait for T+2, "
    "stop wins ambiguous candles, and gaps use the worse available open. "
    "Fees and tax are modeled. Missing sessions and corporate actions are excluded. "
    "These are simulated outcomes of forward-recorded ideas, not broker fills."
)


def record_recommendations(conn, board: dict) -> None:
    made = date.fromisoformat(board["requested_date"])
    if made != date.today() or board["stale"] or not board["market_date"]:
        return  # Past cached boards cannot create a prospective track record.
    engine = CostEngine()
    published = datetime.fromisoformat(board["generated_at"]).astimezone(ZoneInfo("Asia/Kathmandu"))
    entry_on = (
        next_trading_day(published.date())
        if published.time() < time(11)
        else next_trading_day(published.date() + timedelta(days=1))
    )
    for horizon, ideas in board["buys"].items():
        for idea in ideas:
            identity = f"{ENGINE_VERSION}:{board['market_date']}:{idea['symbol']}:{horizon}"
            if conn.execute(
                "SELECT 1 FROM predictions WHERE prediction_id=?", (identity,)
            ).fetchone():
                continue
            buy = engine.compute(OrderSide.BUY, idea["entry_high"], 100)
            sell = engine.compute(
                OrderSide.SELL,
                idea["target"],
                100,
                buy_cost_basis=buy.net_amount,
                holding_days=idea["horizon_days"],
            )
            card = SimpleNamespace(
                **{
                    key: idea[key]
                    for key in (
                        "symbol",
                        "horizon_days",
                        "reference_price",
                        "entry_low",
                        "entry_high",
                        "stop",
                    )
                },
                action="buy",
                targets=[idea["target"]],
                quantity=100,
                net_pnl=sell.net_amount - buy.net_amount,
                rationale=json.dumps(
                    {
                        "reasons": idea["rationale"],
                        "fundamentals": idea.get("fundamental_report"),
                        "published_at": board["generated_at"],
                        "method": METHOD,
                    }
                ),
            )
            score = idea["confidence"]
            log_prediction(
                conn,
                card,
                made_on=made,
                horizon=horizon,
                kind=ENGINE_VERSION,
                prediction_id=identity,
                confidence=market(score["value"], score["basis"]),
                commit=False,
            )
            conn.execute(
                "UPDATE predictions SET forecast_entry_on=?,deadline=? WHERE prediction_id=?",
                (
                    entry_on.isoformat(),
                    add_trading_days(entry_on, idea["horizon_days"] - 1).isoformat(),
                    identity,
                ),
            )


def evaluate_recommendation(
    prediction, bars, *, as_of=None, cost_engine=None, corporate_actions=()
) -> OutcomeResult:
    row = dict(prediction)
    made = date.fromisoformat(row["made_on"])
    entry_on = (
        date.fromisoformat(row["forecast_entry_on"])
        if row.get("forecast_entry_on")
        else next_trading_day(made + timedelta(days=1))
    )
    deadline = date.fromisoformat(row["deadline"])
    cutoff = as_of or max((b.business_date for b in bars), default=made)
    engine = cost_engine or CostEngine()

    def result(outcome, note, *, entry=None, exit_price=None, resolved=None, seen=0, hit=None):
        pnl = net_return = baseline = None
        if entry is not None and exit_price is not None and resolved is not None:
            buy = engine.compute(OrderSide.BUY, entry, 100)
            sell = engine.compute(
                OrderSide.SELL,
                exit_price,
                100,
                buy_cost_basis=buy.net_amount,
                holding_days=(resolved - entry_on).days,
            )
            pnl = sell.net_amount - buy.net_amount
            net_return = float(pnl / buy.net_amount * 100)
            close = tape[resolved].close
            hold = engine.compute(
                OrderSide.SELL,
                close,
                100,
                buy_cost_basis=buy.net_amount,
                holding_days=(resolved - entry_on).days,
            )
            baseline = float((hold.net_amount - buy.net_amount) / buy.net_amount * 100)
        return OutcomeResult(
            prediction_id=row["prediction_id"],
            symbol=row["symbol"],
            outcome=outcome,
            hit=hit,
            resolved_on=resolved,
            realized_exit_price=exit_price,
            realized_net_pnl=pnl,
            bars_seen=seen,
            basis=note,
            entry_on=entry_on,
            entry_price=entry,
            net_return_pct=net_return,
            benchmark_return_pct=baseline,
        )

    if cutoff < entry_on:
        return result(UNRESOLVED, "The next-session entry has not completed yet.")
    action_dates = {
        ca.ex_date
        for ca in corporate_actions
        if ca.symbol == row["symbol"]
        and (made < ca.ex_date or ca.ex_date == entry_on == made)
        and ca.ex_date <= min(cutoff, deadline)
    }
    if any(d <= entry_on for d in action_dates):
        return result(
            EXCLUDED, "Corporate action changed share units or price levels; excluded from returns."
        )
    tape = {
        b.business_date: b
        for b in bars
        if b.symbol == row["symbol"] and entry_on <= b.business_date <= min(cutoff, deadline)
    }
    first = tape.get(entry_on)
    if first is None or first.open is None or not math.isfinite(first.open) or first.open <= 0:
        return result(NO_DATA, "The planned entry session has no usable opening price.")
    entry = first.open
    if not row["entry_low"] <= entry <= row["entry_high"]:
        return result(
            NOT_ENTERED,
            "Next-session open was outside the saved entry zone; no modeled purchase.",
            entry=entry,
        )
    if not row["stop"] < entry < row["target_1"]:
        return result(
            NOT_ENTERED,
            "Opening gap invalidated the saved stop/target plan; no modeled purchase.",
            entry=entry,
        )
    earliest_sell = add_trading_days(entry_on, 2)
    session, seen = entry_on, 0
    while session <= min(cutoff, deadline):
        if is_trading_day(session):
            if any(entry_on < d <= session for d in action_dates):
                return result(
                    EXCLUDED,
                    "Corporate action changed the open holding before its exit; excluded from returns.",
                    entry=entry,
                    seen=seen,
                )
            bar = tape.get(session)
            if (
                bar is None
                or any(
                    v is None or not math.isfinite(v) or v <= 0
                    for v in (bar.open, bar.high, bar.low, bar.close)
                )
                or not bar.low <= min(bar.open, bar.close) <= max(bar.open, bar.close) <= bar.high
            ):
                return result(
                    NO_DATA,
                    "A required session is missing or has invalid OHLC; no reliable outcome.",
                    entry=entry,
                    seen=seen,
                )
            seen += 1
            if session >= earliest_sell:
                if bar.low <= row["stop"]:
                    return result(
                        STOP_HIT,
                        "Saved stop reached after settlement; stop checked first and gaps priced conservatively.",
                        entry=entry,
                        exit_price=min(row["stop"], bar.open),
                        resolved=session,
                        seen=seen,
                        hit=0,
                    )
                if bar.high >= row["target_1"]:
                    return result(
                        TARGET_HIT,
                        "Saved target reached after settlement; modeled fill remains unverified.",
                        entry=entry,
                        exit_price=row["target_1"],
                        resolved=session,
                        seen=seen,
                        hit=1,
                    )
        session += timedelta(days=1)
    if cutoff < deadline:
        return result(
            UNRESOLVED, "The fixed horizon has not completed yet.", entry=entry, seen=seen
        )
    last = tape[deadline].close
    outcome = EXPIRED_UP if last > entry else EXPIRED_DOWN if last < entry else EXPIRED_FLAT
    return result(
        outcome,
        "Horizon expired at the recorded session close after modeled fees.",
        entry=entry,
        exit_price=last,
        resolved=deadline,
        seen=seen,
        hit=0,
    )


def score_recommendations(pipe, *, completed: date, limit: int = 200) -> dict:
    engine, tapes, actions = CostEngine(), {}, {}
    counts = {"checked": 0, "resolved": 0, "excluded": 0}
    with pipe.storage._tx() as conn:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            """SELECT * FROM predictions WHERE kind=? AND status='open'
            AND forecast_entry_on<=? ORDER BY COALESCE(evaluation_checked_at,created_at),id LIMIT ?""",
            (ENGINE_VERSION, completed.isoformat(), limit),
        ).fetchall()
        for row in rows:
            symbol = row["symbol"]
            if symbol not in tapes:
                tapes[symbol] = pipe.reconciled_bars(symbol, adjusted=False, as_of=completed)
                actions[symbol] = pipe.storage.corporate_actions(symbol)
            result = evaluate_recommendation(
                row,
                tapes[symbol],
                as_of=completed,
                cost_engine=engine,
                corporate_actions=actions[symbol],
            )
            persist_score(conn, result)
            counts["checked"] += 1
            counts["resolved"] += result.calibration_eligible
            counts["excluded"] += result.outcome in {EXCLUDED, NOT_ENTERED}
    return counts


def performance_report(storage) -> dict:
    conn = storage._conn
    counts = {
        row[0] or UNRESOLVED: row[1]
        for row in conn.execute(
            "SELECT outcome,COUNT(*) FROM predictions WHERE kind=? GROUP BY outcome",
            (ENGINE_VERSION,),
        )
    }
    resolved = sum(
        counts.get(k, 0) for k in (TARGET_HIT, STOP_HIT, EXPIRED_UP, EXPIRED_DOWN, EXPIRED_FLAT)
    )
    buckets = []
    for lower, upper in ((0, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 1.01)):
        row = conn.execute(
            """SELECT COUNT(*) n,SUM(evaluation_net_return>0) profitable,
            AVG(confidence) mean_score,AVG(evaluation_net_return) mean_return,
            AVG(evaluation_net_return-evaluation_benchmark_return) mean_excess
            FROM predictions WHERE kind=? AND evaluation_net_return IS NOT NULL
            AND confidence>=? AND confidence<?""",
            (ENGINE_VERSION, lower, upper),
        ).fetchone()
        n, hits = row["n"], row["profitable"] or 0
        buckets.append(
            dict(
                lower=lower,
                upper=min(upper, 1),
                samples=n,
                profitable_rate=hits / n if n else None,
                interval_low=wilson_lower_bound(hits, n) if n else None,
                interval_high=1 - wilson_lower_bound(n - hits, n) if n else None,
                mean_score=row["mean_score"],
                mean_net_return=row["mean_return"],
                mean_excess_return=row["mean_excess"],
            )
        )
    recent = [
        dict(row)
        for row in conn.execute(
            """SELECT prediction_id,symbol,made_on,horizon,confidence,outcome,status,
        evaluation_entry_on,evaluation_entry_price,evaluation_net_return,
        evaluation_benchmark_return,evaluation_note FROM predictions
        WHERE kind=? ORDER BY made_on DESC,id DESC LIMIT 20""",
            (ENGINE_VERSION,),
        )
    ]
    oldest = conn.execute(
        "SELECT MIN(created_at) FROM predictions WHERE kind=?", (ENGINE_VERSION,)
    ).fetchone()[0]
    return dict(
        engine_version=ENGINE_VERSION,
        total=sum(counts.values()),
        resolved=resolved,
        tracking_since=oldest,
        status="collecting_evidence" if resolved < 30 else "measured_history",
        outcomes=counts,
        buckets=buckets,
        recent=recent,
        method=METHOD,
        note="Evidence scores are not win probabilities. Unfilled and excluded ideas are disclosed, not counted as losses or wins. Small samples and correlated stocks cannot establish an investment edge. The baseline holds the same stock to each modeled exit date; this is not an index or portfolio benchmark.",
    )
