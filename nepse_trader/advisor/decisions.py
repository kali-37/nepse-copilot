"""A decision-first view of the market and the user's saved holdings."""

from __future__ import annotations

import json
import math
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from nepse_trader.advisor.confidence import market
from nepse_trader.advisor.decision_signals import (
    chart_states,
    evidence_confidence,
    historical_evidence,
)
from nepse_trader.advisor.decision_state import decision_state, market_date, session_dates
from nepse_trader.advisor.positions import available_cash, owned_positions
from nepse_trader.analysis.costs import CostEngine
from nepse_trader.calendar import (
    add_trading_days,
    is_trading_day,
    previous_trading_day,
)
from nepse_trader.models import OrderSide


def build_decisions(pipe, *, today: date | None = None, on_progress=None, check_cancelled=None) -> dict:
    today = today or date.today()
    state_key = decision_state(pipe, today)
    observed = market_date(pipe.storage, today)
    cash = available_cash(pipe.storage)
    holdings = owned_positions(pipe)
    owned = {p["symbol"] for p in holdings}
    expected, trade_date, phase = session_dates(today)
    stale = observed is None or observed < expected
    engine = CostEngine()
    ideas = {"day": [], "month": []}
    details = {}
    names = sorted(owned) + sorted(set(pipe.storage.symbols()) - owned)[:max(0, 500 - len(owned))]
    for index, symbol in enumerate(names, 1):
        if check_cancelled:
            check_cancelled()
        bars = pipe.reconciled_bars(symbol, as_of=observed or today)[-520:]
        if observed:
            bars = [bar for bar in bars if bar.business_date <= observed]
        states = chart_states(bars)
        state = states[-1] if states else None
        if bars and bars[-1].close is not None and bars[-1].close > 0 and math.isfinite(bars[-1].close):
            chart = [{"date": bar.business_date.isoformat(), "close": bar.close} for bar in bars[-45:] if bar.close is not None]
            reconciled = next(r for r in reversed(pipe.storage.reconciled_history(symbol)) if r.business_date == bars[-1].business_date)
            quality = max(0.2, reconciled.confidence) * (1 if len(reconciled.sources_present) >= 2 else 0.88)
            details[symbol] = (state, chart, quality, bars[-1].business_date, bars[-1].close)
        if state:
            reconciled = next(r for r in reversed(pipe.storage.reconciled_history(symbol)) if r.business_date == bars[-1].business_date)
            quality = max(0.2, reconciled.confidence) * (1 if len(reconciled.sources_present) >= 2 else 0.88)
            if bars[-1].business_date < expected:
                quality *= 0.55
            if state.average_volume < 1000:
                quality *= 0.6
            chart = [{"date": bar.business_date.isoformat(), "close": bar.close} for bar in bars[-45:]]
            details[symbol] = (state, chart, quality, bars[-1].business_date, state.close)
            for horizon, days in [("day", 3), ("month", 22)]:
                strength = state.strength(days)
                hits, total = historical_evidence(bars, states, days, completed_through=expected if phase not in ("pre_open", "market_hours") else previous_trading_day(today - timedelta(days=1)))
                confidence = evidence_confidence(state, days, hits, total, quality)
                if symbol in owned or stale or bars[-1].business_date != observed or state.average_volume < 1000 or strength < 0.6 or confidence["value"] < 0.5:
                    continue
                distance = state.atr * (1 if days == 3 else 2)
                stop = round(max(state.close * 0.9, state.close - distance), 2)
                target = round(state.close + state.atr * (1.5 if days == 3 else 3), 2)
                ideas[horizon].append(dict(symbol=symbol, action="buy", horizon=horizon, horizon_days=days,
                    reference_price=state.close, entry_low=round(max(0.01, state.close - state.atr * 0.2), 2),
                    entry_high=round(state.close + state.atr * 0.2, 2), stop=stop, target=target,
                    confidence=confidence, rationale=state.reasons(), chart=chart,
                    metrics={"rsi": round(state.rsi, 1), "volume_ratio": round(state.volume_ratio, 2),
                             "trend_20": round(state.ma20, 2), "trend_50": round(state.ma50, 2)},
                    earliest_sell_date=add_trading_days(trade_date, 2).isoformat()))
        if on_progress:
            on_progress(index, len(names), symbol)
    allocated = Decimal(0)
    selected_symbols = set()
    for horizon, weight in [("day", Decimal("0.4")), ("month", Decimal("0.6"))]:
        budget = cash * weight
        ranked = sorted(ideas[horizon], key=lambda item: (-item["confidence"]["value"], -item["metrics"]["volume_ratio"], item["symbol"]))
        selected = []
        for idea in ranked:
            if idea["symbol"] in selected_symbols:
                continue
            per_name = min(budget, cash * weight / 3)
            price = idea["entry_high"]
            risk = max(0.01, price - idea["stop"])
            quantity = min(int(per_name / Decimal(str(price))), int(float(cash) * 0.02 / risk)) // 10 * 10
            while quantity and engine.compute(OrderSide.BUY, price, quantity).net_amount > per_name:
                quantity -= 10
            if quantity <= 0:
                continue
            buy = engine.compute(OrderSide.BUY, price, quantity)
            sell = engine.compute(OrderSide.SELL, idea["target"], quantity, buy_cost_basis=buy.net_amount, holding_days=idea["horizon_days"])
            if sell.net_amount <= buy.net_amount:
                continue
            idea.update(quantity=quantity, outlay=float(buy.net_amount), estimated_net=float(sell.net_amount - buy.net_amount),
                        estimated_fees=float(buy.total_fees + sell.total_fees))
            budget -= buy.net_amount
            allocated += buy.net_amount
            selected.append(idea)
            selected_symbols.add(idea["symbol"])
            if len(selected) == 3:
                break
        ideas[horizon] = selected
    owned_advice = []
    for position in holdings:
        symbol = position["symbol"]
        item = details.get(symbol)
        state, chart, quality, quote_date, quote = item if item else (None, [], 0, None, None)
        basis = Decimal(position["cost_basis"]) if position["cost_basis"] is not None else None
        pnl = float(Decimal(str(quote)) * position["quantity"] - basis) if quote is not None and basis is not None else None
        reason, action = "Your saved exit plan has not triggered.", "hold"
        if quote is None:
            reason, action = "No usable quote yet. Refresh market data.", "review"
        elif position["stop"] is not None and quote <= position["stop"]:
            reason, action = "Price has reached your saved stop-loss.", "sell"
        elif position["target"] is not None and quote >= position["target"]:
            reason, action = "Price has reached your saved take-profit target.", "sell"
        elif state is not None and state.strength(22) < 0.35:
            reason, action = "The trend and momentum have weakened. Consider reducing this holding.", "sell"
        elif position["bought_on"] and today >= add_trading_days(date.fromisoformat(position["bought_on"]), position["horizon_days"]):
            reason, action = "Your planned holding period is complete. Review or close this position.", "review"
        if action == "hold" and state is None:
            reason, action = "A quote is available, but there is not enough history to judge the trend.", "review"
        elif action == "hold" and position["stop"] is None:
            reason = "The trend supports holding. Set an exit plan to save fixed price levels."
        if quote_date and quote_date < expected:
            reason, action = "This quote is stale. Refresh before making an exit decision.", "review"
        actions = pipe.storage.corporate_actions(symbol)
        if position["bought_on"] and any(max(position["bought_on"], position.get("plan_reviewed_on") or "") < ca.ex_date.isoformat() <= today.isoformat() for ca in actions):
            reason, action = "A corporate action occurred after purchase. Confirm your current share quantity and exit levels before selling.", "review"
        triggered = quote is not None and ((position["stop"] is not None and quote <= position["stop"]) or (position["target"] is not None and quote >= position["target"]))
        certainty = 0 if action == "review" else 0.9 * quality if triggered else ((1 - state.strength(22)) if action == "sell" else state.strength(22)) * quality if state else 0
        confidence = market(certainty, reason).as_dict()
        confidence.update(kind="exit_evidence", label="Exit trigger" if action == "sell" else "Holding evidence")
        earliest = add_trading_days(date.fromisoformat(position["bought_on"]), 2) if position["bought_on"] else None
        net_exit_pnl = None
        if quote is not None and basis is not None:
            holding_days = (today - date.fromisoformat(position["bought_on"])).days if position["bought_on"] else None
            net_exit_pnl = float(engine.compute(OrderSide.SELL, quote, position["quantity"], buy_cost_basis=basis, holding_days=holding_days).net_amount - basis)
        owned_advice.append({**position, "cost_basis": float(basis) if basis is not None else None,
            "average_cost": float(basis / position["quantity"]) if basis is not None else None,
            "reference_price": quote, "quote_date": quote_date.isoformat() if quote_date else None,
            "unrealized_pnl": pnl, "net_exit_pnl": net_exit_pnl, "action": action, "reason": reason, "confidence": confidence,
            "earliest_sell_date": earliest.isoformat() if earliest else None, "settled": today >= earliest if earliest else None,
            "chart": chart})
    return dict(state_key=state_key, requested_date=today.isoformat(), market_date=observed.isoformat() if observed else None,
        generated_at=datetime.now(UTC).isoformat(), session="trading_day" if is_trading_day(today) else "closed",
        session_phase=phase, earliest_entry_date=trade_date.isoformat(),
        stale=stale, available_cash=float(cash), planned_outlay=float(allocated), cash_reserved=float(cash - allocated),
        buys=ideas, holdings=owned_advice, coverage={"symbols": len(names), "analysable": sum(1 for detail in details.values() if detail[0] is not None)},
        confidence_note="Confidence measures the strength of available evidence, not a guaranteed win probability.")


def save_decisions(pipe, board: dict) -> dict:
    storage = pipe.storage
    board = {**board, "id": uuid.uuid4().hex}
    with storage._tx() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if board.get("state_key") != decision_state(pipe, date.fromisoformat(board["requested_date"])):
            raise DecisionsChanged("Market or holdings changed during analysis. Rebuilding advice.")
        conn.execute("INSERT INTO decision_runs(id,generated_at,payload) VALUES(?,?,?)", (board["id"], board["generated_at"], json.dumps(board)))
        conn.execute("DELETE FROM decision_runs WHERE id NOT IN (SELECT id FROM decision_runs ORDER BY generated_at DESC LIMIT 30)")
    return board


class DecisionsChanged(ValueError):
    pass


def publish_decisions(pipe, board: dict | None = None) -> dict:
    for _ in range(3):
        board = board or build_decisions(pipe)
        try:
            return save_decisions(pipe, board)
        except DecisionsChanged:
            board = None
    raise DecisionsChanged("Market or holdings are changing. Refresh advice again.")
