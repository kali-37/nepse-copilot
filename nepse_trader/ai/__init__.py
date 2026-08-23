"""The LLM layer: AI mode, bounded and degradable.

Seven modules, each independently testable with no network:

* :mod:`nepse_trader.ai.providers` — Claude CLI subprocess, OpenRouter, Anthropic,
  and a null provider. None of them raise; failures come back as data.
* :mod:`nepse_trader.ai.cache` — content-hash response cache, so re-runs are free.
* :mod:`nepse_trader.ai.budget` — hard per-day and per-week caps with a DB ledger.
* :mod:`nepse_trader.ai.router` — cache, then budget, then the provider chain.
* :mod:`nepse_trader.ai.prompts` — templates as plain strings.
* :mod:`nepse_trader.ai.schemas` — pydantic contracts that reject bad output.
* :mod:`nepse_trader.ai.analyst` — the orchestrator the advisor calls.

The invariant across all of it: **AI mode adds commentary, never numbers.** Every
price, stop, target, size and date comes from the deterministic engine. When a
provider is down, the budget is spent, or the machine is offline, the analyst
returns ``None`` with a reason and the report prints a banner instead of guessing.
"""

from nepse_trader.ai.analyst import Analyst
from nepse_trader.ai.budget import BudgetStatus, BudgetSummary, TokenBudget, iso_week
from nepse_trader.ai.cache import ResponseCache, cache_key
from nepse_trader.ai.providers import (
    AnthropicProvider,
    ClaudeCliProvider,
    LLMProvider,
    LLMResponse,
    NullProvider,
    OpenRouterProvider,
    build_provider,
)
from nepse_trader.ai.router import BULK, SYNTHESIS, TIERS, LLMRouter
from nepse_trader.ai.schemas import Critique, SymbolNote, WeeklyThesis, parse_into

__all__ = [
    "Analyst",
    "LLMRouter",
    "BULK",
    "SYNTHESIS",
    "TIERS",
    "TokenBudget",
    "BudgetStatus",
    "BudgetSummary",
    "iso_week",
    "ResponseCache",
    "cache_key",
    "LLMProvider",
    "LLMResponse",
    "ClaudeCliProvider",
    "OpenRouterProvider",
    "AnthropicProvider",
    "NullProvider",
    "build_provider",
    "SymbolNote",
    "WeeklyThesis",
    "Critique",
    "parse_into",
]
