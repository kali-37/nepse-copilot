"""The advisor: a daily, actionable prescription instead of a table of facts.

The existing daily report answers "what happened". This package answers "what
should I do" — for each symbol, an entry zone, a stop, targets, a lot-rounded
quantity, a horizon in trading days, and the earliest date the shares can
legally be sold again.

Two modules:

* :mod:`nepse_trader.advisor.plan` — the deterministic engine. Every number in
  a plan card is computed here from price history and the existing risk and
  cost primitives. It needs no network and no LLM.
* :mod:`nepse_trader.advisor.rashifal` — composes the cards into the daily
  report: market regime, sector of the day, buy cards, sell queue, do-not-touch
  list, and (in AI mode only) narrative commentary.

The invariant that separates the two: **AI adds commentary, never numbers.**
The engine owns every price, stop, target, size and date. When the LLM layer is
offline, out of budget, or simply wrong, the advisor drops to Normal mode with a
visible banner and the numbers are unchanged.
"""

from nepse_trader.advisor.plan import (
    PlanCard,
    Skipped,
    build_plan_card,
    build_plan_cards,
)
from nepse_trader.advisor.rashifal import (
    Rashifal,
    build_rashifal,
    latest_run,
    run_history,
    save_rashifal,
)

__all__ = [
    "PlanCard",
    "Skipped",
    "build_plan_card",
    "build_plan_cards",
    "Rashifal",
    "build_rashifal",
    "save_rashifal",
    "latest_run",
    "run_history",
]
