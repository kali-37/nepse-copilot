# NEPSE Trader — Agent Context

## Project
Expert-grade NEPSE (Nepal Stock Exchange) public-data aggregation, analysis,
backtesting and paper-trading engine. Runs entirely offline after data is
ingested. No broker API required.

## Tech Stack
- **Language:** Python 3.11+
- **HTTP client:** httpx
- **HTML parser:** selectolax
- **CLI framework:** typer + rich
- **Config:** pydantic + pydantic-settings + PyYAML
- **Retry/decorators:** tenacity
- **Testing:** pytest + respx (mock HTTP) + freezegun + hypothesis
- **Scraping:** scrapling (optional, for adaptive selectors)
- **Database:** SQLite via stdlib sqlite3, WAL mode

## Project Structure
```
nepse_trader/
  __init__.py
  config.py             — pydantic-settings + sources.yaml loader
  pipeline.py           — DailyPipeline: ingest → reconcile → signal → report
  calendar.py           — NEPSE holiday calendar, trading-day detection
  reporting.py          — Rich/Markdown report builders
  export.py             — CSV/Parquet export
  models.py             — PriceBar, ReconciledPrice, Signal, PaperTrade, etc.
  logging_setup.py      — Per-invocation file logger
  cli/
    __init__.py
    main.py             — typer CLI (ingest, reconcile, signal, backtest, screen,
                          stats, run-daily, dashboard, har, export, fundamentals,
                          paper, corporate-actions)
    progress.py         — Rich progress bar/spinner helpers
  storage/
    __init__.py
    db.py               — Storage class (SQLite CRUD, batch upserts, symbols cache)
    migrations.py       — Schema versioning / migration runner
  ingest/
    __init__.py
    base.py             — SourceClient ABC + BaseClient (throttle, retry, async)
    engines.py          — FetchEngine (httpx), HttpxEngine (async)
    sharesansar.py      — ShareSansarClient
    merolagani.py       — MeroLaganiClient
    chukul.py           — ChukulClient
    nepsealpha.py       — NepseAlphaClient (UDF datafeed)
    nepse_official.py   — NepseScraperClient
    fundamentals.py     — MeroLaganiFundamentalsClient
    reconcile.py        — reconcile_bars() cross-source consensus
  analysis/
    __init__.py
    strategies.py       — SMA Cross, RSI, MACD, Bollinger, Supertrend, Ichimoku,
                          Donchian Breakout, Mean-reversion, Composite voting
    indicators.py       — SMA, EMA, RSI, MACD, Bollinger, ATR, Supertrend,
                          Donchian, Ichimoku (pure Python, no numpy)
    backtest.py         — Backtester (Nepal costs: broker/SEBON/DP/CGT)
    portfolio.py        — Multi-symbol portfolio backtest
    screen.py           — Multi-symbol, multi-strategy backtest screening
    walkforward.py      — Walk-forward optimisation (expanding window)
    costs.py            — CostEngine (broker slabs, SEBON, DP, CGT)
    risk.py             — Position sizing, stops/targets, ±10% circuit clamp
    quant.py            — Sharpe, Sortino, VaR, skew, kurtosis
  trading/
    __init__.py
    portfolio.py        — PaperPortfolio (buy/sell, FIFO lots, realized PnL)
  har/
    __init__.py
    analyzer.py         — HAR capture analysis & endpoint discovery
  web/
    __init__.py
    api.py              — FastAPI app; serves the built React SPA from web/dist
tests/
  test_*.py             — Offline unit, integration and property tests
web/
  src/                  — React 19 + Vite + Tailwind v4 + recharts SPA
```

Alerting lives in `reporting.py` (`Alerter`: Telegram / Discord / SMTP / generic
webhook), not in a separate package.

## Recent Sprint Progress

### Sprint 1 — Data Pipeline Fundamentals ✓
1.1 Source clients (ShareSansar, MeroLagani, Chukul, NepseOfficial, NepseAlpha)
1.2 Ingest reconciliation
1.3 Storage + migrations
1.4 NepseAlpha UDF datafeed client

### Sprint 2 — Strategy & Analysis ✓
2.1 Risk-managed position sizing + stop-loss/take-profit
2.2 Strategy panel: SMA Cross, RSI, MACD, Supertrend, Ichimoku, Donchian, Mean-rev
2.3 Multi-symbol portfolio backtest (Nepal costs, ScreenRow leaderboard)
2.4 Walk-forward optimisation (expanding window, Sharpe-based)
2.5 Fundamentals ingestion (MeroLagani EPS, PE, PBV, etc.)

### Sprint 3 — CLI & User Experience ✓
3.1 Config validation (JSON Schema for sources.yaml)
3.2 User-friendly error messages in CLI
3.3 CLI docs via --help (inherent via typer)
3.4 Full-chain integration test (ingest→reconcile→signal→backtest)
3.5 README architecture documentation

### Sprint 4 — Performance & Data ✓
4.1 Async HTTP (async_raw_request, async_fetch, async_ingest, --async flag)
4.2 DB tuning (synchronous=NORMAL, cache_size, temp_store, symbols cache, batch_log_ingest)
4.3 CLI progress bars/spinners (ingest, reconcile, screen, backtest, stats, run-daily)
4.4 Data export (CSV stdlib, Parquet optional polars, 7 tables)
4.5 Dashboard command (symbols, date range, source coverage, reconciliation health, portfolio)

## Current State
- **Tests:** 1483 passing, 1 skipped (Python 3.12); 194 passing (frontend).
  GitHub CI also checks clean Python 3.11 and 3.12 installs.
- **Lint:** ruff clean
- **Schema:** sources.jsonc config validation shipped
- **Current completion:** historical backfill, persisted price adjustments,
  fundamentals filters, shared portfolio/walk-forward research, broker/sector
  views, ingestion reliability and the populated dashboard are implemented.
- **Decision UI:** daily/monthly evidence-scored buy ideas, saved personal exit
  plans, atomic/idempotent manual trade records, and one-button public-source
  refresh are shipped. Advice remains offline-readable; orders stay manual.
- **Fundamental decisions:** dated EPS/book value gates new buys, valuation
  affects confidence, and visible reasons explain the evidence. An unsized
  lower-risk investment watchlist checks profitability, valuation, liquidity,
  historical losses and net price growth without promising deposit-like safety.
- **Purchase continuity:** permanent original reasons/horizon/levels survive
  refreshes and top-ups. Trend exits require 2/3/5 completed weak sessions for
  daily/monthly/long-term plans; hard levels and T+2 remain explicit. Dated
  advice history, sticky confirmed exits and re-entry cooldowns are shipped.
- **Recommendation evidence:** first fresh ideas are permanently journaled
  under `decision_v1`; completed-session, fee-aware 100-share simulations track
  entry-zone fills, T+2, gaps, missing data and corporate actions. Dashboard
  score-group outcomes/Wilson intervals are research evidence, not win odds.
- **Fund classification:** mutual funds receive NAV/fund review; company EPS
  placeholders are not treated as deterioration or eligible stock fundamentals.
- **Efficiency:** rolling validity/volume and shared cost/quote reads preserve
  rankings; local full-analysis cProfile time fell 66.284s→24.610s, SELECTs 1541→811.
- **Status details:** `docs/COMPLETION_STATUS.md`

## Completed advisor scope
The AI/advisor half is shipped: SQLite FTS5 RAG with optional live retrieval, the
LLM router with local `claude -p` synthesis and DB-backed budgets/cache, the
four-horizon rashifal/dose advisor, the open -> scored -> reviewed -> retired
prediction journal, read-only/toggleable MeroShare mirroring with CSV fallback,
fee-aware manual auction advice, a bounded read-only MCP server, and matching
FastAPI/React surfaces with tests. Normal/offline mode is the safe default; AI
and live retrieval are explicit opt-ins.

## Key Design Decisions
- **SQLite WAL** for concurrent reads during async ingestion
- **PriceBar PK:** (symbol, business_date, source) — upsert, not insert
- **ReconciledPrice PK:** (symbol, business_date) — single source of truth
- **Decimal for money** — paise precision, avoids float rounding in portfolio
- **Each source isolated** — one source failing never blocks others
- **Async optional** — CLI defaults to sync; `--async` flag calls `asyncio.run()`
- **Cosmetic config only** — no `adjust` or `fill` in config (schema checks existence, not shape)

## Useful Commands
```bash
pytest -q --tb=short           # full suite
ruff check .                   # lint
python -m nepse_trader.cli.main --help  # CLI reference
nepse-trader ingest --async    # concurrent fetch (if installed as script)
nepse-trader dashboard         # DB summary
nepse-trader export csv        # dump tables
```

## Open Questions / Planned
- Docker packaging shipped; image-build verification requires a running Docker daemon
- Postgres storage backend (SQLite-only today)
- **No** broker API integration — NEPSE has no sanctioned retail trading API, so
  execution stays manual. MeroShare access is read-only by design.
