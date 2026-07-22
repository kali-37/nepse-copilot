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
    strategies.py       — SMA Cross, RSI, MACD, Supertrend, Ichimoku,
                          Donchian Breakout, Mean-reversion
    backtest.py         — Backtester (Nepal costs: broker/SEBON/DP/CGT)
    screen.py           — Multi-symbol, multi-strategy backtest screening
    walkforward.py      — Walk-forward optimisation (expanding window)
    costs.py            — CostEngine (broker 0.4%, SEBON, DP, CGT slabs)
    quant.py            — Sharpe, Sortino, VaR, skew, kurtosis
  trading/
    __init__.py
    portfolio.py        — PaperPortfolio (buy/sell, FIFO lots, realized PnL)
    risk.py             — PositionSizer (Kelly, fixed-fraction, risk-per-trade)
  har/
    __init__.py
    analyzer.py         — HAR capture analysis & endpoint discovery
  alerting/
    __init__.py
    notifier.py         — Telegram / Discord / SMTP alerts
tests/
  test_*.py             — 364 tests, 1 skipped
```

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
- **Tests:** 364 passing, 1 skipped
- **Lint:** ruff clean
- **Schema:** sources.jsonc config validation shipped
- **Last commit:** `feat: CLI dashboard command with DB & portfolio summary`

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
- Docker image for scheduled deployment
- Broker API integration for real orders
- Web UI dashboard
