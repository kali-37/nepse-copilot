"""Tests for the token budget.

The behaviour that matters is the **hard stop**: once a cap is reached,
:meth:`TokenBudget.check` must refuse, and it must say why in words that can go
straight into a report banner. A cap that could be exceeded by one more call is
not a cap.

The second property is that **cache hits are free**. They appear in the ledger so
the accounting is honest, and count against nothing.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from nepse_trader.ai.budget import TokenBudget, iso_week
from nepse_trader.ai.providers import LLMResponse
from nepse_trader.config import Settings
from nepse_trader.storage import Storage

TODAY = date(2026, 8, 20)  # a Thursday, ISO week 34


@pytest.fixture
def conn(tmp_path: Path):
    storage = Storage(tmp_path / "budget.db")
    yield storage._conn
    storage.close()


def _settings(**kw) -> Settings:
    base = {"_env_file": None}
    base.update(kw)
    return Settings(**base)


def _budget(conn, *, today: date = TODAY, **kw) -> TokenBudget:
    return TokenBudget(conn, _settings(**kw), today=today)


def _ok(tokens: int = 100) -> LLMResponse:
    return LLMResponse(
        text="answer", provider="openrouter", model="a:free",
        prompt_tokens=tokens, completion_tokens=0,
    )


class TestIsoWeek:
    def test_formats_year_and_week(self):
        assert iso_week(date(2026, 8, 20)) == "2026-W34"

    def test_zero_pads_early_weeks(self):
        assert iso_week(date(2026, 1, 8)) == "2026-W02"

    def test_january_can_belong_to_the_previous_iso_year(self):
        """ISO weeks don't respect calendar years; the label must not either."""
        assert iso_week(date(2027, 1, 1)) == "2026-W53"


class TestEmptyLedger:
    def test_nothing_spent(self, conn):
        assert _budget(conn).spent_today() == (0, 0)

    def test_a_call_is_allowed(self, conn):
        assert _budget(conn).check().allowed

    def test_summary_reports_the_caps(self, conn):
        summary = _budget(conn, llm_max_calls_per_day=7).summary()
        assert summary.max_calls == 7
        assert summary.calls_left == 7
        assert summary.exhausted is False


class TestRecording:
    def test_a_successful_call_counts(self, conn):
        budget = _budget(conn)
        budget.record(_ok(500), task="note")
        assert budget.spent_today() == (1, 500)

    def test_a_failed_call_counts_as_a_call_but_no_tokens(self, conn):
        """A provider stuck in a failure loop must still burn its call allowance."""
        budget = _budget(conn)
        budget.record(LLMResponse(error="503", provider="openrouter"), task="note")
        assert budget.spent_today() == (1, 0)

    def test_a_cache_hit_costs_nothing(self, conn):
        budget = _budget(conn)
        budget.record(LLMResponse(text="x", provider="claude_cli", cached=True, prompt_tokens=900), task="note")
        assert budget.spent_today() == (0, 0)
        assert budget.summary().cached_calls == 1

    def test_yesterdays_spend_does_not_count_today(self, conn):
        yesterday = _budget(conn, today=date(2026, 8, 19))
        yesterday.record(_ok(9_999), task="note")
        assert _budget(conn).spent_today() == (0, 0)

    def test_errors_are_kept_for_the_audit_trail(self, conn):
        budget = _budget(conn)
        budget.record(LLMResponse(error="rate limited"), task="note")
        assert budget.history()[0]["error"] == "rate limited"

    def test_history_is_newest_first(self, conn):
        budget = _budget(conn)
        budget.record(_ok(), task="first")
        budget.record(_ok(), task="second")
        assert [r["task"] for r in budget.history()] == ["second", "first"]


class TestCallCap:
    def test_refuses_at_the_cap(self, conn):
        budget = _budget(conn, llm_max_calls_per_day=2)
        for _ in range(2):
            budget.record(_ok(), task="note")
        status = budget.check()
        assert not status.allowed
        assert "call cap" in status.reason

    def test_allows_right_up_to_the_cap(self, conn):
        budget = _budget(conn, llm_max_calls_per_day=2)
        budget.record(_ok(), task="note")
        assert budget.check().allowed

    def test_reason_names_the_numbers(self, conn):
        budget = _budget(conn, llm_max_calls_per_day=1)
        budget.record(_ok(), task="note")
        assert "1/1" in budget.check().reason


class TestTokenCap:
    def test_refuses_once_spent(self, conn):
        budget = _budget(conn, llm_max_tokens_per_day=1_000)
        budget.record(_ok(1_000), task="note")
        status = budget.check(estimated_tokens=1)
        assert not status.allowed
        assert "token cap" in status.reason

    def test_a_large_call_is_refused_before_it_is_made(self, conn):
        """The estimate exists so an overrun is prevented, not just detected."""
        budget = _budget(conn, llm_max_tokens_per_day=1_000)
        assert not budget.check(estimated_tokens=5_000).allowed

    def test_a_call_that_fits_is_allowed(self, conn):
        budget = _budget(conn, llm_max_tokens_per_day=1_000)
        budget.record(_ok(400), task="note")
        assert budget.check(estimated_tokens=200).allowed

    def test_reason_mentions_the_size_of_the_pending_call(self, conn):
        budget = _budget(conn, llm_max_tokens_per_day=100)
        assert "5,000" in budget.check(estimated_tokens=5_000).reason


class TestDeepPassCap:
    def test_ordinary_calls_are_unaffected_by_the_weekly_cap(self, conn):
        budget = _budget(conn, llm_max_deep_passes_per_week=1)
        budget.record(_ok(), task="weekly_thesis", deep=True)
        assert budget.check(deep=False).allowed

    def test_refuses_a_second_deep_pass(self, conn):
        budget = _budget(conn, llm_max_deep_passes_per_week=1)
        budget.record(_ok(), task="weekly_thesis", deep=True)
        status = budget.check(deep=True)
        assert not status.allowed
        assert "deep-pass cap" in status.reason
        assert "2026-W34" in status.reason

    def test_a_failed_deep_pass_does_not_consume_the_week(self, conn):
        """The weekly cap rations successful theses, not failed attempts."""
        budget = _budget(conn, llm_max_deep_passes_per_week=1)
        budget.record(LLMResponse(error="503"), task="weekly_thesis", deep=True)
        assert budget.check(deep=True).allowed

    def test_a_cached_deep_pass_does_not_consume_the_week(self, conn):
        budget = _budget(conn, llm_max_deep_passes_per_week=1)
        budget.record(
            LLMResponse(text="x", provider="claude_cli", cached=True),
            task="weekly_thesis",
            deep=True,
        )
        assert budget.check(deep=True).allowed

    def test_last_weeks_passes_do_not_count(self, conn):
        last_week = _budget(conn, today=date(2026, 8, 13), llm_max_deep_passes_per_week=1)
        last_week.record(_ok(), task="weekly_thesis", deep=True)
        assert _budget(conn, llm_max_deep_passes_per_week=1).check(deep=True).allowed


class TestSummary:
    def test_totals_across_kinds_of_call(self, conn):
        budget = _budget(conn, llm_max_calls_per_day=10, llm_max_tokens_per_day=10_000)
        budget.record(_ok(300), task="note")
        budget.record(LLMResponse(error="boom"), task="note")
        budget.record(LLMResponse(text="x", provider="p", cached=True), task="note")
        summary = budget.summary()
        assert (summary.calls, summary.tokens) == (2, 300)
        assert (summary.cached_calls, summary.failed_calls) == (1, 1)

    def test_remaining_never_goes_negative(self, conn):
        budget = _budget(conn, llm_max_tokens_per_day=100)
        budget.record(_ok(500), task="note")
        assert budget.summary().tokens_left == 0

    def test_exhausted_flips_when_a_cap_is_hit(self, conn):
        budget = _budget(conn, llm_max_calls_per_day=1)
        budget.record(_ok(), task="note")
        assert budget.summary().exhausted is True

    def test_as_dict_is_json_ready(self, conn):
        data = _budget(conn).summary().as_dict()
        assert data["day"] == "2026-08-20"
        assert data["week"] == "2026-W34"
        assert set(data) >= {"calls_left", "tokens_left", "deep_passes_left", "exhausted"}

    def test_status_is_truthy_when_allowed(self, conn):
        assert bool(_budget(conn).check()) is True
