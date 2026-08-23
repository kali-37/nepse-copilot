"""Tests for the analyst and the schemas that guard its output.

Two contracts are pinned down here, and they are the reason AI mode is safe to
enable at all:

* **AI adds commentary, never numbers.** Not one of these schemas has a price,
  stop, target, size or date field, so there is no channel through which a model
  could reach a tradeable figure — the deterministic engine owns all of them.
  :class:`TestNoEngineNumbers` asserts the field sets exactly, so adding
  ``target_price`` to a note breaks the suite rather than the discipline.
* **A bad model reply costs prose and nothing else.** Free models emit fenced
  blocks, chatty preambles and truncated JSON. Every one of those must come back
  as ``None`` plus a readable degradation — never an exception, never a partly
  filled model.

Nothing here touches the network, a real CLI or a real provider: the analyst gets
an injected router, and the two end-to-end tests give a real :class:`LLMRouter` an
injected stub provider.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from nepse_trader.ai.analyst import Analyst
from nepse_trader.ai.budget import TokenBudget
from nepse_trader.ai.providers import LLMProvider, LLMResponse
from nepse_trader.ai.router import BULK, SYNTHESIS, LLMRouter
from nepse_trader.ai.schemas import (
    _MAX_ITEM_CHARS,
    _MAX_ITEMS,
    _MAX_PROSE,
    Critique,
    SymbolNote,
    WeeklyThesis,
    extract_json,
    normalise_citations,
    parse_into,
)
from nepse_trader.config import Settings
from nepse_trader.rag.corpus import Document
from nepse_trader.rag.evidence import build_evidence
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


# --- canned model replies ----------------------------------------------------


def _note_json(**kw) -> str:
    payload = {
        "stance": "accumulate",
        "conviction": 4,
        "thesis": "Volume confirms the breakout [E1].",
        "catalysts": ["Q4 results due"],
        "risks": ["thin liquidity"],
        "citations": ["E1", "E2"],
    }
    payload.update(kw)
    return json.dumps(payload)


def _thesis_json(**kw) -> str:
    payload = {
        "regime": "range-bound, thin volume",
        "summary": "Breadth is narrowing [E1].",
        "focus_symbols": ["nabil"],
        "avoid_symbols": ["upper"],
        "key_risks": ["a policy rate change"],
        "citations": ["E1"],
    }
    payload.update(kw)
    return json.dumps(payload)


def _critique_json(**kw) -> str:
    payload = {
        "verdict": "mixed",
        "concerns": ["the edge was measured on 40 trades [E2]"],
        "missing_evidence": ["sector breadth"],
        "citations": ["E2"],
    }
    payload.update(kw)
    return json.dumps(payload)


# --- test doubles ------------------------------------------------------------


def _reply(text: str) -> LLMResponse:
    return LLMResponse(text=text, provider="stub", model="stub-1")


class _FakeRouter:
    """Only the surface ``Analyst`` actually touches: ``complete`` and ``budget.today``.

    Building a real router here would test the router; this records the kwargs the
    analyst chose (tier, ``deep``, ``max_tokens``) which is what the analyst owns.
    """

    def __init__(self, *responses: LLMResponse, today: date = TODAY) -> None:
        self._responses = list(responses) or [_reply("{}")]
        self.budget = SimpleNamespace(today=today)
        self.calls: list[dict] = []

    def complete(self, prompt: str, **kwargs) -> LLMResponse:
        self.calls.append({"prompt": prompt, **kwargs})
        # The last canned response repeats, so a loop of failures needs one entry.
        return self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]


class _StubProvider(LLMProvider):
    """A provider that answers from a canned list and records what it was asked."""

    name = "stub"

    def __init__(self, *texts: str) -> None:
        self._texts = list(texts) or ["{}"]
        self.calls: list[dict] = []

    @property
    def model(self) -> str:
        return "stub-1"

    @property
    def available(self) -> bool:
        return True

    def complete(self, prompt, *, system=None, max_tokens=2048, temperature=0.2) -> LLMResponse:
        self.calls.append({"prompt": prompt, "system": system, "max_tokens": max_tokens})
        text = self._texts.pop(0) if len(self._texts) > 1 else self._texts[0]
        return LLMResponse(text=text, provider=self.name, model=self.model)


def _real_router(conn, *texts: str, **kw) -> tuple[LLMRouter, _StubProvider]:
    """A real router with every reachable leg injected — see LLMRouter.provider."""
    provider = _StubProvider(*texts)
    settings = _settings(llm_bulk_providers=["stub"], llm_synthesis_providers=["stub"], **kw)
    router = LLMRouter(
        conn,
        settings,
        providers={"stub": provider},
        budget=TokenBudget(conn, settings, today=TODAY),
    )
    return router, provider


def _analyst(conn, *responses: LLMResponse) -> Analyst:
    return Analyst(conn, _settings(), router=_FakeRouter(*responses))


# ===========================================================================
# A. Schemas — the boundary every model reply crosses
# ===========================================================================


class TestExtractJson:
    def test_a_bare_object_parses(self):
        assert extract_json('{"a": 1}') == {"a": 1}

    def test_a_json_fenced_block_parses(self):
        assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}

    def test_an_unlabelled_fence_parses(self):
        assert extract_json('```\n{"a": 1}\n```') == {"a": 1}

    def test_json_wrapped_in_prose_parses(self):
        """Free models ignore "no prose before or after it" constantly."""
        text = 'Sure! Here\'s the analysis: {"a": 1} Hope that helps.'
        assert extract_json(text) == {"a": 1}

    def test_non_json_returns_none(self):
        assert extract_json("I cannot help with that request.") is None

    def test_truncated_json_returns_none(self):
        assert extract_json('{"stance": "accumulate", "conviction":') is None

    def test_empty_text_returns_none(self):
        assert extract_json("") is None

    def test_a_scalar_is_not_a_payload(self):
        """``42`` is valid JSON but no model's worth of fields."""
        assert extract_json("42") is None


class TestParseInto:
    def test_a_well_formed_symbol_note(self):
        note = parse_into(SymbolNote, _note_json(), symbol="NABIL")
        assert note is not None
        assert (note.symbol, note.stance, note.conviction) == ("NABIL", "accumulate", 4)
        assert note.catalysts == ["Q4 results due"]

    def test_a_well_formed_weekly_thesis(self):
        thesis = parse_into(WeeklyThesis, _thesis_json(), week="2026-W34")
        assert thesis is not None
        assert thesis.week == "2026-W34"
        assert thesis.regime == "range-bound, thin volume"
        assert thesis.focus_symbols == ["NABIL"]  # symbols are normalised upward

    def test_a_well_formed_critique(self):
        critique = parse_into(Critique, _critique_json())
        assert critique is not None
        assert critique.verdict == "mixed"
        assert critique.missing_evidence == ["sector breadth"]

    def test_a_fenced_reply_parses(self):
        note = parse_into(SymbolNote, f"```json\n{_note_json()}\n```", symbol="NABIL")
        assert note is not None

    def test_a_chatty_reply_parses(self):
        text = f"Sure! Here's the analysis: {_note_json()} Hope that helps."
        assert parse_into(SymbolNote, text, symbol="NABIL") is not None

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "   ",
            "I'm sorry, I can't do that.",
            '{"stance": "accumulate", "conviction":',
            "<html><body>502 Bad Gateway</body></html>",
            '{"stance": "accumulate"}',  # valid JSON, missing required fields
            "[1, 2, 3]",  # an array of non-objects
            "null",
        ],
    )
    def test_unusable_output_returns_none_and_never_raises(self, text: str):
        """The contract: a failed pass costs narrative, never an exception."""
        assert parse_into(SymbolNote, text, symbol="NABIL") is None

    def test_an_array_of_objects_takes_the_first_object(self):
        """Some models wrap the single answer in a list."""
        note = parse_into(SymbolNote, f"[{_note_json()}]", symbol="NABIL")
        assert note is not None

    def test_defaults_override_what_the_model_echoed(self):
        """The symbol is known; a model that echoes the wrong one must not win."""
        note = parse_into(SymbolNote, _note_json(symbol="WRONG"), symbol="NABIL")
        assert note.symbol == "NABIL"

    def test_a_none_default_leaves_the_payload_alone(self):
        note = parse_into(SymbolNote, _note_json(symbol="nabil"), symbol=None)
        assert note.symbol == "NABIL"


class TestStance:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("buy", "accumulate"),
            ("strong buy", "accumulate"),
            ("add", "accumulate"),
            ("accumulating", "accumulate"),
            ("neutral", "hold"),
            ("wait", "hold"),
            ("watch", "hold"),
            ("sell", "reduce"),
            ("trim", "reduce"),
            ("exit", "reduce"),
            ("strong sell", "reduce"),
            ("avoid", "avoid"),
            ("stay away", "avoid"),
            ("no trade", "avoid"),
        ],
    )
    def test_trading_vocabulary_maps_onto_our_four(self, raw: str, expected: str):
        note = parse_into(SymbolNote, _note_json(stance=raw), symbol="NABIL")
        assert note.stance == expected

    def test_our_own_vocabulary_survives(self):
        note = parse_into(SymbolNote, _note_json(stance="hold"), symbol="NABIL")
        assert note.stance == "hold"

    def test_case_and_padding_are_ignored(self):
        note = parse_into(SymbolNote, _note_json(stance="  STRONG BUY "), symbol="NABIL")
        assert note.stance == "accumulate"

    @pytest.mark.parametrize("raw", ["moon", "high conviction long", "", "hodl"])
    def test_an_unmappable_stance_rejects_the_whole_note(self, raw: str):
        """Guessing at a stance we don't recognise would invent a recommendation."""
        assert parse_into(SymbolNote, _note_json(stance=raw), symbol="NABIL") is None


class TestVerdict:
    @pytest.mark.parametrize("raw", ["agree", "agrees", "concur", "supported"])
    def test_agreement_synonyms(self, raw: str):
        assert parse_into(Critique, _critique_json(verdict=raw)).verdict == "agree"

    @pytest.mark.parametrize("raw", ["disagree", "disagrees", "opposed", "reject"])
    def test_disagreement_synonyms(self, raw: str):
        assert parse_into(Critique, _critique_json(verdict=raw)).verdict == "disagree"

    @pytest.mark.parametrize("raw", ["mixed", "partial", "partially agree", "neutral", "unclear"])
    def test_hedged_synonyms_collapse_to_mixed(self, raw: str):
        assert parse_into(Critique, _critique_json(verdict=raw)).verdict == "mixed"

    def test_an_unmappable_verdict_rejects_the_critique(self):
        assert parse_into(Critique, _critique_json(verdict="lol")) is None


class TestConviction:
    @pytest.mark.parametrize(("raw", "expected"), [(0, 1), (-3, 1), (6, 5), (99, 5)])
    def test_out_of_range_clamps_rather_than_rejects(self, raw: int, expected: int):
        """A model that wrote 9 meant "very confident", not "invalid note"."""
        note = parse_into(SymbolNote, _note_json(conviction=raw), symbol="NABIL")
        assert note.conviction == expected

    def test_prose_around_the_number_is_stripped(self):
        note = parse_into(SymbolNote, _note_json(conviction="4 out of 5"), symbol="NABIL")
        assert note.conviction == 4

    def test_a_fraction_takes_the_first_number(self):
        note = parse_into(SymbolNote, _note_json(conviction="3/5"), symbol="NABIL")
        assert note.conviction == 3

    def test_a_float_truncates_into_range(self):
        note = parse_into(SymbolNote, _note_json(conviction=7.6), symbol="NABIL")
        assert note.conviction == 5

    def test_a_wordy_confidence_is_rejected(self):
        """No digit means no ordinal, and inventing one would be a fabrication."""
        assert parse_into(SymbolNote, _note_json(conviction="high"), symbol="NABIL") is None


class TestCitations:
    @pytest.mark.parametrize("raw", ["E1", "[E1]", "e1", "[e1]", "1", "[1]"])
    def test_every_marker_spelling_normalises_to_one_form(self, raw: str):
        assert normalise_citations([raw]) == ["[E1]"]

    def test_markers_are_pulled_out_of_a_string(self):
        assert normalise_citations("supported by [E1][E2] and E3") == ["[E1]", "[E2]", "[E3]"]

    def test_duplicates_collapse(self):
        assert normalise_citations(["E1", "[E1]", "e1"]) == ["[E1]"]

    def test_unrecognisable_markers_are_dropped_not_guessed(self):
        """A marker only means something if it can match an evidence item."""
        assert normalise_citations(["E1a", "the news article", "[E4]"]) == ["[E4]"]

    def test_a_non_sequence_yields_nothing(self):
        assert normalise_citations(42) == []

    def test_the_list_is_capped(self):
        assert len(normalise_citations([f"E{i}" for i in range(1, 20)])) == _MAX_ITEMS

    def test_every_model_normalises_its_citations(self):
        note = parse_into(SymbolNote, _note_json(citations="see E1 and [e2]"), symbol="NABIL")
        thesis = parse_into(WeeklyThesis, _thesis_json(citations=["e1"]), week="w")
        critique = parse_into(Critique, _critique_json(citations=["E2"]))
        assert note.citations == ["[E1]", "[E2]"]
        assert thesis.citations == ["[E1]"]
        assert critique.citations == ["[E2]"]


class TestClamps:
    def test_long_prose_is_truncated_not_rejected(self):
        """A rambling model costs a shorter card, not a failed run."""
        note = parse_into(SymbolNote, _note_json(thesis="x" * 5_000), symbol="NABIL")
        assert note is not None
        assert len(note.thesis) == _MAX_PROSE

    def test_the_weekly_summary_is_clamped_too(self):
        thesis = parse_into(WeeklyThesis, _thesis_json(summary="y" * 5_000), week="w")
        assert len(thesis.summary) == _MAX_PROSE

    def test_too_many_items_are_dropped_from_the_end(self):
        note = parse_into(
            SymbolNote,
            _note_json(catalysts=[f"catalyst {i}" for i in range(20)]),
            symbol="NABIL",
        )
        assert len(note.catalysts) == _MAX_ITEMS
        assert note.catalysts[0] == "catalyst 0"

    def test_a_long_item_is_truncated(self):
        note = parse_into(SymbolNote, _note_json(risks=["z" * 900]), symbol="NABIL")
        assert len(note.risks[0]) == _MAX_ITEM_CHARS

    def test_a_bulleted_string_becomes_a_list(self):
        """Models write markdown bullets however the mood takes them."""
        note = parse_into(
            SymbolNote, _note_json(risks="- thin volume\n* index drawdown"), symbol="NABIL"
        )
        assert note.risks == ["thin volume", "index drawdown"]

    def test_whitespace_is_flattened(self):
        note = parse_into(SymbolNote, _note_json(thesis="a\n\n  b\t c"), symbol="NABIL")
        assert note.thesis == "a b c"

    def test_missing_lists_default_to_empty(self):
        note = parse_into(
            SymbolNote,
            json.dumps({"stance": "hold", "conviction": 3, "thesis": "t"}),
            symbol="NABIL",
        )
        assert (note.catalysts, note.risks, note.citations) == ([], [], [])


class TestNoEngineNumbers:
    """The load-bearing invariant: no schema field carries a number the engine owns.

    Prices, stops, targets, sizes and dates come from the deterministic engine and
    AI mode may not touch them — the prompt asks for that, this enforces it. If
    someone adds ``target_price`` to a note, these tests fail.
    """

    def test_symbol_note_fields_are_exactly_the_commentary_layer(self):
        assert set(SymbolNote.model_fields) == {
            "citations",
            "symbol",
            "stance",
            "conviction",
            "thesis",
            "catalysts",
            "risks",
        }

    def test_weekly_thesis_fields_are_exactly_posture_and_attention(self):
        assert set(WeeklyThesis.model_fields) == {
            "citations",
            "week",
            "regime",
            "summary",
            "focus_symbols",
            "avoid_symbols",
            "key_risks",
        }

    def test_critique_fields_are_exactly_objections(self):
        assert set(Critique.model_fields) == {
            "citations",
            "verdict",
            "concerns",
            "missing_evidence",
        }

    @pytest.mark.parametrize("model", [SymbolNote, WeeklyThesis, Critique])
    def test_no_field_name_names_a_tradeable_number(self, model: type):
        forbidden = ("price", "stop", "target", "size", "qty", "quantity", "shares", "date")
        offenders = [
            name for name in model.model_fields for token in forbidden if token in name.lower()
        ]
        assert offenders == []

    @pytest.mark.parametrize("model", [SymbolNote, WeeklyThesis, Critique])
    def test_every_field_is_text_or_the_conviction_ordinal(self, model: type):
        """A market number would be a float; nothing here may be one."""
        for name, field in model.model_fields.items():
            if name == "conviction":
                continue  # an intentional 1..5 ordinal, not a market number
            assert field.annotation in (str, list[str]), f"{model.__name__}.{name}"

    def test_conviction_is_the_only_number_and_it_is_a_bounded_ordinal(self):
        ints = [
            name
            for model in (SymbolNote, WeeklyThesis, Critique)
            for name, field in model.model_fields.items()
            if field.annotation is int
        ]
        assert ints == ["conviction"]
        assert parse_into(SymbolNote, _note_json(conviction=1_000), symbol="X").conviction == 5


# ===========================================================================
# B. The Analyst — three passes, each degrading on its own
# ===========================================================================


class TestSymbolNote:
    def test_a_good_reply_becomes_a_populated_note(self, conn):
        analyst = _analyst(conn, _reply(_note_json()))
        note = analyst.symbol_note(symbol="NABIL", plan="entry computed", evidence="[E1] news")
        assert note is not None
        assert (note.symbol, note.stance, note.conviction) == ("NABIL", "accumulate", 4)
        assert analyst.degradations == []
        assert analyst.degraded is False

    def test_it_uses_the_bulk_tier(self, conn):
        """One pass per symbol times twenty-five symbols — free models, not synthesis."""
        analyst = _analyst(conn, _reply(_note_json()))
        analyst.symbol_note(symbol="NABIL", plan="p", evidence="e")
        call = analyst.router.calls[0]
        assert (call["tier"], call["task"], call["deep"]) == (BULK, "symbol_note", False)

    def test_the_symbol_plan_and_evidence_all_reach_the_prompt(self, conn):
        analyst = _analyst(conn, _reply(_note_json()))
        analyst.symbol_note(symbol="NABIL", plan="stop at 512", evidence="[E1] earnings beat")
        prompt = analyst.router.calls[0]["prompt"]
        assert "NABIL" in prompt
        assert "stop at 512" in prompt
        assert "[E1] earnings beat" in prompt

    def test_an_evidence_pack_is_rendered_into_the_prompt(self, conn):
        pack = build_evidence(
            [Document(doc_id="news:1", kind="news", title="Rate cut", body="NRB cut rates")]
        )
        analyst = _analyst(conn, _reply(_note_json()))
        analyst.symbol_note(symbol="NABIL", plan="p", evidence=pack)
        assert "NRB cut rates" in analyst.router.calls[0]["prompt"]

    def test_malformed_output_returns_none_and_names_the_symbol(self, conn):
        analyst = _analyst(conn, _reply("I think you should buy it, honestly."))
        assert analyst.symbol_note(symbol="NABIL", plan="p", evidence="e") is None
        assert analyst.degradations == ["NABIL: model output failed validation"]

    def test_a_provider_error_returns_none_and_carries_the_reason(self, conn):
        analyst = _analyst(conn, LLMResponse(error="openrouter: rate limited"))
        assert analyst.symbol_note(symbol="NABIL", plan="p", evidence="e") is None
        assert analyst.degradations == ["NABIL: openrouter: rate limited"]

    def test_a_provider_error_skips_parsing_entirely(self, conn):
        """One failure, one degradation — not "no response" plus "failed validation"."""
        analyst = _analyst(conn, LLMResponse(error="boom"))
        analyst.symbol_note(symbol="NABIL", plan="p", evidence="e")
        assert len(analyst.degradations) == 1

    def test_empty_text_without_an_error_still_degrades(self, conn):
        analyst = _analyst(conn, LLMResponse(text="   ", provider="stub"))
        assert analyst.symbol_note(symbol="NABIL", plan="p", evidence="e") is None
        assert analyst.degradations == ["NABIL: no response"]


class TestWeeklyThesis:
    def test_a_good_reply_becomes_a_thesis(self, conn):
        analyst = _analyst(conn, _reply(_thesis_json()))
        thesis = analyst.weekly_thesis(
            symbols=["NABIL"], market="breadth narrowing", evidence="[E1] x", week="2026-W34"
        )
        assert thesis is not None
        assert thesis.week == "2026-W34"
        assert thesis.focus_symbols == ["NABIL"]
        assert analyst.degradations == []

    def test_it_is_the_deep_synthesis_pass(self, conn):
        """``deep`` is what the weekly cap counts; it must reach the router."""
        analyst = _analyst(conn, _reply(_thesis_json()))
        analyst.weekly_thesis(symbols=["NABIL"], market="m", evidence="e", week="2026-W34")
        call = analyst.router.calls[0]
        assert call["tier"] == SYNTHESIS
        assert call["deep"] is True
        assert call["task"] == "weekly_thesis"
        assert call["max_tokens"] == 3072

    def test_the_week_label_comes_from_the_budget_clock_by_default(self, conn):
        """The label is part of the prompt, so a second run in the week is a cache hit."""
        analyst = _analyst(conn, _reply(_thesis_json()))
        thesis = analyst.weekly_thesis(symbols=["NABIL"], market="m", evidence="e")
        assert thesis.week == "2026-W34"
        assert "2026-W34" in analyst.router.calls[0]["prompt"]

    def test_an_explicit_date_picks_the_week(self, conn):
        analyst = _analyst(conn, _reply(_thesis_json()))
        thesis = analyst.weekly_thesis(
            symbols=["NABIL"], market="m", evidence="e", today=date(2026, 1, 8)
        )
        assert thesis.week == "2026-W02"

    def test_malformed_output_names_the_week_in_the_degradation(self, conn):
        analyst = _analyst(conn, _reply("The market looks fine to me."))
        result = analyst.weekly_thesis(symbols=["NABIL"], market="m", evidence="e", week="2026-W34")
        assert result is None
        assert analyst.degradations == [
            "weekly thesis for 2026-W34: model output failed validation"
        ]

    def test_a_provider_error_is_labelled_with_the_week(self, conn):
        analyst = _analyst(conn, LLMResponse(error="deep-pass cap reached"))
        assert analyst.weekly_thesis(symbols=[], market="m", evidence="e", week="2026-W34") is None
        assert analyst.degradations == ["2026-W34: deep-pass cap reached"]


class TestCritique:
    def test_a_good_reply_becomes_a_critique(self, conn):
        analyst = _analyst(conn, _reply(_critique_json()))
        critique = analyst.critique(plan="buy NABIL at 512", evidence="[E2] x")
        assert critique is not None
        assert critique.verdict == "mixed"
        assert critique.concerns
        assert analyst.degradations == []

    def test_it_uses_the_synthesis_tier_but_is_not_deep(self, conn):
        analyst = _analyst(conn, _reply(_critique_json()))
        analyst.critique(plan="p", evidence="e")
        call = analyst.router.calls[0]
        assert (call["tier"], call["task"], call["deep"]) == (SYNTHESIS, "critique", False)

    def test_the_plan_reaches_the_prompt(self, conn):
        analyst = _analyst(conn, _reply(_critique_json()))
        analyst.critique(plan="buy NABIL at 512", evidence="e")
        assert "buy NABIL at 512" in analyst.router.calls[0]["prompt"]

    def test_malformed_output_returns_none_and_degrades(self, conn):
        analyst = _analyst(conn, _reply("Looks reasonable to me!"))
        assert analyst.critique(plan="p", evidence="e") is None
        assert analyst.degradations == ["critique: model output failed validation"]

    def test_a_provider_error_returns_none_and_degrades(self, conn):
        analyst = _analyst(conn, LLMResponse(error="claude_cli: timed out after 180s"))
        assert analyst.critique(plan="p", evidence="e") is None
        assert analyst.degradations == ["critique: claude_cli: timed out after 180s"]


class TestBanner:
    def test_no_degradations_means_no_banner(self, conn):
        """An empty string, so a caller can print it unconditionally."""
        analyst = _analyst(conn, _reply(_note_json()))
        analyst.symbol_note(symbol="NABIL", plan="p", evidence="e")
        assert analyst.banner() == ""

    def test_a_single_reason_is_stated_once(self, conn):
        analyst = _analyst(conn, LLMResponse(error="rate limited"))
        analyst.symbol_note(symbol="NABIL", plan="p", evidence="e")
        assert analyst.banner() == "AI narrative incomplete — NABIL: rate limited"

    def test_a_repeated_reason_collapses_to_a_count(self, conn):
        """The cap is hit once, then every call after it — twenty-five identical lines."""
        analyst = _analyst(conn, _reply("not json"))
        for _ in range(3):
            analyst.symbol_note(symbol="NABIL", plan="p", evidence="e")
        assert analyst.banner() == (
            "AI narrative incomplete — NABIL: model output failed validation (x3)"
        )

    def test_at_most_four_reasons_are_listed(self, conn):
        analyst = _analyst(conn, _reply("not json"))
        for symbol in ("AAA", "BBB", "CCC", "DDD", "EEE", "FFF"):
            analyst.symbol_note(symbol=symbol, plan="p", evidence="e")
        assert len(analyst.degradations) == 6
        assert analyst.banner().count("; ") == 3  # four parts, three separators
        assert "EEE" not in analyst.banner()

    def test_degraded_flips_on_the_first_failure(self, conn):
        analyst = _analyst(conn, LLMResponse(error="boom"))
        assert analyst.degraded is False
        analyst.critique(plan="p", evidence="e")
        assert analyst.degraded is True


class TestThroughARealRouter:
    """The same passes with a real LLMRouter, so the wiring is not just mocked."""

    def test_the_ground_rules_and_system_prompt_reach_the_provider(self, conn):
        router, provider = _real_router(conn, _note_json())
        note = Analyst(conn, router.settings, router=router).symbol_note(
            symbol="NABIL", plan="p", evidence="[E1] x"
        )
        assert note is not None
        assert "Ground rules" in provider.calls[0]["prompt"]
        assert "NEPSE" in provider.calls[0]["system"]

    def test_the_weekly_pass_is_recorded_as_a_deep_pass(self, conn):
        """End-to-end proof of ``deep=True``: the weekly cap's ledger sees it."""
        router, _ = _real_router(conn, _thesis_json())
        thesis = Analyst(conn, router.settings, router=router).weekly_thesis(
            symbols=["NABIL"], market="m", evidence="e", week="2026-W34"
        )
        assert thesis is not None
        assert router.budget.deep_passes_this_week() == 1

    def test_a_budget_refusal_becomes_the_banner(self, conn):
        """The docstring's own example: a cap arrives as prose, not an exception."""
        router, provider = _real_router(conn, _note_json(), llm_max_calls_per_day=0)
        analyst = Analyst(conn, router.settings, router=router)
        assert analyst.symbol_note(symbol="NABIL", plan="p", evidence="e") is None
        assert provider.calls == []  # refused before the provider was reached
        assert "daily call cap reached" in analyst.banner()

    def test_offline_with_a_cold_cache_degrades_rather_than_calling_out(self, conn):
        router, provider = _real_router(conn, _note_json())
        router.online = False
        analyst = Analyst(conn, router.settings, router=router)
        assert analyst.symbol_note(symbol="NABIL", plan="p", evidence="e") is None
        assert provider.calls == []
        assert "offline" in analyst.banner()

    def test_a_second_identical_pass_is_served_from_the_cache(self, conn):
        """The prompt is the key, so a repeat run costs one provider call, not two."""
        router, provider = _real_router(conn, _note_json())
        analyst = Analyst(conn, router.settings, router=router)
        for _ in range(2):
            assert analyst.symbol_note(symbol="NABIL", plan="p", evidence="e") is not None
        assert len(provider.calls) == 1
