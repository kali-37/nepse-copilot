"""Use dated public earnings/valuation data without inventing financial strength."""

from __future__ import annotations

import math
from datetime import date

LIMITATIONS = [
    "EPS/book value do not verify cash flow, debt, ROE, bank bad loans or capital adequacy.",
    "Snapshot date is when data was obtained, not a verified financial reporting period.",
    "Declared dividend percentage is not a confirmed market cash yield or future payout.",
    "Fundamentals currently come from one public provider; official filings are not reconciled.",
]


def assess_fundamentals(
    snapshot, *, quote: float | None, snapshot_date: date | None, today: date
) -> dict:
    base = dict(
        source="MeroLagani public snapshot",
        snapshot_date=snapshot_date.isoformat() if snapshot_date else None,
        eps=None,
        book_value=None,
        current_pe=None,
        current_pbv=None,
        reasons=[],
        limitations=LIMITATIONS,
    )
    if snapshot is None or snapshot_date is None or snapshot_date > today:
        return {
            **base,
            "rating": "missing",
            "multiplier": 0,
            "needs_refresh": True,
            "reasons": ["No dated earnings/valuation snapshot is available."],
        }
    if (today - snapshot_date).days > 90:
        return {
            **base,
            "rating": "stale",
            "multiplier": 0,
            "needs_refresh": True,
            "reasons": [f"Financial snapshot {snapshot_date} is more than 90 days old."],
        }
    if any(v is None or not math.isfinite(v) for v in (snapshot.eps, snapshot.book_value)):
        return {
            **base,
            "rating": "incomplete",
            "multiplier": 0,
            "needs_refresh": True,
            "reasons": ["EPS or book value is missing; financial support is unconfirmed."],
        }
    base.update(eps=snapshot.eps, book_value=snapshot.book_value)
    if snapshot.eps <= 0 or snapshot.book_value <= 0:
        return {
            **base,
            "rating": "unsupported",
            "multiplier": 0,
            "needs_refresh": False,
            "reasons": [
                f"Reported EPS {snapshot.eps:.2f} and book value {snapshot.book_value:.2f} do not pass positive-earnings/equity checks."
            ],
        }
    if quote is None or not math.isfinite(quote) or quote <= 0:
        return {
            **base,
            "rating": "incomplete",
            "multiplier": 0,
            "needs_refresh": True,
            "reasons": ["A usable current quote is needed to assess valuation."],
        }
    pe, pbv = quote / snapshot.eps, quote / snapshot.book_value
    rating = (
        "supported"
        if pe <= 30 and pbv <= 3
        else "caution"
        if pe <= 45 and pbv <= 5
        else "expensive"
    )
    multiplier = {"supported": 1.0, "caution": 0.85, "expensive": 0.65}[rating]
    reasons = [
        f"Reported EPS is positive: NPR {snapshot.eps:.2f} (snapshot {snapshot_date}).",
        f"Current P/E {pe:.1f} and price/book {pbv:.2f}: "
        + (
            "within valuation screen limits."
            if rating == "supported"
            else "valuation raises caution; technical strength alone is insufficient."
        ),
    ]
    return {
        **base,
        "current_pe": round(pe, 2),
        "current_pbv": round(pbv, 2),
        "rating": rating,
        "multiplier": multiplier,
        "needs_refresh": False,
        "reasons": reasons,
    }
