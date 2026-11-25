"""A decision-first view of the market and the user's saved holdings."""

from __future__ import annotations

import json
import math
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from nepse_trader.advisor.decision_signals import (
    chart_states,
    evidence_confidence,
    historical_evidence,
    reliable_volume,
)
from nepse_trader.advisor.decision_state import decision_state, market_date, session_dates
from nepse_trader.advisor.fundamentals import assess_fundamentals
from nepse_trader.advisor.holding_advice import holding_advice, record_advice_history
from nepse_trader.advisor.investments import investment_candidate
from nepse_trader.advisor.positions import available_cash, owned_positions
from nepse_trader.analysis.costs import CostEngine
from nepse_trader.calendar import (
    add_trading_days,
    is_trading_day,
    previous_trading_day,
)
from nepse_trader.models import OrderSide


def build_decisions(
    pipe, *, today: date | None = None, on_progress=None, check_cancelled=None
) -> dict:
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
    investments = []
    fundamental_checks = {}
    fundamentals = pipe.storage.fundamentals(as_of=today)
    snapshot_dates = {
        row[0]: date.fromisoformat(row[1])
        for row in pipe.storage._conn.execute(
            "SELECT symbol,MAX(business_date) FROM fundamentals WHERE business_date<=? GROUP BY symbol",
            (today.isoformat(),),
        )
    }
    cooldowns = {
        row[0]: add_trading_days(date.fromisoformat(row[1]), 3)
        for row in pipe.storage._conn.execute(
            "SELECT symbol,MAX(business_date) FROM position_records WHERE side='sell' GROUP BY symbol"
        )
    }
    completed = today if phase == "after_close" else previous_trading_day(today - timedelta(days=1))
    names = sorted(owned) + sorted(set(pipe.storage.symbols()) - owned)[: max(0, 500 - len(owned))]
    quote_metadata = {
        row["symbol"]: row
        for row in pipe.storage._conn.execute(
            """SELECT symbol, confidence, sources_present FROM reconciled_prices r
            WHERE business_date=(SELECT MAX(business_date) FROM reconciled_prices
                WHERE symbol=r.symbol AND business_date<=?)""",
            ((observed or today).isoformat(),),
        )
    }
    for index, symbol in enumerate(names, 1):
        if check_cancelled:
            check_cancelled()
        bars = pipe.reconciled_bars(symbol, as_of=observed or today)[-520:]
        if observed:
            bars = [bar for bar in bars if bar.business_date <= observed]
        states = chart_states(bars)
        state = states[-1] if states else None
        if (
            bars
            and bars[-1].close is not None
            and bars[-1].close > 0
            and math.isfinite(bars[-1].close)
        ):
            chart = [
                {"date": bar.business_date.isoformat(), "close": bar.close}
                for bar in bars[-45:]
                if bar.close is not None
            ]
            metadata = quote_metadata.get(symbol)
            if metadata is None:
                raise DecisionsChanged("A symbol received its first reconciled quote during analysis.")
            quality = max(0.2, metadata["confidence"] or 0) * (
                1 if len((metadata["sources_present"] or "").split(",")) >= 2 else 0.88
            )
            details[symbol] = (
                state,
                chart,
                quality,
                bars[-1].business_date,
                bars[-1].close,
                bars,
                states,
            )
        if state:
            if bars[-1].business_date < expected:
                quality *= 0.55
            if state.average_volume < 1000:
                quality *= 0.6
            chart = [
                {"date": bar.business_date.isoformat(), "close": bar.close} for bar in bars[-45:]
            ]
            details[symbol] = (
                state,
                chart,
                quality,
                bars[-1].business_date,
                state.close,
                bars,
                states,
            )
            if not stale and bars[-1].business_date == observed:
                candidate = investment_candidate(
                    symbol,
                    bars,
                    state,
                    quality,
                    fundamentals.get(symbol),
                    snapshot_date=snapshot_dates.get(symbol),
                    today=today,
                    owned=symbol in owned,
                    cost_engine=engine,
                )
                if candidate:
                    observed_sessions = pipe.storage._conn.execute(
                        "SELECT COUNT(DISTINCT business_date) FROM reconciled_prices WHERE business_date>=? AND business_date<=?",
                        (candidate["history_from"], candidate["history_to"]),
                    ).fetchone()[0]
                    count = sum(
                        candidate["history_from"]
                        <= b.business_date.isoformat()
                        <= candidate["history_to"]
                        for b in bars
                    )
                    if observed_sessions and count / observed_sessions >= 0.9:
                        if symbol in cooldowns and expected <= cooldowns[symbol]:
                            candidate["reconsider_after"] = add_trading_days(
                                cooldowns[symbol], 1
                            ).isoformat()
                        investments.append(candidate)
            fundamental = assess_fundamentals(
                fundamentals.get(symbol),
                quote=state.close,
                snapshot_date=snapshot_dates.get(symbol),
                today=today,
            )
            for horizon, days in [("day", 3), ("month", 22)]:
                strength = state.strength(days)
                hits, total = historical_evidence(
                    bars,
                    states,
                    days,
                    completed_through=expected
                    if phase not in ("pre_open", "market_hours")
                    else previous_trading_day(today - timedelta(days=1)),
                    cost_engine=engine,
                )
                confidence = evidence_confidence(state, days, hits, total, quality)
                technical_value = confidence["value"]
                if (
                    symbol not in owned
                    and not stale
                    and state.average_volume >= 1000
                    and strength >= 0.6
                    and technical_value >= 0.5
                    and fundamental["needs_refresh"]
                ):
                    fundamental_checks[symbol] = max(
                        technical_value, fundamental_checks.get(symbol, 0)
                    )
                confidence["value"] = round(technical_value * fundamental["multiplier"], 3)
                confidence["label"] = "Combined evidence"
                confidence["basis"] += (
                    f" Fundamental valuation/earnings factor {fundamental['multiplier']:.2f} ({fundamental['rating']}); missing or non-positive financial support prevents a new buy."
                )
                confidence.update(
                    technical_value=technical_value, fundamental_rating=fundamental["rating"]
                )
                if (
                    symbol in owned
                    or (symbol in cooldowns and expected <= cooldowns[symbol])
                    or stale
                    or bars[-1].business_date != observed
                    or state.average_volume < 1000
                    or not reliable_volume(bars)
                    or strength < 0.6
                    or confidence["value"] < 0.5
                ):
                    continue
                distance = state.atr * (1 if days == 3 else 2)
                stop = round(max(state.close * 0.9, state.close - distance), 2)
                target = round(state.close + state.atr * (1.5 if days == 3 else 3), 2)
                ideas[horizon].append(
                    dict(
                        symbol=symbol,
                        action="buy",
                        horizon=horizon,
                        horizon_days=days,
                        reference_price=state.close,
                        entry_low=round(max(0.01, state.close - state.atr * 0.2), 2),
                        entry_high=round(state.close + state.atr * 0.2, 2),
                        stop=stop,
                        target=target,
                        confidence=confidence,
                        fundamental_report=fundamental,
                        rationale=state.reasons() + fundamental["reasons"],
                        chart=chart,
                        metrics={
                            "rsi": round(state.rsi, 1),
                            "volume_ratio": round(state.volume_ratio, 2),
                            "trend_20": round(state.ma20, 2),
                            "trend_50": round(state.ma50, 2),
                        },
                        earliest_sell_date=add_trading_days(trade_date, 2).isoformat(),
                    )
                )
        if on_progress:
            on_progress(index, len(names), symbol)
    allocated = Decimal(0)
    selected_symbols = set()
    for horizon, weight in [("day", Decimal("0.4")), ("month", Decimal("0.6"))]:
        budget = cash * weight
        ranked = sorted(
            ideas[horizon],
            key=lambda item: (
                -item["confidence"]["value"],
                -item["metrics"]["volume_ratio"],
                item["symbol"],
            ),
        )
        selected = []
        for idea in ranked:
            if idea["symbol"] in selected_symbols:
                continue
            per_name = min(budget, cash * weight / 3)
            price = idea["entry_high"]
            risk = max(0.01, price - idea["stop"])
            quantity = (
                min(int(per_name / Decimal(str(price))), int(float(cash) * 0.02 / risk)) // 10 * 10
            )
            while quantity and engine.compute(OrderSide.BUY, price, quantity).net_amount > per_name:
                quantity -= 10
            if quantity <= 0:
                continue
            buy = engine.compute(OrderSide.BUY, price, quantity)
            sell = engine.compute(
                OrderSide.SELL,
                idea["target"],
                quantity,
                buy_cost_basis=buy.net_amount,
                holding_days=idea["horizon_days"],
            )
            if sell.net_amount <= buy.net_amount:
                continue
            idea.update(
                quantity=quantity,
                outlay=float(buy.net_amount),
                estimated_net=float(sell.net_amount - buy.net_amount),
                estimated_fees=float(buy.total_fees + sell.total_fees),
            )
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
        state, chart, quality, quote_date, quote, bars, states = (
            item if item else (None, [], 0, None, None, [], [])
        )
        basis = Decimal(position["cost_basis"]) if position["cost_basis"] is not None else None
        pnl = (
            float(Decimal(str(quote)) * position["quantity"] - basis)
            if quote is not None and basis is not None
            else None
        )
        advice = holding_advice(
            pipe,
            position,
            bars,
            states,
            quote=quote,
            quality=quality,
            expected=expected,
            completed=completed,
            today=today,
            fundamental_report=assess_fundamentals(
                fundamentals.get(symbol),
                quote=quote,
                snapshot_date=snapshot_dates.get(symbol),
                today=today,
            ),
        )
        net_exit_pnl = None
        if quote is not None and basis is not None:
            holding_days = (
                (today - date.fromisoformat(position["bought_on"])).days
                if position["bought_on"]
                else None
            )
            net_exit_pnl = float(
                engine.compute(
                    OrderSide.SELL,
                    quote,
                    position["quantity"],
                    buy_cost_basis=basis,
                    holding_days=holding_days,
                ).net_amount
                - basis
            )
        owned_advice.append(
            {
                **position,
                "cost_basis": float(basis) if basis is not None else None,
                "average_cost": float(basis / position["quantity"]) if basis is not None else None,
                "reference_price": quote,
                "quote_date": quote_date.isoformat() if quote_date else None,
                "unrealized_pnl": pnl,
                "net_exit_pnl": net_exit_pnl,
                **advice,
                "chart": chart,
            }
        )
    return dict(
        state_key=state_key,
        requested_date=today.isoformat(),
        market_date=observed.isoformat() if observed else None,
        generated_at=datetime.now(UTC).isoformat(),
        session="trading_day" if is_trading_day(today) else "closed",
        session_phase=phase,
        earliest_entry_date=trade_date.isoformat(),
        stale=stale,
        available_cash=float(cash),
        planned_outlay=float(allocated),
        cash_reserved=float(cash - allocated),
        buys=ideas,
        holdings=owned_advice,
        fundamental_checks_needed=sorted(fundamental_checks, key=lambda s: -fundamental_checks[s])[
            :10
        ],
        investments={
            "candidates": sorted(investments, key=lambda p: -p["score"])[:4],
            "checked_fundamentals": len(fundamentals),
            "fundamentals_missing": len(set(names) - set(fundamentals)),
            "criteria": "Positive EPS/book value; quote-based P/E≤30 and price/book≤3; snapshot≤90 days old; ≥200 sessions over ≥1 year; average volume≥10,000; historical drawdown≤25%, volatility≤30% and positive fee-adjusted price CAGR.",
            "note": "A research watchlist, not a reserved purchase budget. Stocks can lose capital. Historical price returns are not promised returns or bank deposit rates.",
        },
        recent_exits=[
            {"symbol": s, "reconsider_after": add_trading_days(d, 1).isoformat()}
            for s, d in cooldowns.items()
            if s not in owned and expected <= d
        ],
        coverage={
            "symbols": len(names),
            "analysable": sum(1 for detail in details.values() if detail[0] is not None),
        },
        confidence_note="Confidence measures the strength of available evidence, not a guaranteed win probability.",
    )


def save_decisions(pipe, board: dict) -> dict:
    storage = pipe.storage
    board = {**board, "id": uuid.uuid4().hex}
    with storage._tx() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if board.get("state_key") != decision_state(
            pipe, date.fromisoformat(board["requested_date"])
        ):
            raise DecisionsChanged("Market or holdings changed during analysis. Rebuilding advice.")
        record_advice_history(conn, board)
        board["state_key"] = decision_state(pipe, date.fromisoformat(board["requested_date"]))
        if "refresh" not in board:
            prior = conn.execute(
                "SELECT payload FROM decision_runs ORDER BY generated_at DESC LIMIT 1"
            ).fetchone()
            previous = json.loads(prior[0]) if prior else {}
            if (
                previous.get("requested_date") == board["requested_date"]
                and previous.get("market_date") == board["market_date"]
                and previous.get("refresh")
            ):
                board["refresh"] = previous["refresh"]
        # Publication order determines the latest board, even when an earlier
        # analysis finishes after another request or the refresh worker.
        board["generated_at"] = datetime.now(UTC).isoformat()
        from nepse_trader.advisor.track_record import record_recommendations
        record_recommendations(conn, board)
        conn.execute(
            "INSERT INTO decision_runs(id,generated_at,payload) VALUES(?,?,?)",
            (board["id"], board["generated_at"], json.dumps(board)),
        )
        conn.execute(
            "DELETE FROM decision_runs WHERE id NOT IN (SELECT id FROM decision_runs ORDER BY generated_at DESC LIMIT 30)"
        )
    return board


class DecisionsChanged(ValueError):
    pass


def publish_decisions(pipe, board: dict | None = None) -> dict:
    refresh = board.get("refresh") if board else None
    for _ in range(3):
        try:
            board = board or build_decisions(pipe)
            if refresh is not None:
                board["refresh"] = refresh
            return save_decisions(pipe, board)
        except DecisionsChanged:
            board = None
    raise DecisionsChanged("Market or holdings are changing. Refresh advice again.")
