"""A dated entry plan is copied into the trade ledger, not inferred later."""

from __future__ import annotations

import json
import uuid
from datetime import date


def entry_plan(
    storage,
    *,
    symbol: str,
    quantity: int,
    price: float | None,
    bought_on: date | None,
    stop: float | None,
    target: float | None,
    horizon_days: int,
    origin_decision_id: str | None = None,
    origin_horizon: str | None = None,
) -> dict:
    origin = None
    unavailable = "No dated recommendation was linked to this purchase."
    if origin_decision_id and origin_horizon:
        row = storage._conn.execute(
            "SELECT payload FROM decision_runs WHERE id=?", (origin_decision_id,)
        ).fetchone()
        board = json.loads(row[0]) if row else None
        if board and bought_on and board["requested_date"] <= bought_on.isoformat():
            candidates = (
                board.get("investments", {}).get("candidates", [])
                if origin_horizon == "investment"
                else board.get("buys", {}).get(origin_horizon, [])
            )
            candidate = next(
                (p for p in candidates if p["symbol"] == symbol),
                None,
            )
            if candidate:
                origin = {
                    **candidate,
                    "decision_id": origin_decision_id,
                    "requested_date": board["requested_date"],
                    "market_date": board["market_date"],
                }
        elif board:
            unavailable = "That recommendation was generated after the purchase; the original buy reason is unknown."
        else:
            unavailable = (
                "The linked recommendation is unavailable; the original buy reason is unknown."
            )
    reasons = list(origin["rationale"]) if origin else [unavailable]
    if origin and origin["horizon_days"] != horizon_days:
        reasons.append(
            f"The linked recommendation used {origin['horizon_days']} sessions; you selected a {horizon_days}-session holding plan. Its entry confidence refers to the original recommendation horizon."
        )
    return dict(
        id=uuid.uuid4().hex,
        opened_on=bought_on.isoformat() if bought_on else None,
        horizon_days=horizon_days,
        purchase_price=price,
        quantity=quantity,
        stop=stop,
        target=target,
        rationale=reasons,
        confidence_horizon_days=origin["horizon_days"] if origin else None,
        confidence=origin.get("confidence") if origin else None,
        origin=origin,
    )


def decode_plan(position: dict) -> dict | None:
    value = position.get("entry_thesis")
    return json.loads(value) if isinstance(value, str) else value
