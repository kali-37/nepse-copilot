"""The router: which provider answers, and what happens when none can.

Two task tiers, each with its own provider chain from settings:

* ``bulk`` — one small pass per symbol. Free OpenRouter models, because there may
  be twenty-five of these and they are summarising numbers that are already
  computed.
* ``synthesis`` — the daily page and the weekly thesis. The local Claude CLI
  first, since it is both the strongest and (running under an existing
  subscription) the cheapest.

:meth:`LLMRouter.complete` is the single entry point and it **never raises**. In
order it tries the cache, checks the budget, then walks the chain; if every leg
fails it returns an :class:`LLMResponse` carrying the reason. Callers above this
layer branch on ``response.ok``, not on exceptions, which is what lets AI mode
degrade to Normal mode with a banner mid-run.

Offline mode is cache-only rather than disabled: a thesis fetched on Sunday is
still readable on a Thursday with no network.
"""

from __future__ import annotations

import logging
import sqlite3

from nepse_trader.ai.budget import BudgetStatus, TokenBudget
from nepse_trader.ai.cache import ResponseCache
from nepse_trader.ai.providers import (
    LLMProvider,
    LLMResponse,
    build_provider,
    estimate_tokens,
)
from nepse_trader.config import Settings, get_settings

log = logging.getLogger("nepse_trader.ai.router")

BULK = "bulk"
SYNTHESIS = "synthesis"
TIERS = (BULK, SYNTHESIS)


class LLMRouter:
    """Cache → budget → provider chain, with graceful failure at every step."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        settings: Settings | None = None,
        *,
        providers: dict[str, LLMProvider] | None = None,
        budget: TokenBudget | None = None,
        cache: ResponseCache | None = None,
        online: bool | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.budget = budget or TokenBudget(conn, self.settings)
        self.cache = cache or ResponseCache(conn, self.settings)
        # Explicit `online` wins over the setting, so a resolved `--offline` flag
        # is not second-guessed here.
        self.online = self.settings.online if online is None else online
        # Instances are built lazily and reused; tests inject a ready dict.
        self._provided = providers
        self._built: dict[str, LLMProvider] = dict(providers) if providers else {}

    # ------------------------------------------------------------------ chains
    def chain(self, tier: str) -> list[str]:
        """Provider names to try, in order, for *tier*."""
        if tier == SYNTHESIS:
            names = self.settings.llm_synthesis_providers
        elif tier == BULK:
            names = self.settings.llm_bulk_providers
        else:
            raise ValueError(f"unknown tier {tier!r}; known: {', '.join(TIERS)}")
        # De-duplicated, order preserved: a name repeated in .env is a typo, not
        # an instruction to retry the same provider twice.
        seen: set[str] = set()
        return [n for n in (x.strip() for x in names) if n and not (n in seen or seen.add(n))]

    def provider(self, name: str) -> LLMProvider | None:
        """A cached provider instance, or None if the name is unknown."""
        if name in self._built:
            return self._built[name]
        if self._provided is not None:
            return None  # an injected set is authoritative — never build behind it
        try:
            instance = build_provider(name, self.settings)
        except ValueError as exc:
            log.warning("%s", exc)
            return None
        self._built[name] = instance
        return instance

    def available(self, tier: str) -> list[LLMProvider]:
        """The legs of *tier*'s chain that are configured well enough to try."""
        out = []
        for name in self.chain(tier):
            provider = self.provider(name)
            if provider is not None and provider.available:
                out.append(provider)
        return out

    # ---------------------------------------------------------------- the call
    def complete(
        self,
        prompt: str,
        *,
        task: str,
        tier: str = BULK,
        system: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.2,
        deep: bool = False,
        use_cache: bool = True,
    ) -> LLMResponse:
        """Best available answer to *prompt*, or a response explaining the gap.

        ``task`` labels the call in the cache and the ledger — keep it stable
        across runs (``"symbol_note"``, ``"weekly_thesis"``) so caching works.
        ``deep`` marks the expensive weekly pass and counts against its own cap.
        """
        key = self.cache.key(task=task, prompt=prompt, system=system or "")

        if use_cache:
            hit = self.cache.get(key)
            if hit is not None:
                self.budget.record(hit, task=task, deep=deep)
                log.debug("cache hit for %s", task)
                return hit

        if not self.online:
            return self._degraded(task, "offline: no cached answer for this request", deep=deep)

        status = self._gate(prompt, system, deep=deep)
        if not status.allowed:
            return self._degraded(task, f"budget: {status.reason}", deep=deep)

        providers = self.available(tier)
        if not providers:
            configured = ", ".join(self.chain(tier)) or "(none)"
            return self._degraded(
                task, f"no configured provider for {tier} (chain: {configured})", deep=deep
            )

        problems: list[str] = []
        for provider in providers:
            try:
                response = provider.complete(
                    prompt, system=system, max_tokens=max_tokens, temperature=temperature
                )
            except Exception as exc:  # noqa: BLE001 - a raising leg must not abort the run
                # The shipped providers turn their own failures into data, but that is a
                # convention, not a guarantee. Enforcing it here is what lets everything
                # above this layer branch on `.ok` and never wrap a call in try/except.
                response = LLMResponse(error=f"raised {type(exc).__name__}: {exc}")
            self.budget.record(response, task=task, deep=deep)
            if response.ok:
                self.cache.put(key, response, task=task)
                return response
            problems.append(f"{provider.name}: {response.error or 'no text'}")
            log.warning("%s failed for %s: %s", provider.name, task, response.error)

        return LLMResponse(error="; ".join(problems))

    def status(self) -> dict:
        """Everything ``ai models`` prints: chains, availability, caps, cache."""
        tiers = {}
        for tier in TIERS:
            legs = []
            for name in self.chain(tier):
                provider = self.provider(name)
                legs.append(
                    {
                        "name": name,
                        "known": provider is not None,
                        "available": bool(provider and provider.available),
                        "model": provider.model if provider else "",
                    }
                )
            tiers[tier] = legs
        return {
            "online": self.online,
            "tiers": tiers,
            "budget": self.budget.summary().as_dict(),
            "cache": self.cache.stats(),
        }

    # ----------------------------------------------------------------- helpers
    def _gate(self, prompt: str, system: str | None, *, deep: bool) -> BudgetStatus:
        estimated = estimate_tokens(prompt) + estimate_tokens(system or "")
        return self.budget.check(deep=deep, estimated_tokens=estimated)

    def _degraded(self, task: str, reason: str, *, deep: bool) -> LLMResponse:
        """A refusal, logged in the ledger so the reason survives the run."""
        response = LLMResponse(error=reason)
        self.budget.record(response, task=task, deep=deep)
        log.info("LLM call for %s declined — %s", task, reason)
        return response
