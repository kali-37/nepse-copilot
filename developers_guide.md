# Developers Guide — NEPSE Trader

The full internals reference: what every layer does, the contracts between them,
the invariants you must not break, and step-by-step recipes for extending the
system.

Read this alongside [`how_it_works.md`](how_it_works.md) (the algorithms in
detail) and [`how_to_use.md`](how_to_use.md) (the operator's command guide).
This document is the one that assumes you are going to *change* the code.

**Contents**

1. [Ground rules](#1-ground-rules)
2. [Layout of the whole system](#2-layout-of-the-whole-system)
3. [Architecture: how a request flows](#3-architecture-how-a-request-flows)
4. [The data contracts (`models.py`)](#4-the-data-contracts-modelspy)
5. [Config and settings](#5-config-and-settings)
6. [Layer: ingestion](#6-layer-ingestion)
7. [Layer: reconciliation](#7-layer-reconciliation)
8. [Layer: storage and migrations](#8-layer-storage-and-migrations)
9. [Layer: analysis](#9-layer-analysis)
10. [Layer: costs and taxes](#10-layer-costs-and-taxes)
11. [Layer: paper trading](#11-layer-paper-trading)
12. [Layer: RAG](#12-layer-rag)
13. [Layer: AI](#13-layer-ai)
14. [Layer: advisor](#14-layer-advisor)
15. [Layer: MeroShare mirror](#15-layer-meroshare-mirror)
16. [Layer: health](#16-layer-health)
17. [Surface: CLI](#17-surface-cli)
18. [Surface: HTTP API](#18-surface-http-api)
19. [Surface: MCP server](#19-surface-mcp-server)
20. [Surface: web UI](#20-surface-web-ui)
21. [Testing](#21-testing)
22. [Recipes](#22-recipes)
23. [Gotchas](#23-gotchas)
24. [Contribution workflow](#24-contribution-workflow)

---

## 1. Ground rules

These are not style preferences. Each one exists because breaking it caused, or
would cause, a specific class of bug.

- **Python ≥ 3.11.** Every module starts with `from __future__ import annotations`.
- **`ruff check .` must pass.** Config in `pyproject.toml`: `select = E,F,I,UP,B,W`,
  line length 100 with E501 ignored, imports sorted.
- **Full type annotations on public functions.** Data crossing a layer boundary is
  a Pydantic v2 model, not a dict.
- **Parsing is separate from I/O.** Network access lives in `BaseClient`; parsing
  lives in pure `parse_*` functions that take raw text or a dict and return
  models. This is the single most important convention in the codebase — it is
  the reason 1284 tests run offline in about a minute.
- **Ingestion degrades, never raises.** A fetch method returns `[]` or `None` on
  failure and logs. One dead source must not abort a daily run.
- **Money rounds at the cost layer** (`_round2` in `analysis/costs.py`), not in
  callers. Two callers rounding independently is how paisa drift starts.
- **Determinism is authoritative.** AI may add prose and evidence. It may never
  change a price, stop, target, quantity, fee, tax, confidence, or PnL.
- **Read-only means read-only.** No order placement, no IPO/ASBA application, no
  auction bid submission, no broker execution. There is no code for it, and
  adding any is out of scope for this project.
- **Credentials never persist.** They come from env, `.env`, or an optional OS
  keyring, and never reach a log line, a database column, an API response, an
  MCP result, or an exception message.
- **No new runtime dependency without a strong reason.** The stack is deliberately
  small: httpx, pydantic, pyyaml, typer, rich, tenacity, dateutil, selectolax,
  fastapi. Everything else is optional and guarded by a capability check.

---

## 2. Layout of the whole system

```
nepse_trader/
├── models.py              # Pydantic contracts — the shared vocabulary
├── config.py              # Settings (env) + sources.yaml + cost_model.yaml
├── config_validation.py   # JSON-Schema validation of the YAML files
├── calendar.py            # trading-day arithmetic + holidays.yaml
├── pipeline.py            # DailyPipeline orchestrator + build_clients()
├── reporting.py           # markdown/rich reports + Alerter (off by default)
├── health.py              # ten read-only checks + snapshot history
├── export.py              # CSV / Parquet dumps of whole tables
├── logging_setup.py       # rotating file + rich console logging
├── ingest/
│   ├── base.py            # BaseClient (throttle/retry/cache) + SourceClient ABC
│   ├── engines.py         # httpx or scrapling fetch engine, selected by config
│   ├── htmlparse.py       # table extraction (selectolax or scrapling)
│   ├── sharesansar.py     # primary source (HTML + DataTables JSON)
│   ├── merolagani.py      # secondary (ASP.NET HTML)
│   ├── nepsealpha.py      # optional
│   ├── chukul.py          # optional (config-driven JSON)
│   ├── nepse_official.py  # optional nepse_scraper adapter + HAR replay
│   ├── fundamentals.py    # EPS/PE/PB scrape
│   ├── news.py            # announcements & news for the RAG corpus
│   └── reconcile.py       # cross-source consensus
├── analysis/
│   ├── indicators.py      # SMA/EMA/RSI/MACD/Bollinger/ATR/Donchian/Ichimoku/Supertrend
│   ├── strategies.py      # Strategy ABC + 8 strategies + composite + registry
│   ├── backtest.py        # Backtester + BacktestResult
│   ├── portfolio.py       # multi-symbol portfolio backtest
│   ├── walkforward.py     # rolling out-of-sample evaluation
│   ├── quant.py           # returns, Sharpe, Sortino, VaR, drawdown, skew/kurtosis
│   ├── risk.py            # position sizing, stop/target placement, exposure
│   ├── screen.py          # whole-market strategy leaderboard
│   └── costs.py           # CostEngine (commission/SEBON/DP/CGT)
├── trading/
│   └── portfolio.py       # PaperPortfolio (WAC + FIFO lots)
├── storage/
│   ├── db.py              # SQLite layer, idempotent upserts, typed reads
│   ├── migrations.py      # 14 ordered migrations + schema_version
│   └── app_settings.py    # key/value reads over the app_settings table
├── rag/
│   ├── corpus.py          # Document + the ten document kinds
│   ├── index.py           # DocumentIndex over FTS5 (LIKE fallback)
│   ├── build.py           # turn database rows into documents
│   ├── retrievers.py      # Local / Web / Hybrid retriever
│   └── evidence.py        # citation packing under a character budget
├── ai/
│   ├── providers.py       # OpenRouter / Anthropic / Claude CLI / Null
│   ├── router.py          # provider chains, fallback, status probe
│   ├── budget.py          # TokenBudget ledger and caps
│   ├── cache.py           # response cache keyed by prompt hash
│   ├── prompts.py         # prompt templates
│   ├── schemas.py         # expected JSON shapes from the model
│   └── analyst.py         # the only caller that turns evidence into prose
├── advisor/
│   ├── plan.py            # deterministic PlanCard construction
│   ├── doses.py           # four nested horizons over one capital pool
│   ├── rashifal.py        # the daily report object
│   ├── confidence.py      # Confidence value + weakest-link blending
│   ├── auction.py         # fee-aware manual bid ceiling
│   ├── journal.py         # prediction lifecycle
│   └── outcomes.py        # scoring a prediction against later bars
├── meroshare/
│   ├── credentials.py     # env / .env / keyring resolution
│   ├── client.py          # read-only portal client
│   ├── importer.py        # credential-free CSV path
│   ├── sync.py            # mirror holdings and transactions
│   ├── privacy.py         # demat fingerprint + masked last four
│   └── models.py          # holdings / transactions / portfolio
├── mcp_server/
│   ├── protocol.py        # JSON-RPC 2.0 framing over stdio
│   └── server.py          # 15 read-only tools, declarative ToolSpec registry
├── har/
│   └── analyzer.py        # HAR analyze / to-config / redact
├── web/
│   └── api.py             # FastAPI app, 45 routes
└── cli/
    ├── main.py            # Typer CLI, 24 commands and command groups
    └── progress.py        # rich progress helpers

config/    sources.yaml, cost_model.yaml, holidays.yaml
docs/      RUNBOOK.md
har/       HAR_CAPTURE_PLAN.md, captures/ (git-ignored)
tests/     62 files, 1284 tests, all offline
web/       React + TypeScript + Vite front end (12 test files, 96 tests)
```

---

## 3. Architecture: how a request flows

Two flows matter. Everything else is a variation.

### The daily data flow

```
sources (public HTML/JSON)
   │  BaseClient: throttle, retry, backoff, raw cache
   ▼
parse_* (pure)                  → PriceBar / IndexValue / FloorsheetEntry
   ▼
Storage.upsert_price_bars       → price_bars   (PK symbol+date+source)
   ▼
reconcile.reconcile_prices      → ReconciledPrice (largest agreeing cluster)
   ▼
Storage.upsert_reconciled       → reconciled_prices (PK symbol+date)
   ▼
indicators → strategies         → Signal
   ▼
backtest / screen / quant       → metrics, net of Nepal costs
   ▼
reporting.write_markdown_report → the daily markdown
```

Every arrow is a pure function or an idempotent write. Re-running any stage on
the same day produces the same rows.

### The advice flow

```
reconciled_prices ──┐
corporate actions ──┤
fundamentals ───────┼─→ advisor/plan.build_plan_cards  (deterministic)
quant stats ────────┤        │
confidence history ─┘        ├─→ costs.CostEngine       (fees, CGT, break-even)
                             ├─→ risk                   (stop, target, size)
                             └─→ confidence.blend       (weakest link)
                                     │
                                     ▼
                            advisor/doses.build_doses   (4 horizons, 1 pool)
                                     │
             ┌───────────────────────┴────────────────────────┐
             ▼                                                ▼
   rag: retrieve evidence                            journal: log prediction
             ▼                                                ▼
   ai/analyst: prose only                          outcomes: score it later
             ▼                                                ▼
        rashifal report                                calibration table
```

The left branch can be switched off entirely (`--mode normal`) and the numbers do
not move. That is the design constraint: **AI is a commentary layer bolted onto a
deterministic core, never a participant in the arithmetic.**

---

## 4. The data contracts (`models.py`)

Everything speaks these Pydantic v2 models. Construct with keyword arguments;
`symbol` is auto-uppercased on `PriceBar`, `FloorsheetEntry`, `Signal`,
`PaperTrade`, and `Position`, so callers must not re-normalize.

| Model | Purpose | Key fields |
|-------|---------|-----------|
| `PriceBar` | one security's OHLCV for one date, from one source | `symbol, business_date, open/high/low/close, previous_close, volume, turnover, trades, source`; `.change`, `.change_percent` |
| `IndexValue` | one index reading | `name, business_date, value, change, change_percent, source` |
| `FloorsheetEntry` | one matched trade | `contract_id, symbol, business_date, buyer_broker, seller_broker, quantity, rate, amount, source` |
| `MarketStatus` | open or closed | `is_open, as_of, session, source` |
| `ReconciledPrice` | cross-source consensus | `…, sources_agreeing, sources_present, disputed_fields, confidence`; `.is_trustworthy` |
| `Signal` | one strategy decision | `symbol, business_date, action, strategy, strength, reason, price, indicators` |
| `PaperTrade` | an executed paper trade | full cost breakdown plus `net_amount` |
| `Position` | a holding | `symbol, quantity, avg_cost`; `.cost_basis` |

Enums: `SourceName`, `SignalAction` (BUY/SELL/HOLD), `OrderSide` (BUY/SELL).

Advisor and MeroShare add their own models inside their packages (`PlanCard`,
`Dose`, `DoseRun`, `Rashifal`, `Confidence`, `Prediction`, `Outcome`,
`AuctionAdvice`, `MeroShareHolding`, `MeroShareTransaction`,
`MeroSharePortfolio`) — that is local vocabulary, not the shared one.

---

## 5. Config and settings

Three layers, deliberately separate.

**`Settings` (`config.py`)** — 43 fields, environment-driven with the prefix
`NEPSE_`, loadable from `.env`. Get it through `get_settings()`, which is cached;
in tests that mutate the environment call `get_settings.cache_clear()`, or build
`Settings(_env_file=None, **overrides)` so the developer's own `.env` cannot
change the outcome.

Grouped by concern:

- storage and cache — `db_path`, `raw_cache_dir`, `log_dir`, `sources_file`,
  `cost_model_file`
- HTTP — `fetch_engine`, `parse_engine`, `user_agent`, `request_timeout`,
  `max_retries`, `min_request_interval`, `scrapling_impersonate`
- reconciliation — `enabled_sources`, `price_agreement_tolerance`
- advisor — `watchlist`, `advisor_max_symbols`
- AI — `analysis_mode`, `online`, `llm_synthesis_providers`,
  `llm_bulk_providers`, `llm_timeout`, `llm_cache_ttl_hours`,
  `llm_max_calls_per_day`, `llm_max_tokens_per_day`,
  `llm_max_deep_passes_per_week`, `openrouter_*`, `anthropic_*`, `claude_cli_*`
- RAG — `rag_enable_web`, `rag_web_search_urls`, `rag_max_documents`,
  `rag_max_evidence_chars`
- MeroShare — `meroshare_enabled`, `meroshare_base_url`, `meroshare_dp_id`,
  `meroshare_username`, `meroshare_password`, `meroshare_use_keyring`,
  `meroshare_keyring_service`

**YAML (`config/`)** — data that should change without a code edit:
`sources.yaml` (per-source base URL, endpoints, `enabled`, confidence),
`cost_model.yaml` (commission slabs, SEBON/DP/CGT rates), `holidays.yaml`
(single dates and ranges). Loaded by `load_sources()`, `load_cost_model()`,
`load_holidays()`.

**`config_validation.py`** — JSON Schemas for those three files, run by
`validate_all()` and surfaced through the `config` health check. A schema must
accept everything the repository actually ships. `holidays.yaml` has a `ranges:`
key whose entries are all commented out, so YAML parses it as `null`;
`load_holidays` already reads that as empty, so the schema accepts
`["array", "null"]`. After tightening a schema, run the health check.

**Database-backed settings (`storage/app_settings.py`)** — a small key/value
table for toggles a user flips at runtime (the watchlist, the MeroShare switch).
A database value overrides the environment, and `read_bool` reports which source
won so the UI can say so. The module raises if migration `0011_app_settings` has
not run rather than silently creating the table: DDL belongs to migrations only.

---

## 6. Layer: ingestion

`BaseClient` (`ingest/base.py`) owns everything about talking to the network:

- **Throttling** — at least `min_request_interval` seconds between requests to
  the same host.
- **Retries** — tenacity with exponential backoff; 403 and 429 back off harder.
- **Raw cache** — every response body is written to
  `data/raw/<YYYYMMDD>_<hash>.txt` on a best-effort basis, so a disagreement
  between two sources can be traced to exactly what each returned.
- **Engine choice** — `engines.build_engine()` returns an httpx engine or a
  scrapling engine depending on `fetch_engine`, and falls back if scrapling is
  not installed.

`SourceClient` is the ABC each source implements. The pattern every source
follows:

```python
def fetch_prices(self, business_date=None) -> list[PriceBar]:
    try:
        res = self.client.fetch(url, params=...)
        return self.parse_prices(res.text, business_date, self.name)
    except Exception:
        return []          # degrade; the pipeline logs and continues

@staticmethod
def parse_prices(raw: str, business_date, source) -> list[PriceBar]:
    ...                    # pure; this is what the tests exercise
```

`htmlparse.py` provides `table_rows()` and `td_texts()` over selectolax (or
scrapling), so no source hand-rolls HTML traversal.

Source status today: ShareSansar is the enabled primary. MeroLagani, NepseAlpha,
Chukul and NEPSE-official ship disabled — enable one by setting `enabled: true`
in `sources.yaml` **and** adding its name to `NEPSE_ENABLED_SOURCES`. Both gates
must agree, and the `config` health check reports the intersection.

---

## 7. Layer: reconciliation

`reconcile.reconcile_prices` takes every bar for one symbol on one date and finds
the **largest cluster of sources whose close agrees** within
`price_agreement_tolerance` (0.5% by default). That cluster's values become the
consensus; `confidence` is the share of present sources inside it; every field
where sources disagreed is listed in `disputed_fields`.

Design notes worth knowing before you touch it:

- One source present means confidence `1.0` with a single-element
  `sources_agreeing`. That is honest — nothing contradicted it — but it is not
  corroboration. `is_trustworthy` exists so callers can require more.
- Ties break toward the source with the higher configured confidence in
  `sources.yaml`, then alphabetically, so the result is deterministic.
- The write is keyed `(symbol, business_date)`, so re-reconciling a day is
  idempotent and safe to schedule.

---

## 8. Layer: storage and migrations

**`Storage` (`storage/db.py`)** wraps one SQLite connection in WAL mode with
`row_factory = sqlite3.Row`. Rules:

- Idempotent primary keys: `price_bars (symbol, business_date, source)`,
  `reconciled_prices (symbol, business_date)`,
  `signals (symbol, business_date, strategy)`.
- Callers use the typed helpers (`price_history`, `reconciled_history`,
  `bars_for_date`, `paper_trades`, `db_stats`, `symbols`, `all_*`) rather than
  raw SQL. The `all_*` readers exist for the exporter and return whole tables.
- Every write is parameterized. No string interpolation into SQL, ever.
- `_tx()` is the transaction context manager; batch writes go through it.

**Migrations (`storage/migrations.py`)** are an ordered list of
`(version, callable)` pairs recorded in `schema_version`. There are 14, from
`0000_initial` to `0013_health_snapshots`, producing 30 tables (including the
FTS5 shadow tables).

```python
def _m0013_health_snapshots(conn) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS health_snapshots (...)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_health_snapshots_captured ...")

MIGRATIONS = [..., ("0013_health_snapshots", _m0013_health_snapshots)]
```

Rules for adding one: append, never renumber; make it idempotent
(`IF NOT EXISTS`); never rewrite a shipped migration, since databases in the wild
already recorded it; add typed read/write methods on `Storage` and a test in
`tests/test_migrations.py`. The `schema` health check compares `schema_version`
against `MIGRATIONS` and reports a missing version as a failure and an unknown
one as a warning — a newer build wrote it, and reads still work.

---

## 9. Layer: analysis

**`indicators.py`** — pure functions returning a list aligned to the input with
`None` during warm-up: `sma`, `ema`, `rsi`, `macd`, `bollinger_bands`, `atr`,
`donchian_channel`, `supertrend`, and the Ichimoku set (`tenkan_sen`,
`kijun_sen`, `senkou_span_a`, `senkou_span_b`, `chikou_span`), plus `latest()`.

**`strategies.py`** — the `Strategy` ABC, eight registered strategies, and a
`CompositeStrategy` that is deliberately *not* in the registry because it needs
sub-strategy instances.

| Name | Class | Idea |
|------|-------|------|
| `sma_cross` | `SmaCrossStrategy` | fast SMA crossing slow SMA |
| `rsi` | `RsiStrategy` | oversold/overbought reversal |
| `macd` | `MacdStrategy` | MACD zero-line cross (by design, not a signal-line cross) |
| `bollinger` | `BollingerStrategy` | band touch and mean reversion |
| `donchian` | `DonchianStrategy` | channel breakout |
| `ichimoku` | `IchimokuStrategy` | cloud and conversion-line state |
| `supertrend` | `SupertrendStrategy` | ATR trailing-stop flip |
| `mean_reversion` | `MeanReversionStrategy` | z-score reversion to the mean |

Two conventions every strategy obeys. `self._closes(bars)` returns
`(closes, has_close)`: a None close carries the previous value forward so
indicator maths stay continuous, while `has_close[i]` is False so **no signal is
emitted on a gap day**. And BUY/SELL fire **only on a state change** — otherwise
HOLD. `build_strategy(name, **kwargs)` instantiates from `STRATEGIES` and raises
`ValueError` listing the known names.

**`backtest.py`** — long-only, same-bar-close execution, full Nepal costs on
every fill. `BacktestResult` carries total return, CAGR, max drawdown, Sharpe,
trade count, win rate, exposure.

**`portfolio.py`** (analysis) — the same idea across many symbols with one shared
cash pool. **`walkforward.py`** — rolling out-of-sample windows, so a parameter
set that only works in-sample is visible as such. **`quant.py`** — returns, log
returns, annualized return and volatility, Sharpe, Sortino, max drawdown, VaR,
skewness, kurtosis, beta, correlation, `summary_stats`. **`risk.py`** —
`size_position`, `stop_loss_price`, `take_profit_price`, `exposure_pct`.
**`screen.py`** — runs the panel over every symbol with enough history and ranks
by `sharpe | total_return_pct | cagr_pct | max_drawdown_pct | win_rate_pct`.

---

## 10. Layer: costs and taxes

`analysis/costs.py` is the money authority. `CostEngine` reads
`config/cost_model.yaml` and exposes `commission_rate`, `broker_commission`,
`sebon_fee`, `compute`, and `effective_buy_cost_per_share`.

The shipped Nepal model:

| Component | Value |
|-----------|-------|
| Broker commission | 0.36% below Rs 50k; 0.33% to 500k; 0.31% to 2M; 0.27% to 10M; 0.24% above |
| Minimum commission | Rs 10 |
| SEBON fee | 0.015% of turnover |
| DP charge | Rs 25 per scrip per settlement |
| CGT | 7.5% short-term individual, 5% long-term (held **> 365 days**), 10% institutional |
| Settlement | T+2 |

Two boundary rules have regression tests, and both are easy to "fix" wrongly: a
commission slab boundary belongs to the **lower** (higher-rate) tier, and
long-term CGT requires **strictly more than** 365 days. The headline invariant is
the worked example in `tests/test_costs.py` — BUY 100 @ 1000 costs 100,370 and
SELL 100 @ 1200 returns 118,121.67 with CGT 1,439.33. If you touch `costs.py` or
the YAML, that must still hold to the paisa.

---

## 11. Layer: paper trading

`trading/portfolio.py` implements `PaperPortfolio` with weighted-average cost for
reporting and **FIFO lots** for CGT, because the holding period that sets the tax
rate is the oldest lot's. Buys are rejected when cash is insufficient with fees
included; sells are rejected when the shares are not held.

The important structural decision: **paper state is replay-derived**. Nothing
stores a running balance. `DailyPipeline.replay_portfolio(cash)` rebuilds the
account by replaying `paper_trades` in order. So keep `--cash` consistent between
calls, and do not add a second source of truth.

---

## 12. Layer: RAG

`rag/corpus.py` defines `Document` and the ten kinds: `price`, `indicator`,
`signal`, `quant`, `reconcile`, `fundamental`, `corporate_action`, `news`,
`report`, `web`.

`rag/index.py` — `DocumentIndex` over an FTS5 virtual table with BM25 ranking,
falling back to `LIKE` when the SQLite build has no FTS5. `uses_fts` says which
path is live, and the `rag` health check surfaces it, because the fallback is
unranked and that changes what evidence the advisor sees.

`rag/build.py` turns database rows into documents (this is what `rag index`
runs). `rag/retrievers.py` has `LocalRetriever`, `WebRetriever`, and
`HybridRetriever`; `build_retriever(settings)` picks one, and the web leg is only
built when `rag_enable_web` **and** `online` are both true.

`rag/evidence.py` packs hits into a citation pack under
`rag_max_evidence_chars`, returning markers, kinds, symbols, a `citations` map
from marker to document id, a `truncated` flag, and the rendered text. Prose that
cites `[1]` can always be traced back to a stored document — that is the whole
point, and it is why the packer never silently drops the marker map.

---

## 13. Layer: AI

Four providers behind one interface in `ai/providers.py`: `OpenRouterProvider`,
`AnthropicProvider`, `ClaudeCliProvider`, and `NullProvider`. Each implements
`available()` as a **configuration probe** — no network call, no subprocess —
which is what lets the health check ask "could this work?" for free.

`ai/router.py` (`LLMRouter`) holds two chains, bulk and synthesis, and walks the
legs in order until one answers. `status()` returns each leg's availability, the
budget, and cache size without spending anything.

`ai/budget.py` (`TokenBudget`) is a ledger in `ai_budget_ledger` enforcing calls
per day, tokens per day, and deep passes per week. `record(response, task=...)`
takes an `LLMResponse`, so the ledger cannot drift from what was actually
returned. `ai/cache.py` keys responses by prompt hash with a TTL.

`ai/analyst.py` is the **only** module that turns evidence into prose, and it is
the boundary where the determinism rule is enforced. When no provider is
available, or the budget is spent, the run degrades to normal mode with a visible
banner — it does not fail, and it does not alter a single number.

---

## 14. Layer: advisor

**`plan.py`** builds a `PlanCard`: entry, stop, target, quantity, fees, tax,
break-even, expected net PnL, earliest sell date (T+2), and a confidence. Every
value is arithmetic over reconciled prices and the cost model.

**`doses.py`** partitions one capital pool across four nested horizons:

| Dose | Trading days | Allocation |
|------|--------------|-----------|
| day | 3 | 10% |
| week | 10 | 20% |
| month | 22 | 30% |
| year | 250 | 40% |

A card belongs to exactly one horizon. `_FORBIDDEN` is a compiled regex
(`guaranteed?|sure|risk[- ]?free`) applied to dose prose, because language
implying certainty is a real harm in a market tool regardless of the number next
to it.

**`confidence.py`** — `Confidence(value, basis, sample_size)` with seven bands
from `CERTAIN` (1.0, "arithmetic, not a forecast") down to `REMOTE`. `CERTAINTY`
is 1.0 and reserved for arithmetic; `MARKET_CEILING` is 0.9, so no directional
forecast can ever be presented as certain; `DEFAULT_PRIOR` is 0.45.

`blend()` combines legs by **weakest link — the minimum, not the average**. A
plan needs the entry to fill *and* the target to be reached *and* enough volume
to exit; those are conjunctive. Averaging would let a 0.99-certain settlement
date paper over a 0.35 edge and produce a comfortable-looking 0.67 that describes
nothing. The returned basis names the binding leg.

**`auction.py`** computes a fee-aware break-even, recommended bid, maximum
sensible bid, and walk-away price. `manual_only` is always true and there is no
submission path.

**`journal.py` / `outcomes.py`** — the prediction lifecycle
`open → scored → reviewed → retired`. Scoring checks the **stop before the
target** (a conservative intrabar sequence assumption that must stay that way),
counts only `TARGET_HIT` as a hit, and excludes `UNRESOLVED` and `NO_DATA` from
calibration. Distilled lessons are indexed for RAG, so a reviewed mistake becomes
retrievable evidence later.

---

## 15. Layer: MeroShare mirror

Strictly read-only, and the constraint is structural rather than documented:
there is no application, order, or bid code to disable.

`credentials.py` resolves from environment, `.env`, or an optional OS keyring
into `MeroShareCredentials`, whose `missing()` returns **field names** — `dp_id`,
`username`, `password` — never values. `resolve_credentials` returns a
`Resolution` saying whether it is complete and where it came from.

`client.py` performs the read-only portal calls; `importer.py` offers a
credential-free path from a CSV export; `sync.py` mirrors holdings and
transactions into `ms_holdings` / `ms_transactions` and logs each attempt to
`ms_sync_log`. A failed sync **does not clear the last good holdings** — a portal
outage should not look like an emptied portfolio.

`privacy.py` stores a `demat_fingerprint` (hash) plus `demat_last4`. The full
demat number is never persisted or returned. `redact()` scrubs credential-shaped
values before anything is logged, and a test asserts a known secret is absent
from a whole dumped payload.

---

## 16. Layer: health

`health.py` answers one question: *why does the output look wrong?* A stale
database, a source that stopped parsing, an exhausted token budget, and a
half-applied schema all look identical from the outside otherwise.

Three rules the module states in its own docstring and every check obeys:

1. Nothing writes, fetches, or spends — except `record_snapshot`, which a caller
   must ask for explicitly.
2. A check never raises. `_guarded` catches everything and turns a broken check
   into a `fail` on that check alone, because a broken check is itself a finding.
3. No credential and no account identifier ever appears in the output.

Ten checks, in a fixed order (`CHECK_ORDER`):

| Check | Watches | Fails when |
|-------|---------|-----------|
| `schema` | migrations vs `schema_version` | a migration is missing, or the database was never migrated |
| `database` | row counts, symbol count, file size | — (warns when empty, or when raw rows exist with nothing reconciled) |
| `freshness` | trading days behind the last trading day | — (warns past `STALE_AFTER_TRADING_DAYS` = 3) |
| `ingest` | error ratio over the last 20 attempts | — (warns past 25%, naming the failing source) |
| `config` | `validate_all()` plus the effective source set | a YAML file fails its schema |
| `rag` | corpus size, per-kind coverage, FTS5 | — (warns when empty or unranked) |
| `ai` | provider availability and today's budget | — (warns at 80% of a cap, or with no provider) |
| `meroshare` | toggle, credential completeness, last sync | — (warns on missing fields or a failed sync) |
| `journal` | open, scored, overdue predictions | — (warns when a prediction is past its deadline) |
| `paper` | replayed cash, positions, realized PnL | — |

Statuses are `ok`, `warn`, `fail`, `off`, and the overall verdict is worst-wins
over `_SEVERITY = {off: 0, ok: 1, warn: 2, fail: 3}`. **`off` ranks below `ok`
deliberately**: a feature nobody enabled must not drag the verdict down, so
`analysis_mode=normal` reports `off` for `ai` and the system still reads healthy.

`system_health(storage, settings, today=None)` returns
`{status, generated_at, counts, checks}`. `problems(report)` filters to warnings
and failures. `record_snapshot`, `snapshot_history`, and `snapshot` handle the
`health_snapshots` table. Recording is opt-in on every surface — CLI `--record`,
API `?record=true`, an explicit web button — so viewing health never grows the
database.

---

## 17. Surface: CLI

`cli/main.py` is a Typer app: 24 commands and command groups. Top-level:
`sources`, `ingest`, `reconcile`, `signal`, `backtest`, `stats`, `screen`,
`run-daily`, `rashifal`, `advise`, `doses`, `health`, `dashboard`. Groups: `har`,
`paper`, `corporate-actions`, `fundamentals`, `journal`, `auction`, `meroshare`,
`mcp`, `export`, `rag`, `ai`.

Conventions: output through `rich` (`console`), status marks from small maps like
`_HEALTH_MARKS`, `--json` on commands whose output is worth piping, and a
non-zero exit when the result is actionable — `health` exits 1 on an overall
`fail` so cron can alert on it.

---

## 18. Surface: HTTP API

`web/api.py` is a FastAPI app with a module-level `app` (there is no `create_app`
factory) and 45 routes under `/api`. Groups: dashboard and market
(`/dashboard`, `/market-breadth`, `/movers`, `/symbols`, `/symbols/{symbol}/…`),
`/portfolio`, `/backtest/*`, `/ingest`, `/rag/*`, `/ai/budget`, `/news`,
`/advisor/*`, `/journal/*`, `/auction/*`, `/meroshare/*`, `/settings/*`, and
`/health*`.

The health routes show the intended split: `/api/health` stays a **bare liveness
probe** returning `{"status": "ok"}`, while the ten-check report lives at
`/api/health/report`. A load balancer polling the probe can never be made
expensive, and `?record=true` is the only way the report writes.

---

## 19. Surface: MCP server

`mcp_server/protocol.py` implements JSON-RPC 2.0 framing over newline-delimited
stdio with a `Dispatcher`. `server.py` registers 15 read-only tools declaratively
as `ToolSpec` entries: `list_symbols`, `price_history`, `market_breadth`,
`top_movers`, `latest_signals`, `quant_stats`, `search_documents`,
`database_stats`, `system_health`, `backtest`, `screen`, `portfolio`,
`meroshare_holdings`, `rashifal`, `doses`.

Non-negotiables: the server reads the local SQLite database and constructs **no
source clients**, so no tool call can trigger a network fetch; all diagnostics go
to **stderr** so stdout stays valid JSON-RPC; every tool is bounded (explicit
limits, no unbounded table scans); and no tool returns a credential or a full
demat number. Copy `.mcp.json.example` to `.mcp.json` and point it at this
checkout's `.venv/bin/python`.

---

## 20. Surface: web UI

`web/` is React + TypeScript + Vite, tested with Vitest, React Testing Library
and msw, linted with oxlint. 11 routes across 10 nav items: Dashboard, Symbols
(plus `/symbols/:symbol`), Portfolio, Backtest, Rashifal, Auction, MeroShare,
Research, Health, Settings.

Structure: `api/types.ts` mirrors the FastAPI response shapes, `api/client.ts` is
the single fetch layer (every call goes through `fetchJson`), `components/ui/*`
holds the six primitives (`Badge`, `Card`, `DataTable`, `ErrorState`,
`LoadingSpinner`, `StatCard` — note `Card` takes only
`children/className/title/actions`), `layouts/RootLayout.tsx` owns the nav and
dark mode, and `pages/*` is one file per route with a `*.test.tsx` beside it.

Adding a page means touching five places: the type in `types.ts`, the method in
`client.ts`, a fixture in `test/fixtures.ts`, a handler in `test/handlers.ts`, the
page plus its test, then the route in `App.tsx` and the nav entry in
`RootLayout.tsx`. Miss one and the test suite tells you which.

---

## 21. Testing

```bash
.venv/bin/python -m pytest -q      # 1284 tests, all offline
.venv/bin/ruff check .             # lint
cd web && npm run lint             # oxlint
cd web && npx vitest run           # 96 tests across 12 files
cd web && npm run build            # type-check + production build
```

Principles:

- **Everything is offline.** Network is mocked with `respx`; parsing is tested
  with inline fixtures; anything time-sensitive takes an explicit date.
- **One `test_<module>.py` per module.** 62 files today. New code ships with its
  tests in the same commit.
- **Test the pure functions directly** (fast, exact) and add one integration test
  through the client or pipeline for wiring.
- **Build `Settings(_env_file=None, …)` in tests** that touch AI or MeroShare, so
  the developer's own `.env` cannot decide the result.
- **`tests/test_properties.py` uses Hypothesis** and can occasionally trip a
  deadline on a loaded machine. Re-run the single test before believing it.
- Do not pass `-p no:logging` — it disables the `caplog` fixture and several
  tests error at setup.

---

## 22. Recipes

### Add a data source

1. Add `YOURSITE = "yoursite"` to `SourceName` in `models.py`.
2. Create `ingest/yoursite.py`:

   ```python
   from __future__ import annotations
   from datetime import date
   from nepse_trader.config import SourceSpec, load_sources
   from nepse_trader.ingest.base import BaseClient, SourceClient
   from nepse_trader.models import PriceBar, SourceName

   class YourSiteClient(SourceClient):
       name = SourceName.YOURSITE

       def __init__(self, client=None, source_spec=None):
           self.client = client or BaseClient()
           self.spec = source_spec or load_sources().get("yoursite")

       def fetch_prices(self, business_date: date | None = None) -> list[PriceBar]:
           try:
               url = self.spec.endpoints["today_price"].url
               params = {"date": business_date.isoformat()} if business_date else None
               return self.parse_prices(self.client.fetch(url, params=params).text,
                                        business_date, self.name)
           except Exception:
               return []

       @staticmethod
       def parse_prices(raw: str, business_date, source) -> list[PriceBar]:
           ...   # pure
   ```

3. Add a `yoursite:` block to `config/sources.yaml` with `base_url`, `endpoints`,
   `enabled`, and an honest `confidence`.
4. Register the factory in `pipeline._CLIENT_FACTORIES`.
5. Add `tests/test_yoursite.py`: fixture HTML/JSON into `parse_prices`, plus one
   `respx` test for the endpoint wiring.

Discover the real endpoints with `har analyze` / `har to-config` rather than
guessing, and always fetch through `BaseClient` so you inherit throttling,
retries, backoff, and the audit cache.

### Add a strategy

1. Subclass `Strategy` in `analysis/strategies.py`:

   ```python
   class MyStrategy(Strategy):
       name = "my_strategy"

       def __init__(self, period: int = 14):
           self.period = period

       def generate(self, bars: list[PriceBar]) -> list[Signal]:
           closes, has_close = self._closes(bars)
           out, prev_state = [], None
           for i, bar in enumerate(bars):
               if not has_close[i]:
                   continue
               state = ...                      # from indicators
               action = ... if state != prev_state else SignalAction.HOLD
               prev_state = state
               out.append(self._emit(bar, action, strength, reason, {"period": self.period}))
           return out
   ```

2. Register it in `STRATEGIES`. `build_strategy`, the CLI help, `screen`, and the
   API all pick it up from the registry.
3. Test it: craft a synthetic price path that forces a known crossover, assert
   BUY then SELL on the right dates and HOLD elsewhere, assert
   `0 ≤ strength ≤ 1`, and assert `indicators` is populated.

Long-only, emit on state change, never emit on a no-close day.

### Add an indicator

Add a pure function to `analysis/indicators.py` returning a list aligned to the
input with `None` during warm-up:

```python
def wma(values: Sequence[float], period: int) -> list[Number]:
    out: list[Number] = [None] * len(values)
    weights = list(range(1, period + 1)); denom = sum(weights)
    for i in range(period - 1, len(values)):
        window = values[i - period + 1 : i + 1]
        out[i] = sum(w * v for w, v in zip(window, weights, strict=True)) / denom
    return out
```

Test exact values against hand-computed expectations.

### Add a table

1. Append a migration to `MIGRATIONS` (never renumber, always `IF NOT EXISTS`).
2. Add typed read/write methods on `Storage`.
3. Add a test in `tests/test_migrations.py` and one in `tests/test_storage.py`.
4. If it should be exportable, add it to `EXPORT_TABLES` in `export.py` mapped to
   its `all_*` reader.

### Add a health check

1. Write `check_<name>(...) -> Check` in `health.py`. Return, never raise; put the
   numbers in `metrics` and a human sentence in `detail`; use `OFF` when the
   feature is switched off rather than broken.
2. Add it to `CHECK_ORDER` and to the `checks` list in `system_health`, wrapped in
   `_guarded`.
3. Add the plain-words label to `WHAT_IT_WATCHES` in `web/src/pages/Health.tsx`.
4. Test every branch, plus one test asserting no credential value reaches the
   report.

### Add an MCP tool

Add a `ToolSpec` with a JSON Schema and a `_tool_<name>` handler on `MCPServer`.
It must read only local SQLite, be bounded, keep diagnostics on stderr, and
return no credential or full demat number. Add cases to
`tests/test_mcp_server.py`, and to `tests/test_mcp_protocol.py` if the framing
changes.

---

## 23. Gotchas

- **Symbols are uppercased by the models.** Do not re-normalize in callers.
- **`_closes()` masks gap days.** A None close carries forward for indicator
  maths, but `has_close[i]` is False, so no signal is emitted there.
- **MACD is a zero-line cross by design**, documented in the class. Do not "fix"
  it to a signal-line cross.
- **CGT long-term is `> 365` days**, and **commission slab boundaries belong to
  the lower, higher-rate tier**. Both have regression tests.
- **Paper state is replay-derived.** Keep `--cash` consistent; never add a second
  source of truth.
- **`confidence.blend` is a minimum, not a mean.** Changing it to an average
  silently inflates every card.
- **`1.0` confidence is arithmetic only**; `MARKET_CEILING` (0.9) caps any
  directional claim.
- **Dose prose is regex-screened** for `guarantee`, `guaranteed`, `sure`, and
  `risk-free`. Adding prose means keeping that screen passing.
- **`off` sorts below `ok`** in health severity. Reordering `_SEVERITY` would make
  every disabled feature look like a problem.
- **`/api/health` must stay cheap.** Put anything expensive under
  `/api/health/report`.
- **A schema in `config_validation.py` must accept what the repo ships.** Run the
  `config` health check after tightening one.
- **`Card` has no `subtitle` prop** — only `children`, `className`, `title`,
  `actions`.
- **HAR redaction** must strip any new secret-bearing field you introduce; the
  test asserts a known token is absent from the whole dumped HAR.
- **`data/raw/`, `s.py`, and `graphify-out/`** are working artifacts. Leave them
  alone.

---

## 24. Contribution workflow

1. Branch from `master`.
2. Make the change with its tests, preserving the parse/fetch separation.
3. Green: `ruff check .`, `pytest -q`, and in `web/` — `npm run lint`,
   `npx vitest run`, `npm run build`.
4. Run `.venv/bin/python -m nepse_trader.cli.main health` and confirm nothing that
   was `ok` regressed to `warn` or `fail`.
5. If you added or verified an endpoint, update `config/sources.yaml` including
   its `confidence`.
6. Update the docs that changed: `how_it_works.md` for algorithms,
   `how_to_use.md` for commands, `docs/RUNBOOK.md` for operations, this file for
   contracts.
7. Run `graphify update .` so the knowledge graph matches the code.
8. Commit with a conventional-commit subject (`feat:`, `fix:`, `refactor:`,
   `chore:`), one logical unit per commit.

See [`what_to_add_next.md`](what_to_add_next.md) for the prioritized backlog and
[`make_evenBetter.md`](make_evenBetter.md) for engineering-quality upgrades.
