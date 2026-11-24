"""A holding keeps its original plan; exits require named, persistent triggers."""

from __future__ import annotations

import hashlib
import json
from datetime import date

from nepse_trader.advisor.confidence import market
from nepse_trader.advisor.entry_plan import decode_plan
from nepse_trader.calendar import add_trading_days


def plan_key(position: dict) -> str:
    thesis = decode_plan(position) or {}
    identity = [
        position["symbol"],
        thesis.get("id"),
        position.get("plan_revision", 0),
        position["stop"],
        position["target"],
        position["horizon_days"],
    ]
    return hashlib.sha256(json.dumps(identity).encode()).hexdigest()


def holding_advice(
    pipe,
    position,
    bars,
    states,
    *,
    quote,
    quality,
    expected,
    completed,
    today,
    fundamental_report=None,
) -> dict:
    thesis = decode_plan(position)
    horizon = position["horizon_days"]
    name = "daily" if horizon <= 3 else "monthly" if horizon <= 22 else "long-term"
    opened = (thesis or {}).get("opened_on") or position["bought_on"]
    review_on = (
        add_trading_days(date.fromisoformat(opened), horizon).isoformat() if opened else None
    )
    earliest = (
        add_trading_days(date.fromisoformat(position["bought_on"]), 2)
        if position["bought_on"]
        else None
    )
    settled = today >= earliest if earliest else None
    key = plan_key(position)
    required = 2 if horizon <= 3 else 3 if horizon <= 22 else 5
    anchor = max(opened or "", position.get("plan_reviewed_on") or "")
    by_date = {bar.business_date: state for bar, state in zip(bars, states, strict=True)}
    confirmations = 0
    for offset in range(required):
        session = add_trading_days(completed, -offset)
        state = by_date.get(session)
        if (
            not anchor
            or session.isoformat() <= anchor
            or state is None
            or state.strength(horizon) >= 0.35
        ):
            break
        confirmations += 1
    state = states[-1] if states else None
    sticky = pipe.storage._conn.execute(
        """SELECT * FROM holding_advice_events
        WHERE symbol=? AND plan_key=? AND action='sell' ORDER BY id DESC LIMIT 1""",
        (position["symbol"], key),
    ).fetchone()
    action, trigger = "hold", "plan_intact"
    reason = f"Keep your {name} plan. Its saved stop and target have not triggered."
    if quote is None:
        action, trigger, reason = "review", "no_quote", "No usable quote yet. Refresh market data."
    elif bars[-1].business_date < expected:
        action, trigger, reason = (
            "review",
            "stale_quote",
            "This quote is stale. Refresh before deciding on an exit.",
        )
    elif opened and any(
        max(opened, position.get("plan_reviewed_on") or "")
        < ca.ex_date.isoformat()
        <= today.isoformat()
        for ca in pipe.storage.corporate_actions(position["symbol"])
    ):
        action, trigger = "review", "corporate_action"
        reason = "A corporate action occurred after purchase. Confirm current shares and exit levels before selling."
    elif position["stop"] is not None and quote <= position["stop"]:
        action, trigger, reason = (
            "sell",
            "stop_hit",
            f"Price reached your saved stop-loss of NPR {position['stop']:.2f}.",
        )
    elif position["target"] is not None and quote >= position["target"]:
        action, trigger, reason = (
            "sell",
            "target_hit",
            f"Price reached your saved take-profit target of NPR {position['target']:.2f}.",
        )
    elif sticky:
        action, trigger = "sell", sticky["trigger_code"]
        reason = f"Your exit condition was confirmed on {sticky['market_date']}. It stays pending until you record a sale or explicitly review your exit plan."
    elif fundamental_report and fundamental_report["rating"] == "unsupported":
        action, trigger = "review", "fundamental_deterioration"
        entry_fundamentals = ((thesis or {}).get("origin") or {}).get("fundamental_report") or {}
        entry_note = ""
        if entry_fundamentals.get("eps") is not None:
            entry_note = f"At entry, reported EPS was {entry_fundamentals['eps']:.2f} and book value was {entry_fundamentals.get('book_value')}. "
        reason = (
            entry_note
            + " ".join(fundamental_report["reasons"])
            + f" Snapshot {fundamental_report['snapshot_date']}; review the financial thesis before adding risk."
        )
    elif state is None:
        action, trigger = "review", "insufficient_history"
        reason = "A quote is available, but there is not enough history to judge the holding trend."
    elif settled is None:
        action, trigger = "review", "unknown_entry"
        reason = "Confirm your purchase date and exit plan. The original entry and settlement date are unknown."
    elif confirmations >= required:
        action, trigger = "sell", "confirmed_weakness"
        reason = f"Your {name} trend has weakened for {confirmations} consecutive completed sessions after entry. Review deadline and shortlists did not trigger this exit."
    elif review_on and today.isoformat() >= review_on:
        action, trigger = "review", "horizon_review"
        reason = f"Your {name} review date ({review_on}) has arrived. Review the evidence before deciding whether to keep or close it."
    elif confirmations:
        trigger = "weakness_pending"
        reason = f"Keep your {name} plan for now. Weakness is confirmed for {confirmations}/{required} completed sessions; one changing signal does not trigger a trend exit."
    elif position["stop"] is None:
        trigger = "missing_exit_plan"
        reason = "The trend supports holding. Set an exit plan to save fixed price levels."
    if action == "sell" and settled is None:
        action, trigger = "review", "unknown_settlement"
        reason += " Confirm settlement with your broker before selling."
    if action == "hold" and fundamental_report:
        if fundamental_report["rating"] in ("caution", "expensive"):
            reason += " " + fundamental_report["reasons"][-1]
        elif fundamental_report["needs_refresh"]:
            reason += (
                " Financial support is unconfirmed; refresh its snapshot before adding shares."
            )
    strength = state.strength(horizon) if state else 0
    value = (
        0
        if action == "review"
        else quality
        * (
            0.9
            if trigger in ("stop_hit", "target_hit")
            else 1 - strength
            if action == "sell"
            else strength
        )
    )
    if sticky and action == "sell" and trigger == "confirmed_weakness":
        value = sticky["confidence"]
    if action == "hold" and fundamental_report:
        factor = (
            fundamental_report["multiplier"] if not fundamental_report["needs_refresh"] else 0.8
        )
        value *= factor
    score = market(
        value,
        f"{reason} Current {name} chart evidence; original entry confidence is kept separately.",
    ).as_dict()
    score.update(
        kind="holding_evidence", label="Exit evidence" if action == "sell" else "Holding evidence"
    )
    return dict(
        action=action,
        trigger_code=trigger,
        reason=reason,
        confidence=score,
        plan_key=key,
        original_plan=thesis,
        fundamental_report=fundamental_report,
        review_on=review_on,
        holding_horizon=name,
        trend_confirmations=confirmations,
        confirmations_required=required,
        earliest_sell_date=earliest.isoformat() if earliest else None,
        settled=settled,
        exit_status="waiting_settlement"
        if action == "sell" and settled is False
        else "actionable"
        if action == "sell"
        else "review"
        if action == "review"
        else "hold",
    )


def record_advice_history(conn, board) -> None:
    for holding in board["holdings"]:
        key, symbol = holding["plan_key"], holding["symbol"]
        prior = conn.execute(
            "SELECT * FROM holding_advice_events WHERE symbol=? AND plan_key=? ORDER BY id DESC LIMIT 1",
            (symbol, key),
        ).fetchone()
        if not prior or (prior["action"], prior["trigger_code"]) != (
            holding["action"],
            holding["trigger_code"],
        ):
            conn.execute(
                """INSERT INTO holding_advice_events(symbol,plan_key,market_date,action,trigger_code,
                previous_action,reason,confidence,evaluated_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    symbol,
                    key,
                    board["market_date"],
                    holding["action"],
                    holding["trigger_code"],
                    prior["action"] if prior else None,
                    holding["reason"],
                    holding["confidence"]["value"],
                    board["generated_at"],
                ),
            )
        holding["advice_history"] = [
            dict(row)
            for row in conn.execute(
                """SELECT market_date,action,previous_action,plan_key,
            trigger_code,reason,confidence,evaluated_at FROM holding_advice_events
            WHERE symbol=? ORDER BY id DESC LIMIT 8""",
                (symbol,),
            )
        ]
