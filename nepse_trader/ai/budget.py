"""Token budgeting: hard ceilings with a DB-backed ledger.

Three caps, all from settings:

* ``llm_max_calls_per_day`` — a runaway loop can't drain an account overnight.
* ``llm_max_tokens_per_day`` — the one that matters on a metered key.
* ``llm_max_deep_passes_per_week`` — the expensive weekly pass (full evidence,
  synthesis model) is what "I might not have enough tokens" was about. Daily runs
  reuse its cached thesis and only pay for the delta.

Exhaustion is **not** an error. :meth:`TokenBudget.check` returns a status with a
human-readable reason, and the caller degrades to Normal mode with that reason as
a banner. Nothing here ever raises during a run.

Cache hits are recorded in the ledger (so the accounting shows them) but excluded
from every cap, because they cost nothing.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime

from nepse_trader.ai.providers import LLMResponse
from nepse_trader.config import Settings, get_settings

log = logging.getLogger("nepse_trader.ai.budget")


def iso_week(day: date) -> str:
    """``"2026-W35"`` — the key the weekly deep-pass cap counts against."""
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


@dataclass
class BudgetStatus:
    """Whether a call may proceed, and if not, why not in plain words."""

    allowed: bool
    reason: str = ""

    def __bool__(self) -> bool:
        return self.allowed


@dataclass
class BudgetSummary:
    """Today's spend against the caps."""

    day: str
    week: str
    calls: int
    tokens: int
    cached_calls: int
    failed_calls: int
    deep_passes: int
    max_calls: int
    max_tokens: int
    max_deep_passes: int

    @property
    def calls_left(self) -> int:
        return max(0, self.max_calls - self.calls)

    @property
    def tokens_left(self) -> int:
        return max(0, self.max_tokens - self.tokens)

    @property
    def deep_passes_left(self) -> int:
        return max(0, self.max_deep_passes - self.deep_passes)

    @property
    def exhausted(self) -> bool:
        return self.calls_left == 0 or self.tokens_left == 0

    def as_dict(self) -> dict:
        return {
            "day": self.day,
            "week": self.week,
            "calls": self.calls,
            "calls_left": self.calls_left,
            "max_calls": self.max_calls,
            "tokens": self.tokens,
            "tokens_left": self.tokens_left,
            "max_tokens": self.max_tokens,
            "cached_calls": self.cached_calls,
            "failed_calls": self.failed_calls,
            "deep_passes": self.deep_passes,
            "deep_passes_left": self.deep_passes_left,
            "max_deep_passes": self.max_deep_passes,
            "exhausted": self.exhausted,
        }


class TokenBudget:
    """Spend accounting over the ``ai_budget_ledger`` table."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        settings: Settings | None = None,
        *,
        today: date | None = None,
    ) -> None:
        self._conn = conn
        self._conn.row_factory = sqlite3.Row
        self.settings = settings or get_settings()
        # Pinned in tests so a run at midnight can't straddle two ledger days.
        self._today = today

    @property
    def today(self) -> date:
        return self._today or datetime.now(UTC).date()

    # ------------------------------------------------------------------ reads
    def spent_today(self) -> tuple[int, int]:
        """``(billable_calls, billable_tokens)`` for today. Cache hits excluded."""
        row = self._conn.execute(
            """SELECT COUNT(*) AS calls,
                      COALESCE(SUM(prompt_tokens + completion_tokens), 0) AS tokens
               FROM ai_budget_ledger
               WHERE day = ? AND cached = 0""",
            (self.today.isoformat(),),
        ).fetchone()
        return (int(row["calls"]), int(row["tokens"]))

    def deep_passes_this_week(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM ai_budget_ledger "
            "WHERE iso_week = ? AND deep = 1 AND cached = 0 AND ok = 1",
            (iso_week(self.today),),
        ).fetchone()
        return int(row["n"])

    def summary(self) -> BudgetSummary:
        calls, tokens = self.spent_today()
        extra = self._conn.execute(
            """SELECT COALESCE(SUM(cached), 0) AS cached,
                      COALESCE(SUM(CASE WHEN ok = 0 THEN 1 ELSE 0 END), 0) AS failed
               FROM ai_budget_ledger WHERE day = ?""",
            (self.today.isoformat(),),
        ).fetchone()
        return BudgetSummary(
            day=self.today.isoformat(),
            week=iso_week(self.today),
            calls=calls,
            tokens=tokens,
            cached_calls=int(extra["cached"]),
            failed_calls=int(extra["failed"]),
            deep_passes=self.deep_passes_this_week(),
            max_calls=self.settings.llm_max_calls_per_day,
            max_tokens=self.settings.llm_max_tokens_per_day,
            max_deep_passes=self.settings.llm_max_deep_passes_per_week,
        )

    # ------------------------------------------------------------------ gates
    def check(self, *, deep: bool = False, estimated_tokens: int = 0) -> BudgetStatus:
        """Whether one more call fits inside the caps.

        ``estimated_tokens`` lets a large call be refused *before* it is made,
        instead of only discovering the overrun once it's been paid for.
        """
        calls, tokens = self.spent_today()
        if calls >= self.settings.llm_max_calls_per_day:
            return BudgetStatus(
                False,
                f"daily call cap reached ({calls}/{self.settings.llm_max_calls_per_day})",
            )
        projected = tokens + max(0, estimated_tokens)
        if projected > self.settings.llm_max_tokens_per_day:
            return BudgetStatus(
                False,
                f"daily token cap reached ({tokens:,} spent of "
                f"{self.settings.llm_max_tokens_per_day:,}"
                + (f", this call needs ~{estimated_tokens:,}" if estimated_tokens else "")
                + ")",
            )
        if deep:
            passes = self.deep_passes_this_week()
            if passes >= self.settings.llm_max_deep_passes_per_week:
                return BudgetStatus(
                    False,
                    f"weekly deep-pass cap reached "
                    f"({passes}/{self.settings.llm_max_deep_passes_per_week} "
                    f"in {iso_week(self.today)})",
                )
        return BudgetStatus(True)

    # ------------------------------------------------------------------ writes
    def record(self, response: LLMResponse, *, task: str, deep: bool = False) -> None:
        """Append one call to the ledger, successful or not.

        Failures are recorded with zero tokens: a provider that errored produced
        nothing to bill, but the attempt still counts as a call so a provider
        stuck in a failure loop cannot be retried without limit.
        """
        billable = response.ok and not response.cached
        self._conn.execute(
            """INSERT INTO ai_budget_ledger
               (created_at, day, iso_week, task, provider, model,
                prompt_tokens, completion_tokens, cached, deep, ok, error)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                datetime.now(UTC).isoformat(),
                self.today.isoformat(),
                iso_week(self.today),
                task,
                response.provider or "(none)",
                response.model or "(none)",
                response.prompt_tokens if billable else 0,
                response.completion_tokens if billable else 0,
                int(response.cached),
                int(deep),
                int(response.ok),
                response.error or None,
            ),
        )
        self._conn.commit()

    def history(self, *, limit: int = 20) -> list[dict]:
        """Most recent ledger rows, newest first — the audit trail."""
        rows = self._conn.execute(
            "SELECT * FROM ai_budget_ledger ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
