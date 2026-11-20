"""Offline sector breadth and matched-contract broker flow."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from decimal import Decimal

from nepse_trader.models import FloorsheetEntry, FundamentalData, ReconciledPrice


def broker_flows(entries: Sequence[FloorsheetEntry]) -> list[dict]:
    totals: dict[tuple[str, str], dict] = {}
    seen = set()
    for entry in entries:
        identity = (entry.symbol, entry.business_date, entry.contract_id or
                    (entry.buyer_broker, entry.seller_broker, entry.quantity, entry.rate))
        if identity in seen:
            continue
        seen.add(identity)
        amount = Decimal(str(entry.amount)) if entry.amount is not None else Decimal(str(entry.rate)) * entry.quantity
        for broker, side in [(entry.buyer_broker, "buy"), (entry.seller_broker, "sell")]:
            if not broker:
                continue
            key = (entry.symbol, broker)
            row = totals.setdefault(key, {"symbol": entry.symbol, "broker": broker,
                "buy_quantity": 0, "sell_quantity": 0, "buy_amount": Decimal(0), "sell_amount": Decimal(0)})
            row[f"{side}_quantity"] += entry.quantity
            row[f"{side}_amount"] += amount
    rows = []
    for row in totals.values():
        row["net_quantity"] = row["buy_quantity"] - row["sell_quantity"]
        row["net_amount"] = row["buy_amount"] - row["sell_amount"]
        rows.append({key: float(value) if isinstance(value, Decimal) else value for key, value in row.items()})
    return sorted(rows, key=lambda row: (-row["net_amount"], row["symbol"], row["broker"]))


def sector_breadth(prices: Sequence[ReconciledPrice], snapshots: Mapping[str, FundamentalData]) -> list[dict]:
    groups = defaultdict(list)
    for price in prices:
        data = snapshots.get(price.symbol)
        groups[data.sector if data and data.sector else "Unclassified"].append(price)
    rows = []
    for sector, group in groups.items():
        changes = [(p.close - p.previous_close) / p.previous_close * 100
                   for p in group if p.close is not None and p.previous_close and p.previous_close > 0]
        rows.append({"sector": sector, "symbols": len(group), "advancers": sum(c > 0 for c in changes),
                     "decliners": sum(c < 0 for c in changes), "unchanged": sum(c == 0 for c in changes),
                     "missing_change": len(group) - len(changes),
                     "mean_change_pct": sum(changes) / len(changes) if changes else None,
                     "turnover": sum(p.turnover or 0 for p in group)})
    return sorted(rows, key=lambda row: (row["mean_change_pct"] is None, -(row["mean_change_pct"] or 0), row["sector"]))
