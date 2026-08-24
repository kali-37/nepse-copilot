"""The MCP server: a declarative tool registry plus the stdio loop.

An MCP client (Claude Desktop, Claude Code) spawns this as a subprocess and talks
newline-delimited JSON-RPC over its stdin/stdout. What it gets is read access to
whatever the local pipeline has already collected — symbols, reconciled price
history, breadth, movers, signals, quant summaries and the RAG document corpus.

Three design choices worth explaining:

**Every tool is read-only, by construction.** No tool writes a paper trade,
applies for an IPO, or triggers an ingest. The caller on the other end is a model
choosing tools from descriptions, so the cost of a misread description has to be
"a useless answer", never "an order was placed". Note that the pipeline is built
with ``clients=[]``: no source client is even constructed, so there is no code
path from here to the network or to a market-data write.

**stdout carries protocol frames and nothing else.** A single stray ``print()``
anywhere in the imported dependency tree desynchronises the client's parser and
the session dies with an opaque error. :func:`serve_stdio` therefore keeps a
private handle on the real stdout and rebinds ``sys.stdout`` to stderr for the
duration of the loop, so stray output is merely visible instead of fatal. The
project logger is left unconfigured, which means Python's last-resort handler
sends log records to stderr.

**A tool that raises is a successful call with ``isError: true``.** The model can
read "unknown symbol FOO" out of a content block and retry; it cannot do anything
with a JSON-RPC error, and it certainly cannot recover from the server process
exiting. Only genuinely protocol-level problems (unknown method, missing tool
name) use the ``error`` member.

The registry is a list of :class:`ToolSpec` records rather than a dispatch chain,
because ``tools/list`` has to render the same data that ``tools/call`` routes on —
two if/elif chains that must agree is a bug waiting to happen.
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any, TextIO

from nepse_trader.advisor import (
    DOSE_HORIZONS,
    build_rashifal,
    confidence_for_prediction,
    latest_dose_run,
    save_rashifal,
)
from nepse_trader.ai import Analyst
from nepse_trader.analysis.backtest import Backtester
from nepse_trader.analysis.screen import RANKABLE
from nepse_trader.analysis.strategies import build_strategy
from nepse_trader.config import Settings, get_settings
from nepse_trader.health import problems, system_health
from nepse_trader.mcp_server.protocol import (
    INVALID_PARAMS,
    Dispatcher,
    RpcError,
)
from nepse_trader.meroshare import (
    MeroShareError,
    compare_with_paper,
    comparison_summary,
    stored_holdings,
    sync_status,
)
from nepse_trader.pipeline import DailyPipeline
from nepse_trader.rag.corpus import ALL_KINDS
from nepse_trader.rag.evidence import build_evidence
from nepse_trader.rag.index import DocumentIndex
from nepse_trader.rag.retrievers import build_retriever
from nepse_trader.storage import Storage

log = logging.getLogger("nepse_trader.mcp_server")

SERVER_NAME = "nepse-trader"
SERVER_VERSION = "0.1.0"

# Protocol revisions we can speak. We echo the client's requested revision when
# it is one of these, so a client pinned to an older spec still works; otherwise
# we answer with our newest and let the client decide.
SUPPORTED_PROTOCOL_VERSIONS = ("2024-11-05", "2025-03-26", "2025-06-18")
DEFAULT_PROTOCOL_VERSION = SUPPORTED_PROTOCOL_VERSIONS[-1]

# Document bodies are prose facts and normally short, but a scraped web document
# can run to thousands of characters. Cap them so one search cannot swallow the
# client's context window.
MAX_DOCUMENT_BODY_CHARS = 1_000
MAX_SCREEN_SYMBOLS = 300
MAX_SCREEN_ROWS = 100
MAX_BACKTEST_TRADES = 100

# Every tool result crosses into a model's context window, so each list-returning
# tool needs a ceiling that does not depend on how large the local database grew.
# Where a result is truncated rather than rejected the payload says so, because a
# silently shortened list reads as "that is all there is".
MAX_SYMBOLS_LISTED = 1_000
MAX_PRICE_BARS = 2_000
MAX_TOP_MOVERS = 50
MAX_SIGNAL_SYMBOLS = 300
MAX_QUANT_SYMBOLS = 100
MAX_SEARCH_RESULTS = 50
MAX_PORTFOLIO_DIFFS = 200
MAX_MEROSHARE_HOLDINGS = 500

STRATEGY_NAMES = (
    "sma_cross",
    "rsi",
    "macd",
    "bollinger",
    "supertrend",
    "ichimoku",
    "donchian",
    "mean_reversion",
)


@dataclass(frozen=True)
class ToolSpec:
    """One MCP tool: what the model sees, and what runs when it is called.

    ``description`` is prompt text, not documentation — it is the only thing a
    model has to decide between this tool and eight others, so it states what
    comes back and when *not* to reach for it.
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], Any]

    def as_wire(self) -> dict[str, Any]:
        """The ``tools/list`` representation (handler is not serialisable)."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


@dataclass
class ToolResult:
    """A ``tools/call`` result in MCP content-block form."""

    text: str
    is_error: bool = False

    def as_wire(self) -> dict[str, Any]:
        return {
            "content": [{"type": "text", "text": self.text}],
            "isError": self.is_error,
        }


# --------------------------------------------------------------------------- #
# Argument coercion. Raising ValueError here is deliberate: tool_call turns any
# exception into an isError content block the model can read and correct.
# --------------------------------------------------------------------------- #


def _require_str(args: dict[str, Any], key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"'{key}' is required and must be a non-empty string")
    return value.strip()


def _optional_date(args: dict[str, Any], key: str) -> date | None:
    value = args.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"'{key}' must be an ISO date string (YYYY-MM-DD)")
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError(f"'{key}' is not a valid ISO date (YYYY-MM-DD): {value!r}") from exc


def _optional_int(
    args: dict[str, Any],
    key: str,
    default: int,
    *,
    minimum: int = 1,
    maximum: int | None = None,
) -> int:
    value = args.get(key)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"'{key}' must be an integer")
    if value < minimum:
        raise ValueError(f"'{key}' must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"'{key}' must be <= {maximum}")
    return value


def _optional_number(
    args: dict[str, Any],
    key: str,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    value = args.get(key)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"'{key}' must be a number")
    number = float(value)
    if minimum is not None and number < minimum:
        raise ValueError(f"'{key}' must be >= {minimum}")
    if maximum is not None and number > maximum:
        raise ValueError(f"'{key}' must be <= {maximum}")
    return number


def _optional_bool(args: dict[str, Any], key: str, default: bool) -> bool:
    value = args.get(key)
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ValueError(f"'{key}' must be a boolean")
    return value


def _optional_choice(
    args: dict[str, Any], key: str, default: str, choices: tuple[str, ...]
) -> str:
    value = args.get(key, default)
    if not isinstance(value, str) or value not in choices:
        raise ValueError(f"'{key}' must be one of: {', '.join(choices)}")
    return value


def _optional_str_list(args: dict[str, Any], key: str) -> list[str] | None:
    value = args.get(key)
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError(f"'{key}' must be an array of strings")
    cleaned = [v.strip() for v in value if v.strip()]
    return cleaned or None


def _json_text(payload: Any) -> str:
    """Render a result as indented JSON. ``default=str`` covers date/Decimal."""
    return json.dumps(payload, indent=2, default=str, ensure_ascii=False)


class MCPServer:
    """Holds the DB handles, owns the tool registry, wires up the dispatcher."""

    def __init__(
        self,
        settings: Settings | None = None,
        storage: Storage | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.storage = storage or Storage(self.settings.db_path)
        # clients=[] is the read-only guarantee in code: with no source clients
        # there is nothing for ingest() to call even if something reached it.
        self.pipeline = DailyPipeline(
            settings=self.settings, storage=self.storage, clients=[]
        )
        self.tools: list[ToolSpec] = self._build_tools()
        self._tools_by_name = {t.name: t for t in self.tools}
        self.dispatcher = self._build_dispatcher()

    # ------------------------------------------------------------- protocol
    def _build_dispatcher(self) -> Dispatcher:
        d = Dispatcher()
        d.register("initialize", self.initialize)
        d.register("notifications/initialized", self._noop)
        d.register("notifications/cancelled", self._noop)
        d.register("ping", self.ping)
        d.register("tools/list", self.tools_list)
        d.register("tools/call", self.tools_call)
        return d

    def initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        requested = params.get("protocolVersion")
        version = (
            requested
            if isinstance(requested, str) and requested in SUPPORTED_PROTOCOL_VERSIONS
            else DEFAULT_PROTOCOL_VERSION
        )
        return {
            "protocolVersion": version,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        }

    def _noop(self, params: dict[str, Any]) -> None:
        """Handler for notifications we accept and ignore."""
        return None

    def ping(self, params: dict[str, Any]) -> dict[str, Any]:
        return {}

    def tools_list(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"tools": [t.as_wire() for t in self.tools]}

    def tools_call(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        if not isinstance(name, str) or not name:
            raise RpcError(INVALID_PARAMS, "Invalid params: 'name' must be a tool name string")
        spec = self._tools_by_name.get(name)
        if spec is None:
            known = ", ".join(sorted(self._tools_by_name))
            raise RpcError(INVALID_PARAMS, f"Unknown tool {name!r}. Available tools: {known}")

        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            raise RpcError(INVALID_PARAMS, "Invalid params: 'arguments' must be an object")

        try:
            payload = spec.handler(arguments)
        except (ValueError, MeroShareError) as exc:
            # Tool failure is data, not a transport fault: the model reads the
            # message and retries. The loop must survive to serve the next call.
            log.warning("tool %s rejected the call: %s", name, type(exc).__name__)
            return ToolResult(f"{type(exc).__name__}: {exc}", is_error=True).as_wire()
        except Exception as exc:  # noqa: BLE001 - a tool must never end the server
            # Unexpected exception text is untrusted. A remote body or a client
            # exception can contain credentials, cookies or tokens, so only the
            # exception class crosses either the log or the MCP boundary.
            log.warning("tool %s failed safely: %s", name, type(exc).__name__)
            return ToolResult(
                f"{type(exc).__name__}: tool failed; sensitive details withheld",
                is_error=True,
            ).as_wire()

        text = payload if isinstance(payload, str) else _json_text(payload)
        return ToolResult(text).as_wire()

    # ---------------------------------------------------------------- tools
    def _build_tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="list_symbols",
                description=(
                    "List every NEPSE stock symbol that has price data in the local database. "
                    "Call this first when the user names a company loosely or you need to know "
                    "what coverage exists — every other tool takes symbols from this list. "
                    "Optionally filter to symbols containing a substring."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "contains": {
                            "type": "string",
                            "description": "Case-insensitive substring filter, e.g. 'BANK'.",
                        }
                    },
                    "additionalProperties": False,
                },
                handler=self._tool_list_symbols,
            ),
            ToolSpec(
                name="price_history",
                description=(
                    "Reconciled daily OHLCV history for one symbol, oldest first. Each row is "
                    "the cross-source consensus close with a confidence score (1.0 = all "
                    "sources agreed; below 0.7 means the sources disputed a field, so treat "
                    "the numbers as soft). Use this for 'how has X moved', charting, or "
                    "checking a specific day's close."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": "Stock symbol, e.g. 'NABIL'. Case-insensitive.",
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": MAX_PRICE_BARS,
                            "default": 60,
                            "description": "Return only the most recent N trading days.",
                        },
                    },
                    "required": ["symbol"],
                    "additionalProperties": False,
                },
                handler=self._tool_price_history,
            ),
            ToolSpec(
                name="market_breadth",
                description=(
                    "Whole-market summary for one trading day: advancers, decliners, unchanged, "
                    "total turnover, and the average reconciliation confidence. Use this to "
                    "answer 'how was the market today' before drilling into individual stocks. "
                    "Defaults to the most recent reconciled date in the database."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "business_date": {
                            "type": "string",
                            "description": (
                                "Trading day as YYYY-MM-DD. Omit for the latest available day."
                            ),
                        }
                    },
                    "additionalProperties": False,
                },
                handler=self._tool_market_breadth,
            ),
            ToolSpec(
                name="top_movers",
                description=(
                    "Biggest gainers and losers by percentage change for one trading day, "
                    "computed from reconciled closes against previous close. Returns two lists. "
                    "Defaults to the most recent reconciled date."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "business_date": {
                            "type": "string",
                            "description": (
                                "Trading day as YYYY-MM-DD. Omit for the latest available day."
                            ),
                        },
                        "top": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": MAX_TOP_MOVERS,
                            "default": 5,
                            "description": "How many names per side.",
                        },
                    },
                    "additionalProperties": False,
                },
                handler=self._tool_top_movers,
            ),
            ToolSpec(
                name="latest_signals",
                description=(
                    "Most recent technical BUY/SELL/HOLD signal per symbol from one strategy, "
                    "with the indicator values behind it. These are backtest-grade mechanical "
                    "signals, not advice, and 'strength' is the strategy's own confidence, not "
                    "a probability. Restrict 'symbols' when asking about specific names: with "
                    "no filter this recomputes signals across the whole database and is slow."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "symbols": {
                            "type": "array",
                            "items": {"type": "string"},
                            "maxItems": MAX_SIGNAL_SYMBOLS,
                            "description": "Symbols to evaluate. Omit for every symbol (slow).",
                        },
                        "strategy": {
                            "type": "string",
                            "enum": list(STRATEGY_NAMES),
                            "default": "sma_cross",
                            "description": "Which strategy to run.",
                        },
                    },
                    "additionalProperties": False,
                },
                handler=self._tool_latest_signals,
            ),
            ToolSpec(
                name="quant_stats",
                description=(
                    "Risk and return statistics over each symbol's full reconciled close "
                    "history: total and annualised return, annualised volatility, Sharpe, "
                    "Sortino, max drawdown, skew, kurtosis and 95% VaR. Use this to compare "
                    "candidates or to answer 'how risky is X'. Symbols are required."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "symbols": {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 1,
                            "maxItems": MAX_QUANT_SYMBOLS,
                            "description": "Symbols to summarise, e.g. ['NABIL', 'NICA'].",
                        }
                    },
                    "required": ["symbols"],
                    "additionalProperties": False,
                },
                handler=self._tool_quant_stats,
            ),
            ToolSpec(
                name="search_documents",
                description=(
                    "Full-text search over the local NEPSE document corpus — one short prose "
                    "document per fact, covering prices, indicators, quant summaries, signals, "
                    "data-quality notes, fundamentals, corporate actions, news and saved "
                    "reports. This is the tool for open-ended questions ('any news on NABIL', "
                    "'which stocks had disputed data') where you do not know which structured "
                    "tool applies. Returns nothing if the corpus has not been indexed yet. "
                    "Local only; never hits the network."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": (
                                "Free-text query. Empty query plus filters lists the most "
                                "recent matching documents."
                            ),
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": MAX_SEARCH_RESULTS,
                            "default": 8,
                            "description": "Maximum documents to return.",
                        },
                        "symbols": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Restrict to these symbols.",
                        },
                        "kinds": {
                            "type": "array",
                            "items": {"type": "string", "enum": list(ALL_KINDS)},
                            "description": "Restrict to these document kinds.",
                        },
                        "since": {
                            "type": "string",
                            "description": "Only documents dated on or after this YYYY-MM-DD.",
                        },
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
                handler=self._tool_search_documents,
            ),
            ToolSpec(
                name="database_stats",
                description=(
                    "Health and coverage report for the local database: row counts per table, "
                    "date range covered, how many sources contributed, latest reconciled date "
                    "and its average confidence, and how many symbols were disputed. Call this "
                    "when a query returns nothing, to tell 'no such stock' apart from 'the "
                    "database has not been populated for that period'."
                ),
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                handler=self._tool_database_stats,
            ),
            ToolSpec(
                name="system_health",
                description=(
                    "Whole-system health report: schema migrations applied, how many trading "
                    "days behind the newest reconciled close is, recent ingest error rate, "
                    "which sources are effectively enabled, document-corpus size, LLM budget "
                    "left, MeroShare mirror state and prediction-journal backlog. Each check "
                    "returns ok/warn/fail/off with a one-sentence explanation. Call this before "
                    "concluding that a number is wrong — a stale database and a bad calculation "
                    "look identical from a single query. Read-only: nothing is fetched, spent, "
                    "or written. Contains no credential and no account identifier."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "problems_only": {
                            "type": "boolean",
                            "description": "Return only the warn/fail checks. Default false.",
                        },
                    },
                    "additionalProperties": False,
                },
                handler=self._tool_system_health,
            ),
            ToolSpec(
                name="backtest",
                description=(
                    "Run one local, historical strategy backtest for a symbol with Nepal "
                    "broker commission, SEBON fee, DP charge and CGT included. It never "
                    "places an order and never reaches the network. Returns headline metrics "
                    "plus at most the latest 100 simulated trades."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string", "description": "NEPSE symbol."},
                        "strategy": {
                            "type": "string",
                            "enum": list(STRATEGY_NAMES),
                            "default": "sma_cross",
                        },
                        "cash": {
                            "type": "number",
                            "exclusiveMinimum": 0,
                            "default": 100000,
                        },
                        "fraction": {
                            "type": "number",
                            "exclusiveMinimum": 0,
                            "maximum": 1,
                            "default": 1,
                        },
                    },
                    "required": ["symbol"],
                    "additionalProperties": False,
                },
                handler=self._tool_backtest,
            ),
            ToolSpec(
                name="screen",
                description=(
                    "Backtest a bounded local symbol/strategy panel and return a ranked "
                    "leaderboard net of Nepal costs. Omit symbols to use locally stored "
                    "symbols, capped at 300; output is capped at 100 rows. No network or "
                    "market action is possible."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "symbols": {"type": "array", "items": {"type": "string"}},
                        "strategies": {
                            "type": "array",
                            "items": {"type": "string", "enum": list(STRATEGY_NAMES)},
                        },
                        "cash": {
                            "type": "number",
                            "exclusiveMinimum": 0,
                            "default": 100000,
                        },
                        "min_bars": {"type": "integer", "minimum": 2, "default": 60},
                        "rank_by": {
                            "type": "string",
                            "enum": list(RANKABLE),
                            "default": "sharpe",
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": MAX_SCREEN_ROWS,
                            "default": 30,
                        },
                    },
                    "additionalProperties": False,
                },
                handler=self._tool_screen,
            ),
            ToolSpec(
                name="portfolio",
                description=(
                    "Read the local paper portfolio, mark it to the latest reconciled closes, "
                    "and compare it with the last stored MeroShare mirror. This is reporting "
                    "only: it cannot buy, sell, sync, log in or alter either portfolio."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "initial_cash": {
                            "type": "number",
                            "exclusiveMinimum": 0,
                            "default": 100000,
                        },
                        "include_meroshare": {"type": "boolean", "default": True},
                    },
                    "additionalProperties": False,
                },
                handler=self._tool_portfolio,
            ),
            ToolSpec(
                name="meroshare_holdings",
                description=(
                    "Return only the last locally stored read-only MeroShare holdings and sync "
                    "status. This tool never logs in, never contacts CDSC, and has no IPO, "
                    "ASBA, order or bid capability. Account identifiers are masked."
                ),
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                handler=self._tool_meroshare_holdings,
            ),
            ToolSpec(
                name="rashifal",
                description=(
                    "Generate and locally journal the deterministic NEPSE trade prescription: "
                    "entry zone, stop, targets, quantity, T+2 earliest sell date, net outcome, "
                    "and all four day/week/month/year doses. Normal mode is fully offline; AI "
                    "mode adds prose only and visibly degrades when unavailable. Nothing here "
                    "places an order or bid; execution remains manual."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "symbols": {"type": "array", "items": {"type": "string"}},
                        "mode": {
                            "type": "string",
                            "enum": ["normal", "ai"],
                            "default": "normal",
                        },
                        "online": {
                            "type": "boolean",
                            "default": False,
                            "description": "Explicit opt-in to live retrieval/providers in AI mode.",
                        },
                        "horizon": {
                            "type": "string",
                            "enum": list(DOSE_HORIZONS),
                            "default": "week",
                        },
                        "equity": {
                            "type": "number",
                            "exclusiveMinimum": 0,
                            "default": 100000,
                        },
                    },
                    "additionalProperties": False,
                },
                handler=self._tool_rashifal,
            ),
            ToolSpec(
                name="doses",
                description=(
                    "Return the latest persisted four-horizon investment prescription. Cards "
                    "are partitioned exactly once across day, week, month and year, so the "
                    "headline expected outcome cannot double-count capital. Call rashifal first "
                    "when no dose run exists."
                ),
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                handler=self._tool_doses,
            ),
        ]

    # ------------------------------------------------------- tool handlers
    def _tool_list_symbols(self, args: dict[str, Any]) -> dict[str, Any]:
        symbols = self.storage.symbols()
        contains = args.get("contains")
        if contains:
            if not isinstance(contains, str):
                raise ValueError("'contains' must be a string")
            needle = contains.strip().upper()
            symbols = [s for s in symbols if needle in s]
        window = symbols[:MAX_SYMBOLS_LISTED]
        return {
            "count": len(symbols),
            "returned": len(window),
            "truncated": len(symbols) > len(window),
            "symbols": window,
        }

    def _tool_price_history(self, args: dict[str, Any]) -> dict[str, Any]:
        symbol = _require_str(args, "symbol").upper()
        limit = _optional_int(args, "limit", 60, maximum=MAX_PRICE_BARS)
        rows = self.storage.reconciled_history(symbol)
        if not rows:
            raise ValueError(
                f"No reconciled price history for {symbol!r}. "
                "Use list_symbols to see what is available."
            )
        window = rows[-limit:]
        return {
            "symbol": symbol,
            "total_rows": len(rows),
            "returned": len(window),
            "bars": [r.model_dump(mode="json") for r in window],
        }

    def _tool_market_breadth(self, args: dict[str, Any]) -> dict[str, Any]:
        business_date = _optional_date(args, "business_date") or self._latest_date()
        return self.pipeline.market_breadth(business_date)

    def _tool_top_movers(self, args: dict[str, Any]) -> dict[str, Any]:
        business_date = _optional_date(args, "business_date") or self._latest_date()
        top = _optional_int(args, "top", 5, maximum=MAX_TOP_MOVERS)
        gainers, losers = self.pipeline.top_movers(business_date, top=top)
        return {
            "business_date": business_date.isoformat(),
            "gainers": gainers,
            "losers": losers,
        }

    def _tool_latest_signals(self, args: dict[str, Any]) -> dict[str, Any]:
        symbols = _optional_str_list(args, "symbols")
        if symbols:
            symbols = [s.upper() for s in symbols]
        strategy = args.get("strategy") or "sma_cross"
        if strategy not in STRATEGY_NAMES:
            raise ValueError(
                f"Unknown strategy {strategy!r}. Known: {', '.join(STRATEGY_NAMES)}"
            )
        signals = self.pipeline.latest_signals(symbols=symbols, strategy=strategy)
        window = signals[:MAX_SIGNAL_SYMBOLS]
        return {
            "strategy": strategy,
            "count": len(signals),
            "returned": len(window),
            "truncated": len(signals) > len(window),
            "signals": [s.model_dump(mode="json") for s in window],
        }

    def _tool_quant_stats(self, args: dict[str, Any]) -> dict[str, Any]:
        symbols = _optional_str_list(args, "symbols")
        if not symbols:
            raise ValueError("'symbols' is required and must contain at least one symbol")
        if len(symbols) > MAX_QUANT_SYMBOLS:
            raise ValueError(f"'symbols' must contain at most {MAX_QUANT_SYMBOLS} symbols")
        rows = self.pipeline.quant_stats([s.upper() for s in symbols])
        return {"count": len(rows), "stats": rows}

    def _tool_search_documents(self, args: dict[str, Any]) -> dict[str, Any]:
        query = args.get("query")
        if not isinstance(query, str):
            raise ValueError("'query' is required and must be a string")
        limit = _optional_int(args, "limit", 8, maximum=MAX_SEARCH_RESULTS)
        symbols = _optional_str_list(args, "symbols")
        kinds = _optional_str_list(args, "kinds")
        since = _optional_date(args, "since")

        index = DocumentIndex(self.storage._conn)
        hits = index.search(query, limit=limit, symbols=symbols, kinds=kinds, since=since)
        return {
            "query": query,
            "count": len(hits),
            "uses_fts": index.uses_fts,
            "results": [_hit_to_dict(h) for h in hits],
        }

    def _tool_database_stats(self, args: dict[str, Any]) -> dict[str, Any]:
        return self.storage.db_stats()

    def _tool_system_health(self, args: dict[str, Any]) -> dict[str, Any]:
        report = system_health(self.storage, self.settings)
        if _optional_bool(args, "problems_only", False):
            checks = problems(report)
            return {**report, "checks": checks, "problems_only": True}
        return report

    def _tool_backtest(self, args: dict[str, Any]) -> dict[str, Any]:
        symbol = _require_str(args, "symbol").upper()
        strategy_name = _optional_choice(args, "strategy", "sma_cross", STRATEGY_NAMES)
        cash = _optional_number(args, "cash", 100_000.0, minimum=0.01)
        fraction = _optional_number(args, "fraction", 1.0, minimum=0.0001, maximum=1.0)
        bars = self.pipeline.reconciled_bars(symbol)
        if len(bars) < 2:
            raise ValueError(
                f"Not enough reconciled history for {symbol!r}; need at least two bars"
            )
        result = Backtester(
            cost_engine=self.pipeline.cost_engine,
            initial_cash=cash,
            position_fraction=fraction,
        ).run(build_strategy(strategy_name), bars)
        return {
            "symbol": symbol,
            "bars": len(bars),
            "summary": result.summary(),
            "trades": result.trades[-MAX_BACKTEST_TRADES:],
            "trades_truncated": len(result.trades) > MAX_BACKTEST_TRADES,
        }

    def _tool_screen(self, args: dict[str, Any]) -> dict[str, Any]:
        requested = _optional_str_list(args, "symbols")
        available = self.storage.symbols()
        symbols = _normalise_symbols(requested or available)[:MAX_SCREEN_SYMBOLS]
        strategies = _optional_str_list(args, "strategies")
        if strategies:
            unknown = sorted(set(strategies) - set(STRATEGY_NAMES))
            if unknown:
                raise ValueError(
                    "Unknown strategies: " + ", ".join(unknown)
                    + f". Known: {', '.join(STRATEGY_NAMES)}"
                )
        cash = _optional_number(args, "cash", 100_000.0, minimum=0.01)
        min_bars = _optional_int(args, "min_bars", 60, minimum=2)
        rank_by = _optional_choice(args, "rank_by", "sharpe", tuple(RANKABLE))
        limit = _optional_int(args, "limit", 30, maximum=MAX_SCREEN_ROWS)
        rows = self.pipeline.screen_strategies(
            symbols=symbols,
            strategy_names=strategies,
            cash=cash,
            min_bars=min_bars,
            rank_by=rank_by,
        )
        return {
            "rank_by": rank_by,
            "symbols_evaluated": len(symbols),
            "symbols_available": len(available),
            "total_rows": len(rows),
            "returned": min(len(rows), limit),
            "rows": [row.as_dict() for row in rows[:limit]],
        }

    def _tool_portfolio(self, args: dict[str, Any]) -> dict[str, Any]:
        initial_cash = _optional_number(
            args, "initial_cash", 100_000.0, minimum=0.01
        )
        include_meroshare = _optional_bool(args, "include_meroshare", True)
        portfolio = self.pipeline.replay_portfolio(initial_cash)
        prices: dict[str, float] = {}
        for position in portfolio.holdings():
            history = self.storage.reconciled_history(position.symbol)
            if history and history[-1].close is not None:
                prices[position.symbol] = float(history[-1].close)

        payload = portfolio.to_dict()
        payload.update(
            {
                "prices": prices,
                "market_value": float(portfolio.market_value(prices)),
                "equity": float(portfolio.equity(prices)),
                "unrealized_pnl": float(portfolio.unrealized_pnl(prices)),
            }
        )
        result: dict[str, Any] = {"paper": payload}
        if include_meroshare:
            holdings = stored_holdings(self.storage._conn)
            diffs = compare_with_paper(holdings, portfolio.holdings())
            window = diffs[:MAX_PORTFOLIO_DIFFS]
            result["meroshare"] = {
                "status": sync_status(self.storage._conn),
                "comparison": comparison_summary(diffs),
                "differences": [d.model_dump(mode="json") for d in window],
                "differences_truncated": len(diffs) > len(window),
            }
        return result

    def _tool_meroshare_holdings(self, args: dict[str, Any]) -> dict[str, Any]:
        holdings = stored_holdings(self.storage._conn)
        window = holdings[:MAX_MEROSHARE_HOLDINGS]
        return {
            "status": sync_status(self.storage._conn),
            "count": len(holdings),
            "returned": len(window),
            "truncated": len(holdings) > len(window),
            "holdings": [_holding_to_dict(h) for h in window],
            "source": "local mirror only; no CDSC request was made",
        }

    def _tool_rashifal(self, args: dict[str, Any]) -> dict[str, Any]:
        mode = _optional_choice(args, "mode", "normal", ("normal", "ai"))
        online = _optional_bool(args, "online", False)
        horizon = _optional_choice(args, "horizon", "week", tuple(DOSE_HORIZONS))
        equity = _optional_number(args, "equity", 100_000.0, minimum=0.01)
        requested = _optional_str_list(args, "symbols")
        symbols = _normalise_symbols(
            requested or self.settings.watchlist or self.storage.symbols()
        )[: max(1, self.settings.advisor_max_symbols)]
        if not symbols:
            raise ValueError("No symbols are available; ingest and reconcile data first")

        run_date = self._latest_date()
        breadth = self.pipeline.market_breadth(run_date)
        positions = {
            p.symbol: p.quantity for p in self.pipeline.replay_portfolio(equity).holdings()
        }
        analyst = Analyst(
            self.storage._conn,
            self.settings,
            online=online,
        ) if mode == "ai" else None
        evidence_for = self._advisor_evidence(online) if mode == "ai" else None

        result = build_rashifal(
            symbols=symbols,
            bars_for=self.pipeline.reconciled_bars,
            signals_for=self._latest_strategy_panel,
            equity=equity,
            run_date=run_date,
            mode=mode,
            horizon=horizon,
            online=online,
            breadth=breadth,
            positions=positions,
            analyst=analyst,
            evidence_for=evidence_for,
            cost_engine=self.pipeline.cost_engine,
            confidence_for=self._journal_confidence,
            max_symbols=self.settings.advisor_max_symbols,
        )
        save_rashifal(self.storage._conn, result)
        return result.as_dict()

    def _tool_doses(self, args: dict[str, Any]) -> dict[str, Any]:
        result = latest_dose_run(self.storage._conn)
        if result is None:
            raise ValueError("No dose prescription exists yet; call rashifal first")
        return result

    def _latest_strategy_panel(self, symbol: str) -> list[Any]:
        """One current vote per strategy, without persisting generated signals."""
        bars = self.pipeline.reconciled_bars(symbol)
        panel: list[Any] = []
        for name in STRATEGY_NAMES:
            generated = build_strategy(name).generate(bars)
            if generated:
                panel.append(generated[-1])
        return panel

    def _journal_confidence(self, **context: Any) -> Any:
        horizon_days = int(context.get("horizon_days") or 0)
        horizon = next(
            (name for name, days in DOSE_HORIZONS.items() if days == horizon_days),
            "",
        )
        return confidence_for_prediction(
            self.storage._conn,
            symbol=str(context.get("symbol") or ""),
            action=str(context.get("action") or ""),
            horizon=horizon,
            horizon_days=horizon_days,
        )

    def _advisor_evidence(self, online: bool) -> Callable[[str], str]:
        index = DocumentIndex(self.storage._conn)
        retriever = build_retriever(index, self.settings, online=online)

        def evidence_for(symbol: str) -> str:
            query = symbol or "market breadth regime"
            hits = retriever.retrieve(
                query,
                limit=self.settings.rag_max_documents,
                symbols=[symbol] if symbol else None,
            )
            return build_evidence(
                hits,
                query=query,
                max_documents=self.settings.rag_max_documents,
                max_chars=self.settings.rag_max_evidence_chars,
            ).render()

        return evidence_for

    # ---------------------------------------------------------------- utils
    def _latest_date(self) -> date:
        latest = self.storage.latest_reconciled_date()
        if latest is None:
            raise ValueError(
                "The database holds no reconciled prices yet, so there is no latest trading "
                "day. Run database_stats to confirm coverage."
            )
        return latest


def _hit_to_dict(hit: Any) -> dict[str, Any]:
    doc = hit.document
    body = doc.body or ""
    truncated = len(body) > MAX_DOCUMENT_BODY_CHARS
    return {
        "doc_id": doc.doc_id,
        "kind": doc.kind,
        "symbol": doc.symbol,
        "business_date": doc.business_date.isoformat() if doc.business_date else None,
        "title": doc.title,
        "body": body[:MAX_DOCUMENT_BODY_CHARS] + ("…" if truncated else ""),
        "truncated": truncated,
        "source": doc.source,
        "url": doc.url,
        "score": round(hit.score, 4),
        "matched_terms": hit.matched_terms,
    }


def _normalise_symbols(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        symbol = str(value).strip().upper()
        if symbol and symbol not in out:
            out.append(symbol)
    return out


def _holding_to_dict(holding: Any) -> dict[str, Any]:
    """Render stored holdings without exposing account identifiers."""
    demat = str(
        getattr(holding, "demat_last4", "")
        or getattr(holding, "demat_number", "")
        or ""
    )
    return {
        "symbol": holding.symbol,
        "current_balance": holding.current_balance,
        "previous_balance": holding.previous_balance,
        "pledged_balance": holding.pledged_balance,
        "wacc": holding.wacc,
        "previous_closing_price": holding.previous_closing_price,
        "cost_basis": holding.cost_basis,
        "market_value": holding.market_value,
        "isin": holding.isin,
        "script_desc": holding.script_desc,
        "demat_last4": demat[-4:] if demat else None,
        "last_transaction_date": (
            holding.last_transaction_date.isoformat()
            if holding.last_transaction_date
            else None
        ),
        "source": holding.source,
    }


def build_server(
    settings: Settings | None = None,
    storage: Storage | None = None,
) -> MCPServer:
    """Construct a fully wired :class:`MCPServer`.

    Separate from :func:`serve_stdio` so tests can drive the dispatcher directly
    against a temp DB without touching real streams.
    """
    return MCPServer(settings=settings, storage=storage)


@dataclass
class _StdioStreams:
    """Resolved I/O plus whether we own (and may therefore guard) real stdout."""

    stdin: TextIO
    stdout: TextIO
    guard_stdout: bool = field(default=False)


def _resolve_streams(stdin: TextIO | None, stdout: TextIO | None) -> _StdioStreams:
    owns_real_stdout = stdout is None
    return _StdioStreams(
        stdin=stdin if stdin is not None else sys.stdin,
        stdout=stdout if stdout is not None else sys.stdout,
        guard_stdout=owns_real_stdout,
    )


def serve_stdio(
    *,
    settings: Settings | None = None,
    storage: Storage | None = None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> None:
    """Serve MCP over newline-delimited JSON-RPC until stdin closes.

    Blocks. Returns normally on EOF (the client closed the pipe) or on
    ``KeyboardInterrupt``. ``stdin``/``stdout`` exist for tests; a real client
    leaves them unset, in which case ``sys.stdout`` is rebound to stderr for the
    duration so no library ``print()`` can corrupt the frame stream.
    """
    streams = _resolve_streams(stdin, stdout)
    server = build_server(settings=settings, storage=storage)

    saved_stdout = sys.stdout
    if streams.guard_stdout:
        sys.stdout = sys.stderr
    try:
        while True:
            line = streams.stdin.readline()
            if not line:
                break  # EOF: client closed the pipe.
            response = server.dispatcher.handle_line(line)
            if response is None:
                continue  # Notification, or a blank line — say nothing.
            streams.stdout.write(json.dumps(response, default=str) + "\n")
            streams.stdout.flush()
    except KeyboardInterrupt:
        pass
    finally:
        if streams.guard_stdout:
            sys.stdout = saved_stdout


if __name__ == "__main__":
    serve_stdio()
