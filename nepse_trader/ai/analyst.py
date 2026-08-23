"""The analyst: evidence in, validated commentary out.

One class tying the pieces together — :mod:`prompts` renders the request,
:mod:`router` gets it answered, :mod:`schemas` decides whether the answer is
usable. Three methods, one per prompt.

**Every method returns ``None`` on any failure** and appends a human-readable
reason to :attr:`Analyst.degradations`. That list is what Phase 3 prints as the
banner at the top of an AI-mode report ("AI narrative unavailable: daily token cap
reached"). The deterministic plan is complete without any of this, so a None here
costs prose and nothing else.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import date

from nepse_trader.ai import prompts
from nepse_trader.ai.budget import iso_week
from nepse_trader.ai.router import BULK, SYNTHESIS, LLMRouter
from nepse_trader.ai.schemas import Critique, SymbolNote, WeeklyThesis, parse_into
from nepse_trader.config import Settings, get_settings
from nepse_trader.rag.evidence import EvidencePack

log = logging.getLogger("nepse_trader.ai.analyst")


class Analyst:
    """LLM commentary over deterministic output. Never a source of numbers."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        settings: Settings | None = None,
        *,
        router: LLMRouter | None = None,
        online: bool | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.router = router or LLMRouter(conn, self.settings, online=online)
        self.degradations: list[str] = []

    # ------------------------------------------------------------------ passes
    def symbol_note(
        self,
        *,
        symbol: str,
        plan: str,
        evidence: EvidencePack | str,
    ) -> SymbolNote | None:
        """Narrative for one symbol. Bulk tier — this runs once per symbol."""
        prompt = prompts.symbol_note_prompt(
            symbol=symbol, plan=plan, evidence=_render(evidence)
        )
        text = self._ask(prompt, task="symbol_note", tier=BULK, label=symbol)
        if text is None:
            return None
        note = parse_into(SymbolNote, text, symbol=symbol)
        if note is None:
            self._degrade(f"{symbol}: model output failed validation")
        return note

    def weekly_thesis(
        self,
        *,
        symbols: list[str],
        market: str,
        evidence: EvidencePack | str,
        week: str | None = None,
        today: date | None = None,
    ) -> WeeklyThesis | None:
        """The expensive weekly pass. Synthesis tier, and the only ``deep`` call.

        Cached by ISO week: the week label is part of the prompt, so a second run
        in the same week is a cache hit and costs nothing.
        """
        label = week or iso_week(today or self.router.budget.today)
        prompt = prompts.weekly_thesis_prompt(
            week=label, market=market, symbols=symbols, evidence=_render(evidence)
        )
        text = self._ask(
            prompt,
            task="weekly_thesis",
            tier=SYNTHESIS,
            label=label,
            deep=True,
            max_tokens=3072,
        )
        if text is None:
            return None
        thesis = parse_into(WeeklyThesis, text, week=label)
        if thesis is None:
            self._degrade(f"weekly thesis for {label}: model output failed validation")
        return thesis

    def critique(self, *, plan: str, evidence: EvidencePack | str) -> Critique | None:
        """Devil's advocate against the deterministic plan. Synthesis tier."""
        prompt = prompts.critique_prompt(plan=plan, evidence=_render(evidence))
        text = self._ask(prompt, task="critique", tier=SYNTHESIS, label="critique")
        if text is None:
            return None
        result = parse_into(Critique, text)
        if result is None:
            self._degrade("critique: model output failed validation")
        return result

    # ----------------------------------------------------------------- banners
    @property
    def degraded(self) -> bool:
        return bool(self.degradations)

    def banner(self) -> str:
        """One line naming why AI output is missing, or empty when it isn't.

        Reasons repeat across twenty-five symbols (the cap is hit once, then every
        call after it), so identical reasons collapse to a count.
        """
        if not self.degradations:
            return ""
        counts: dict[str, int] = {}
        for reason in self.degradations:
            counts[reason] = counts.get(reason, 0) + 1
        parts = [r if n == 1 else f"{r} (x{n})" for r, n in counts.items()]
        return "AI narrative incomplete — " + "; ".join(parts[:4])

    # ----------------------------------------------------------------- helpers
    def _ask(
        self,
        prompt: str,
        *,
        task: str,
        tier: str,
        label: str,
        deep: bool = False,
        max_tokens: int = 2048,
    ) -> str | None:
        response = self.router.complete(
            prompt,
            task=task,
            tier=tier,
            system=prompts.SYSTEM,
            deep=deep,
            max_tokens=max_tokens,
        )
        if not response.ok:
            self._degrade(f"{label}: {response.error or 'no response'}")
            return None
        return response.text

    def _degrade(self, reason: str) -> None:
        log.info("AI pass degraded — %s", reason)
        self.degradations.append(reason)


def _render(evidence: EvidencePack | str) -> str:
    return evidence.render() if isinstance(evidence, EvidencePack) else str(evidence or "")
