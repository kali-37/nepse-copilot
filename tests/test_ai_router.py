"""Tests for the LLM router.

The contract this file pins down is the order of the gates — **cache, then
budget, then the chain** — and that every way of failing arrives as an
:class:`LLMResponse` with ``error`` set. That is what lets AI mode degrade to
Normal mode with a banner mid-run instead of aborting a daily pass.

Three properties carry the module:

* **A cache hit costs nothing and touches nothing.** It must not reach a
  provider (that would be a real API call for an answer we already have) and it
  must not consume the daily caps, or a re-run would burn the day's allowance on
  work it isn't doing. Every fake here records its calls so a hit that leaked
  through to a provider is visible rather than silent.
* **Offline is cache-only, not disabled.** A thesis fetched on Sunday stays
  readable on a Thursday with no network, and a miss degrades instead of dialling
  out.
* **A refusal says why.** The budget reason, the tier and its configured chain,
  and each failing leg's error all have to survive into ``response.error``,
  because that string is what the report banner shows.

An injected ``providers=`` mapping is authoritative: :meth:`LLMRouter.provider`
returns ``None`` for anything outside it rather than building behind it. Every
test that expects a provider to be reachable therefore injects it — an
uninjected fake would be skipped and the test would pass for the wrong reason.
Nothing here touches the network or a real CLI.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from nepse_trader.ai.budget import TokenBudget
from nepse_trader.ai.providers import LLMProvider, LLMResponse
from nepse_trader.ai.router import BULK, SYNTHESIS, LLMRouter
from nepse_trader.config import Settings
from nepse_trader.storage import Storage

TODAY = date(2026, 8, 20)  # a Thursday, ISO week 34


@pytest.fixture
def conn(tmp_path: Path):
    storage = Storage(tmp_path / "ai.db")
    yield storage._conn
    storage.close()


def _settings(**kw) -> Settings:
    base = {"_env_file": None}
    base.update(kw)
    return Settings(**base)


class FakeProvider(LLMProvider):
    """A provider that answers from a script and records every call it got.

    ``calls`` is the whole point: it is how a test proves a cache hit or an
    offline miss never reached out.
    """

    def __init__(
        self,
        name: str = "fake",
        *,
        text: str = "the answer",
        error: str = "",
        available: bool = True,
        model: str = "fake-1",
    ) -> None:
        self.name = name
        self._text = text
        self._error = error
        self._available = available
        self._model = model
        self.calls: list[tuple[str, str | None]] = []

    @property
    def model(self) -> str:
        return self._model

    @property
    def available(self) -> bool:
        return self._available

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ) -> LLMResponse:
        self.calls.append((prompt, system))
        return LLMResponse(
            text="" if self._error else self._text,
            provider=self.name,
            model=self._model,
            prompt_tokens=10,
            completion_tokens=5,
            error=self._error,
        )


class ExplodingProvider(LLMProvider):
    """A badly-behaved leg: it raises instead of returning a failed response."""

    name = "boom"

    @property
    def model(self) -> str:
        return "boom-1"

    @property
    def available(self) -> bool:
        return True

    def complete(self, prompt: str, **kw) -> LLMResponse:
        raise RuntimeError("provider exploded")


def _router(
    conn, providers: dict[str, LLMProvider] | None = None, *, online=None, **kw
) -> LLMRouter:
    """A router whose ledger day is pinned, so a midnight run can't straddle two."""
    settings = _settings(**kw)
    return LLMRouter(
        conn,
        settings,
        providers=providers,
        budget=TokenBudget(conn, settings, today=TODAY),
        online=online,
    )


def _prime_cache(router: LLMRouter, *, task: str, prompt: str, text: str = "yesterday") -> None:
    key = router.cache.key(task=task, prompt=prompt)
    stored = LLMResponse(text=text, provider="claude_cli", model="claude-opus-5", prompt_tokens=900)
    assert router.cache.put(key, stored, task=task)


def _ok(tokens: int = 100) -> LLMResponse:
    return LLMResponse(text="answer", provider="fake", model="fake-1", prompt_tokens=tokens)


class TestChain:
    def test_each_tier_comes_from_its_own_setting(self, conn):
        router = _router(
            conn,
            llm_bulk_providers=["openrouter"],
            llm_synthesis_providers=["claude_cli", "anthropic"],
        )
        assert router.chain(BULK) == ["openrouter"]
        assert router.chain(SYNTHESIS) == ["claude_cli", "anthropic"]

    def test_unknown_tier_raises(self, conn):
        """Tiers are code, not config — a typo here is a bug, not a bad .env."""
        with pytest.raises(ValueError, match="unknown tier"):
            _router(conn).chain("medium")

    def test_a_repeated_name_is_dropped_but_order_is_kept(self, conn):
        router = _router(conn, llm_bulk_providers=["b", "a", "b", "c"])
        assert router.chain(BULK) == ["b", "a", "c"]

    def test_blank_and_padded_entries_are_cleaned(self, conn):
        router = _router(conn, llm_bulk_providers=[" claude_cli ", "", "   "])
        assert router.chain(BULK) == ["claude_cli"]


class TestProviderLookup:
    def test_an_injected_set_is_authoritative(self, conn):
        """The router must never build a real provider behind an injected mapping."""
        router = _router(conn, {"fake": FakeProvider()})
        assert router.provider("fake") is not None
        assert router.provider("claude_cli") is None

    def test_an_unknown_name_is_none_rather_than_an_exception(self, conn):
        """A typo in .env degrades the run; it does not crash it."""
        assert _router(conn).provider("gpt5") is None

    def test_built_instances_are_reused(self, conn):
        router = _router(conn)
        assert router.provider("openrouter") is router.provider("openrouter")

    def test_unavailable_legs_are_skipped(self, conn):
        usable = FakeProvider("b")
        router = _router(
            conn,
            {"a": FakeProvider("a", available=False), "b": usable},
            llm_bulk_providers=["a", "b"],
        )
        assert router.available(BULK) == [usable]


class TestCacheHit:
    def test_a_hit_never_reaches_a_provider(self, conn):
        provider = FakeProvider()
        router = _router(conn, {"fake": provider}, llm_bulk_providers=["fake"])
        _prime_cache(router, task="note", prompt="p")
        response = router.complete("p", task="note")
        assert response.text == "yesterday"
        assert response.cached is True
        assert provider.calls == []

    def test_a_hit_is_recorded_but_bills_nothing(self, conn):
        """Honest accounting: the hit shows up, and consumes none of the caps."""
        router = _router(conn, {"fake": FakeProvider()}, llm_bulk_providers=["fake"])
        _prime_cache(router, task="note", prompt="p")
        router.complete("p", task="note")
        assert router.budget.spent_today() == (0, 0)
        assert router.budget.summary().cached_calls == 1

    def test_use_cache_false_goes_back_to_the_provider(self, conn):
        provider = FakeProvider(text="fresh")
        router = _router(conn, {"fake": provider}, llm_bulk_providers=["fake"])
        _prime_cache(router, task="note", prompt="p")
        response = router.complete("p", task="note", use_cache=False)
        assert response.text == "fresh"
        assert len(provider.calls) == 1

    def test_a_different_prompt_is_a_miss(self, conn):
        provider = FakeProvider(text="fresh")
        router = _router(conn, {"fake": provider}, llm_bulk_providers=["fake"])
        _prime_cache(router, task="note", prompt="p")
        assert router.complete("other", task="note").text == "fresh"


class TestChainFallthrough:
    def test_a_failing_leg_falls_through_to_the_next(self, conn):
        first = FakeProvider("first", error="rate limited")
        second = FakeProvider("second", text="second answer")
        router = _router(
            conn,
            {"first": first, "second": second},
            llm_bulk_providers=["first", "second"],
        )
        response = router.complete("p", task="note")
        assert response.text == "second answer"
        assert response.provider == "second"
        assert len(first.calls) == 1  # it really was tried, not skipped

    def test_a_later_leg_is_not_called_once_one_answers(self, conn):
        second = FakeProvider("second")
        router = _router(
            conn,
            {"first": FakeProvider("first"), "second": second},
            llm_bulk_providers=["first", "second"],
        )
        assert router.complete("p", task="note").provider == "first"
        assert second.calls == []

    def test_every_leg_failing_names_each_problem(self, conn):
        router = _router(
            conn,
            {"a": FakeProvider("a", error="429"), "b": FakeProvider("b", error="503")},
            llm_bulk_providers=["a", "b"],
        )
        response = router.complete("p", task="note")
        assert not response.ok
        assert "a: 429" in response.error
        assert "b: 503" in response.error

    def test_each_failed_attempt_burns_a_call(self, conn):
        """A provider stuck in a failure loop must not be retried without limit."""
        router = _router(
            conn,
            {"a": FakeProvider("a", error="429"), "b": FakeProvider("b", error="503")},
            llm_bulk_providers=["a", "b"],
        )
        router.complete("p", task="note")
        assert router.budget.spent_today() == (2, 0)  # calls counted, no tokens billed

    def test_the_tier_selects_the_chain(self, conn):
        bulk = FakeProvider("bulk_leg", text="cheap")
        deep = FakeProvider("deep_leg", text="considered")
        router = _router(
            conn,
            {"bulk_leg": bulk, "deep_leg": deep},
            llm_bulk_providers=["bulk_leg"],
            llm_synthesis_providers=["deep_leg"],
        )
        assert router.complete("p", task="thesis", tier=SYNTHESIS).text == "considered"
        assert bulk.calls == []

    def test_system_prompt_and_text_reach_the_provider(self, conn):
        provider = FakeProvider()
        router = _router(conn, {"fake": provider}, llm_bulk_providers=["fake"])
        router.complete("the evidence", task="note", system="be terse")
        assert provider.calls == [("the evidence", "be terse")]


class TestCacheWrite:
    def test_a_successful_response_is_cached(self, conn):
        router = _router(conn, {"fake": FakeProvider(text="fresh")}, llm_bulk_providers=["fake"])
        router.complete("p", task="note")
        hit = router.cache.get(router.cache.key(task="note", prompt="p"))
        assert hit is not None
        assert hit.text == "fresh"

    def test_a_second_identical_call_is_served_from_the_cache(self, conn):
        provider = FakeProvider(text="fresh")
        router = _router(conn, {"fake": provider}, llm_bulk_providers=["fake"])
        router.complete("p", task="note")
        second = router.complete("p", task="note")
        assert second.cached is True
        assert len(provider.calls) == 1

    def test_a_failure_is_not_cached(self, conn):
        """A five-minute outage must not be remembered for the whole TTL."""
        router = _router(conn, {"fake": FakeProvider(error="503")}, llm_bulk_providers=["fake"])
        router.complete("p", task="note")
        assert router.cache.get(router.cache.key(task="note", prompt="p")) is None

    def test_the_system_prompt_is_part_of_the_cached_key(self, conn):
        provider = FakeProvider(text="fresh")
        router = _router(conn, {"fake": provider}, llm_bulk_providers=["fake"])
        router.complete("p", task="note", system="be terse")
        assert router.complete("p", task="note", system="be verbose").cached is False
        assert len(provider.calls) == 2


class TestOffline:
    def test_a_miss_degrades_without_calling_out(self, conn):
        provider = FakeProvider()
        router = _router(conn, {"fake": provider}, llm_bulk_providers=["fake"], online=False)
        response = router.complete("p", task="note")
        assert not response.ok
        assert "offline" in response.error
        assert provider.calls == []

    def test_a_cached_answer_is_still_served(self, conn):
        """Cache-only, not disabled: Sunday's thesis is readable on Thursday."""
        router = _router(conn, {"fake": FakeProvider()}, llm_bulk_providers=["fake"], online=False)
        _prime_cache(router, task="thesis", prompt="p")
        response = router.complete("p", task="thesis")
        assert response.ok
        assert response.text == "yesterday"

    def test_the_refusal_is_logged_in_the_ledger(self, conn):
        router = _router(conn, {"fake": FakeProvider()}, llm_bulk_providers=["fake"], online=False)
        router.complete("p", task="note")
        assert router.budget.summary().failed_calls == 1
        assert "offline" in router.budget.history()[0]["error"]

    def test_offline_comes_from_settings_when_not_passed(self, conn):
        router = LLMRouter(conn, _settings(online=False), providers={})
        assert router.online is False

    def test_an_explicit_flag_beats_the_setting(self, conn):
        """A resolved ``--offline`` must not be second-guessed by the .env value."""
        router = LLMRouter(conn, _settings(online=False), providers={}, online=True)
        assert router.online is True


class TestBudgetGate:
    def test_an_exhausted_call_cap_returns_the_reason(self, conn):
        provider = FakeProvider()
        router = _router(
            conn,
            {"fake": provider},
            llm_bulk_providers=["fake"],
            llm_max_calls_per_day=1,
        )
        router.budget.record(_ok(), task="earlier")
        response = router.complete("p", task="note")
        assert not response.ok
        assert "budget:" in response.error
        assert "call cap reached (1/1)" in response.error
        assert provider.calls == []  # refused before it was made

    def test_the_token_cap_refuses_before_the_call(self, conn):
        provider = FakeProvider()
        router = _router(
            conn,
            {"fake": provider},
            llm_bulk_providers=["fake"],
            llm_max_tokens_per_day=10,
        )
        response = router.complete("x" * 4_000, task="note")
        assert "token cap reached" in response.error
        assert provider.calls == []

    def test_the_weekly_deep_cap_only_binds_deep_passes(self, conn):
        router = _router(
            conn,
            {"fake": FakeProvider()},
            llm_bulk_providers=["fake"],
            llm_max_deep_passes_per_week=1,
        )
        router.budget.record(_ok(), task="weekly_thesis", deep=True)
        assert "deep-pass cap" in router.complete("p", task="thesis", deep=True).error
        assert router.complete("p", task="note", deep=False).ok

    def test_a_hit_is_served_even_with_the_budget_gone(self, conn):
        """The cache is checked first precisely so a spent day is still readable."""
        router = _router(
            conn,
            {"fake": FakeProvider()},
            llm_bulk_providers=["fake"],
            llm_max_calls_per_day=1,
        )
        _prime_cache(router, task="note", prompt="p")
        router.budget.record(_ok(), task="earlier")
        assert router.complete("p", task="note").ok


class TestNoConfiguredProvider:
    def test_an_all_unavailable_tier_names_the_tier_and_the_chain(self, conn):
        router = _router(
            conn,
            {"a": FakeProvider("a", available=False), "b": FakeProvider("b", available=False)},
            llm_bulk_providers=["a", "b"],
        )
        response = router.complete("p", task="note")
        assert not response.ok
        assert "no configured provider for bulk" in response.error
        assert "chain: a, b" in response.error

    def test_an_empty_chain_says_so(self, conn):
        response = _router(conn, {}, llm_bulk_providers=[]).complete("p", task="note")
        assert "(none)" in response.error

    def test_an_unknown_name_in_a_chain_is_survived(self, conn):
        """The router uses the legs it can build and ignores the rest."""
        usable = FakeProvider("fake")
        router = _router(conn, {"fake": usable}, llm_bulk_providers=["gpt5", "fake"])
        response = router.complete("p", task="note")
        assert response.ok
        assert len(usable.calls) == 1

    def test_a_chain_of_only_unknown_names_degrades(self, conn):
        response = _router(conn, llm_bulk_providers=["gpt5"]).complete("p", task="note")
        assert not response.ok
        assert "no configured provider" in response.error

    def test_the_refusal_is_logged_in_the_ledger(self, conn):
        router = _router(conn, {}, llm_bulk_providers=["gpt5"])
        router.complete("p", task="note")
        assert router.budget.summary().failed_calls == 1


class TestStatus:
    def test_reports_the_documented_shape(self, conn):
        router = _router(conn, {"fake": FakeProvider()}, llm_bulk_providers=["fake"])
        status = router.status()
        assert set(status) == {"online", "tiers", "budget", "cache"}
        assert set(status["tiers"]) == {BULK, SYNTHESIS}
        assert status["online"] is True
        assert status["budget"]["day"] == TODAY.isoformat()
        assert status["cache"]["entries"] == 0

    def test_each_leg_carries_name_known_available_and_model(self, conn):
        router = _router(conn, {"fake": FakeProvider()}, llm_bulk_providers=["fake"])
        assert router.status()["tiers"][BULK] == [
            {"name": "fake", "known": True, "available": True, "model": "fake-1"}
        ]

    def test_an_unknown_leg_is_marked_not_known(self, conn):
        router = _router(conn, {}, llm_bulk_providers=["gpt5"])
        leg = router.status()["tiers"][BULK][0]
        assert (leg["known"], leg["available"], leg["model"]) == (False, False, "")

    def test_a_configured_but_unusable_leg_is_known_and_unavailable(self, conn):
        """What ``ai models`` shows for a provider whose key is missing."""
        router = _router(
            conn,
            {"fake": FakeProvider(available=False)},
            llm_bulk_providers=["fake"],
        )
        leg = router.status()["tiers"][BULK][0]
        assert (leg["known"], leg["available"]) == (True, False)

    def test_offline_shows_in_the_status(self, conn):
        assert _router(conn, {}, online=False).status()["online"] is False


class TestARaisingProviderIsContained:
    """The invariant the whole layer rests on: ``complete`` never raises.

    The shipped providers turn their own failures into data, but that is a
    convention. A third-party leg, or an error type an existing leg doesn't
    catch, would otherwise escape here and abort a daily pass halfway through —
    the exact failure AI mode's degradation exists to prevent.
    """

    def test_an_exception_becomes_a_failed_response(self, conn):
        router = _router(conn, {"boom": ExplodingProvider()}, llm_bulk_providers=["boom"])
        response = router.complete("p", task="t")
        assert not response.ok
        assert "RuntimeError" in response.error
        assert "provider exploded" in response.error

    def test_the_chain_carries_on_past_a_raising_leg(self, conn):
        good = FakeProvider("good", text="survived")
        router = _router(
            conn,
            {"boom": ExplodingProvider(), "good": good},
            llm_bulk_providers=["boom", "good"],
        )
        response = router.complete("p", task="t")
        assert response.text == "survived"
        assert len(good.calls) == 1

    def test_a_raising_leg_still_burns_a_call_in_the_ledger(self, conn):
        """Otherwise a provider stuck in a raising loop would never hit the cap."""
        router = _router(conn, {"boom": ExplodingProvider()}, llm_bulk_providers=["boom"])
        router.complete("p", task="t")
        assert router.budget.summary().failed_calls == 1
