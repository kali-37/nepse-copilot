"""Manual holding records and entry-anchored exit plans; never broker orders."""

from __future__ import annotations

import json
import math
import re
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from nepse_trader.advisor.decision_signals import chart_states
from nepse_trader.advisor.entry_plan import decode_plan, entry_plan
from nepse_trader.analysis.costs import CostEngine, _to_money
from nepse_trader.meroshare import stored_holdings
from nepse_trader.models import OrderSide
from nepse_trader.pipeline import DailyPipeline
from nepse_trader.storage.app_settings import read_json


def available_cash(storage) -> Decimal:
    value, _ = read_json(storage._conn, "available_cash")
    try:
        money = Decimal(str(value if value is not None else 100000))
        return _to_money(money) if money.is_finite() and money >= 0 else Decimal(100000)
    except Exception:
        return Decimal(100000)


def set_cash(storage, cash: Decimal) -> None:
    if not cash.is_finite() or cash < 0:
        raise ValueError("Available cash must be finite and non-negative.")
    with storage._tx() as conn:
        conn.execute(
            """INSERT INTO app_settings(key,value,updated_at) VALUES(?,?,?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at""",
            ("available_cash", json.dumps(str(_to_money(cash))), datetime.now(UTC).isoformat()),
        )


def owned_positions(pipe: DailyPipeline) -> list[dict]:
    positions = {}
    # Prefer a real read-only mirror over the simulated book for the same name.
    for position in pipe.replay_portfolio(10**12).holdings():
        positions[position.symbol] = dict(
            symbol=position.symbol,
            quantity=position.quantity,
            cost_basis=str(position.cost_basis),
            bought_on=None,
            stop=None,
            target=None,
            horizon_days=22,
            entry_price=None,
            plan_reviewed_on=None,
            entry_thesis=None,
            plan_revision=0,
            source="paper",
        )
    for holding in stored_holdings(pipe.storage._conn):
        if holding.current_balance > 0:
            positions[holding.symbol] = dict(
                symbol=holding.symbol,
                quantity=holding.current_balance,
                cost_basis=str(holding.cost_basis) if holding.cost_basis is not None else None,
                bought_on=None,
                stop=None,
                target=None,
                horizon_days=22,
                entry_price=None,
                plan_reviewed_on=None,
                entry_thesis=None,
                plan_revision=0,
                source="meroshare",
            )
    for row in pipe.storage._conn.execute("SELECT * FROM tracked_positions"):
        positions[row["symbol"]] = {**dict(row), "source": "tracked"}
    return [p for p in positions.values() if p["quantity"] > 0]


def _record_trade(
    pipe: DailyPipeline,
    *,
    symbol: str,
    side: str,
    quantity: int,
    price: Decimal,
    bought_on: date,
    stop: float | None = None,
    target: float | None = None,
    horizon_days: int = 22,
    record_id: str | None = None,
    origin_decision_id: str | None = None,
    origin_horizon: str | None = None,
) -> dict:
    symbol = symbol.strip().upper()
    if (
        not re.fullmatch(r"[A-Z0-9][A-Z0-9.-]{0,19}(?:/[0-9]{1,4})?", symbol)
        or not 1 <= horizon_days <= 252
        or quantity <= 0
        or not price.is_finite()
        or price <= 0
        or bought_on > date.today()
    ):
        raise ValueError(
            "Provide a symbol, positive quantity/price, and a trade date no later than today."
        )
    if side not in ("buy", "sell"):
        raise ValueError("Trade side must be buy or sell.")
    if any(v is not None and (not math.isfinite(v) or v <= 0) for v in (stop, target)):
        raise ValueError("Stop and target must be finite positive prices.")
    if record_id:
        if not re.fullmatch(r"[a-fA-F0-9-]{32,36}", record_id):
            raise ValueError("Invalid trade record ID.")
        prior = pipe.storage._conn.execute(
            "SELECT * FROM position_records WHERE id=?", (record_id,)
        ).fetchone()
        if prior:
            if (
                prior["symbol"],
                prior["side"],
                prior["quantity"],
                Decimal(prior["price"]),
                prior["business_date"],
            ) != (symbol, side, quantity, price, bought_on.isoformat()):
                raise ValueError("This record ID was already used for a different trade.")
            position = next((p for p in owned_positions(pipe) if p["symbol"] == symbol), None)
            return {
                "symbol": symbol,
                "quantity": position["quantity"] if position else 0,
                "recorded": True,
                "order_submitted": False,
                "already_recorded": True,
                "available_cash": float(available_cash(pipe.storage)),
            }
    latest = pipe.storage._conn.execute(
        "SELECT MAX(business_date) FROM position_records WHERE symbol=?", (symbol,)
    ).fetchone()[0]
    if latest and bought_on.isoformat() < latest:
        raise ValueError("Record trades in date order for each symbol.")
    current = next((p for p in owned_positions(pipe) if p["symbol"] == symbol), None)
    if current and current["source"] == "tracked" and current["bought_on"]:
        anchor = max(current["bought_on"], current.get("plan_reviewed_on") or "")
        if any(
            anchor < ca.ex_date.isoformat() <= bought_on.isoformat()
            for ca in pipe.storage.corporate_actions(symbol)
        ):
            raise ValueError(
                "A corporate action changed this holding. Confirm current shares with Set exit plan before recording another trade."
            )
    cash = available_cash(pipe.storage)
    engine = CostEngine()
    old_quantity = current["quantity"] if current else 0
    original = decode_plan(current) if current else None
    revision = current.get("plan_revision", 0) if current else 0
    receipt_plan = None
    old_basis = (
        Decimal(str(current["cost_basis"]))
        if current and current["cost_basis"] is not None
        else None
        if current
        else Decimal(0)
    )
    if side == "sell":
        if current and current["bought_on"] and bought_on.isoformat() < current["bought_on"]:
            raise ValueError("A sale cannot precede the recorded purchase date.")
        if quantity > old_quantity:
            raise ValueError("You cannot record selling more shares than you own.")
        consumed = _to_money(old_basis * quantity / old_quantity) if old_basis is not None else None
        holding_days = (
            (bought_on - date.fromisoformat(current["bought_on"])).days
            if current["bought_on"]
            else None
        )
        fees = engine.compute(
            OrderSide.SELL, price, quantity, buy_cost_basis=consumed, holding_days=holding_days
        )
        if consumed is None:
            # Unknown mirrored basis: reserve the maximum modeled short-term CGT.
            fees.net_amount -= _to_money(
                fees.net_amount * Decimal(str(engine.model.cgt_short_percent)) / 100
            )
        new_quantity, basis = (
            old_quantity - quantity,
            old_basis - consumed if old_basis is not None else None,
        )
        cash += fees.net_amount
        stop, target = current["stop"], current["target"]
        entry_price = current["entry_price"]
        entry_date = current["bought_on"]
        horizon_days = current["horizon_days"]
    else:
        if old_quantity:
            horizon_days = current["horizon_days"]
        fees = engine.compute(OrderSide.BUY, price, quantity)
        new_quantity, basis = (
            old_quantity + quantity,
            old_basis + fees.net_amount if old_basis is not None else None,
        )
        cash = max(Decimal(0), cash - fees.net_amount)
        previous_entry = current["entry_price"] if current else None
        previous_entry = previous_entry or float(price)
        average = (previous_entry * old_quantity + float(price) * quantity) / new_quantity
        entry_price = average
        bars = [
            bar
            for bar in pipe.reconciled_bars(symbol, as_of=bought_on)
            if bar.business_date <= bought_on
        ]
        state = chart_states(bars)[-1] if len(bars) >= 50 else None
        distance = state.atr * (1 if horizon_days <= 3 else 2) if state else average * 0.05
        stop = (
            stop
            if stop is not None
            else current["stop"]
            if old_quantity and current["stop"] is not None
            else round(max(average * 0.9, average - distance), 2)
        )
        target_given = target is not None
        target_existing = old_quantity and target is None and current["target"] is not None
        target = (
            target
            if target_given
            else current["target"]
            if target_existing
            else round(average + distance * 2, 2)
        )
        if basis is not None and not target_given and not target_existing:
            # A take-profit level must cover fees even for a tiny odd-lot.
            while (
                engine.compute(
                    OrderSide.SELL, target, new_quantity, buy_cost_basis=basis
                ).net_amount
                <= basis
            ):
                target = round(target * 1.01 + 0.01, 2)
        if (
            basis is not None
            and target_given
            and engine.compute(
                OrderSide.SELL, target, new_quantity, buy_cost_basis=basis
            ).net_amount
            <= basis
        ):
            raise ValueError(
                "The take-profit target must cover the estimated sale fees at this quantity."
            )
        if not 0 < stop < target or (not old_quantity and not stop < average < target):
            raise ValueError(
                "The exit plan must have a positive stop below your cost and a target above it."
            )
        entry_date = bought_on.isoformat()
        receipt_plan = entry_plan(
            pipe.storage,
            symbol=symbol,
            quantity=quantity,
            price=float(price),
            bought_on=bought_on,
            stop=stop,
            target=target,
            horizon_days=horizon_days,
            origin_decision_id=origin_decision_id,
            origin_horizon=origin_horizon,
        )
        if original is None:
            original = (
                receipt_plan
                if not old_quantity
                else entry_plan(
                    pipe.storage,
                    symbol=symbol,
                    quantity=new_quantity,
                    price=previous_entry,
                    bought_on=date.fromisoformat(current["bought_on"])
                    if current["bought_on"]
                    else None,
                    stop=stop,
                    target=target,
                    horizon_days=horizon_days,
                )
            )
        if old_quantity and (stop, target) != (current["stop"], current["target"]):
            revision += 1
    recorded = datetime.now(UTC).isoformat()
    conn = pipe.storage._conn
    conn.execute(
        """INSERT INTO tracked_positions(symbol,quantity,cost_basis,bought_on,stop,target,horizon_days,updated_at,entry_price,entry_thesis,plan_revision)
        VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(symbol) DO UPDATE SET quantity=excluded.quantity,
        cost_basis=excluded.cost_basis,bought_on=excluded.bought_on,stop=excluded.stop,
        target=excluded.target,horizon_days=excluded.horizon_days,updated_at=excluded.updated_at,entry_price=excluded.entry_price,entry_thesis=excluded.entry_thesis,plan_revision=excluded.plan_revision""",
        (
            symbol,
            new_quantity,
            str(_to_money(basis)) if basis is not None else None,
            entry_date,
            stop,
            target,
            horizon_days,
            recorded,
            entry_price,
            json.dumps(original) if original else None,
            revision,
        ),
    )
    conn.execute(
        "INSERT INTO position_records(id,symbol,side,quantity,price,business_date,recorded_at,entry_thesis) VALUES(?,?,?,?,?,?,?,?)",
        (
            record_id or uuid.uuid4().hex,
            symbol,
            side,
            quantity,
            str(price),
            bought_on.isoformat(),
            recorded,
            json.dumps(receipt_plan) if receipt_plan else None,
        ),
    )
    conn.execute(
        """INSERT INTO app_settings(key,value,updated_at) VALUES('available_cash',?,?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at""",
        (json.dumps(str(_to_money(cash))), recorded),
    )
    return {
        "symbol": symbol,
        "quantity": new_quantity,
        "recorded": True,
        "order_submitted": False,
        "available_cash": float(cash),
        "tax_basis_known": old_basis is not None,
    }


def record_trade(pipe: DailyPipeline, **kwargs) -> dict:
    # Lock before reading quantity/cash: simultaneous records cannot oversell
    # or lose an update. The transaction rolls back validation failures too.
    with pipe.storage._tx() as conn:
        conn.execute("BEGIN IMMEDIATE")
        return _record_trade(pipe, **kwargs)


def set_position_plan(
    pipe: DailyPipeline,
    *,
    symbol: str,
    quantity: int,
    stop: float,
    target: float,
    average_cost: Decimal | None = None,
    bought_on: date | None = None,
    horizon_days: int | None = None,
) -> dict:
    """Confirm an existing holding and exit levels without recording a new buy."""
    symbol = symbol.strip().upper()
    if (
        quantity <= 0
        or not all(math.isfinite(v) and v > 0 for v in (stop, target))
        or stop >= target
    ):
        raise ValueError("Provide a positive share count and stop below target.")
    if average_cost is not None and (not average_cost.is_finite() or average_cost <= 0):
        raise ValueError("Average cost must be finite and positive.")
    if horizon_days is not None and not 3 <= horizon_days <= 252:
        raise ValueError("Holding period must be 3–252 trading sessions.")
    if bought_on and bought_on > date.today():
        raise ValueError("Purchase date cannot be in the future.")
    with pipe.storage._tx() as conn:
        conn.execute("BEGIN IMMEDIATE")
        current = next((p for p in owned_positions(pipe) if p["symbol"] == symbol), None)
        if current is None:
            raise ValueError("Record a purchase before setting an exit plan.")
        basis = (
            _to_money(average_cost * quantity)
            if average_cost is not None
            else (Decimal(current["cost_basis"]) if current["cost_basis"] is not None else None)
        )
        if quantity != current["quantity"] and average_cost is None:
            basis = None  # Units changed; the old per-position basis is not assumed.
        recorded = datetime.now(UTC).isoformat()
        original = decode_plan(current) or entry_plan(
            pipe.storage,
            symbol=symbol,
            quantity=quantity,
            price=float(average_cost) if average_cost else None,
            bought_on=bought_on
            or (date.fromisoformat(current["bought_on"]) if current["bought_on"] else None),
            stop=stop,
            target=target,
            horizon_days=horizon_days or current["horizon_days"],
        )
        entry = current["entry_price"]  # WACC includes fees; it is not a market entry price.
        conn.execute(
            """INSERT INTO tracked_positions(symbol,quantity,cost_basis,bought_on,stop,target,
            horizon_days,updated_at,entry_price,plan_reviewed_on,entry_thesis,plan_revision) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(symbol) DO UPDATE SET quantity=excluded.quantity,cost_basis=excluded.cost_basis,
            bought_on=excluded.bought_on,stop=excluded.stop,target=excluded.target,
            updated_at=excluded.updated_at,entry_price=excluded.entry_price,plan_reviewed_on=excluded.plan_reviewed_on,
            horizon_days=excluded.horizon_days,entry_thesis=excluded.entry_thesis,plan_revision=excluded.plan_revision""",
            (
                symbol,
                quantity,
                str(basis) if basis is not None else None,
                bought_on.isoformat() if bought_on else current["bought_on"],
                stop,
                target,
                horizon_days or current["horizon_days"],
                recorded,
                entry,
                date.today().isoformat(),
                json.dumps(original),
                current.get("plan_revision", 0) + 1,
            ),
        )
    return {"symbol": symbol, "updated": True, "order_submitted": False}
