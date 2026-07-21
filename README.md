# NEPSE Trader

**Expert-grade NEPSE public-data aggregation, analysis, backtesting and paper-trading engine.**

NEPSE Trader collects *publicly available* Nepal Stock Exchange market data from
multiple Nepali sources, **cross-validates** it so you can trust it ("genuine
information"), computes technical indicators and strategy signals, **backtests**
with an accurate Nepal cost & tax model, and runs a **paper-trading** portfolio
with full fee/CGT accounting. It also ships a **HAR toolkit** to discover and
verify each site's real data endpoints from your own browser captures.

> ### Scope, ethics & legality — read this first
> - This tool reads **public** market data and is for **personal / research /
>   educational** use. NEPSE market data is ultimately licensed by Nepal Stock
>   Exchange Ltd — **obtain a license for any commercial or redistributed use.**
> - It is **polite by design**: per-host rate limiting, capped retries, a
>   descriptive User-Agent, and it **honours `robots.txt`**. It does **not**
>   bypass authentication, CAPTCHAs, WAFs, or rate limits. On `403`/`429` it
>   backs off instead of evading.
> - NEPSE's official `/api/nots/` endpoints sit behind an obfuscated token that
>   gates NEPSE's own front-end. **We do not reimplement or bypass it.** Use the
>   optional MIT-licensed `nepse-scraper` library, or replay a HAR **you**
>   captured from **your own** session.
> - There is **no live order placement** — NEPSE has no sanctioned retail trading
>   API. Signals and trades are **paper only**. Nothing here is financial advice.

---

## Documentation

| Doc | For |
|-----|-----|
| [`how_to_use.md`](how_to_use.md) | Operators — every command, with examples |
| [`how_it_works.md`](how_it_works.md) | The algorithms & design decisions, stage by stage |
| [`developerguide.md`](developerguide.md) | Contributors — contracts and extension recipes |
| [`it's_capiblity.md`](it's_capiblity.md) | What it can / cannot do (capability matrix) |
| [`what_to_add_next.md`](what_to_add_next.md) | Prioritized feature roadmap |
| [`make_evenBetter.md`](make_evenBetter.md) | Engineering-quality upgrades |
| [`docs/RUNBOOK.md`](docs/RUNBOOK.md) | Day-to-day operations & troubleshooting |
| [`har/HAR_CAPTURE_PLAN.md`](har/HAR_CAPTURE_PLAN.md) | Per-site HAR capture playbook |

## Architecture

```
                  ┌─────────────────────────── ingestion (polite HTTP) ───────────────────────────┐
  ShareSansar ──▶│ ShareSansarClient  MeroLaganiClient  ChukulClient  NepseAlpha  NepseScraper │
  MeroLagani  ──▶│  (HTML + JSON)       (HTML)          (JSON, config)  (UDF JSON)  (HAR / lib) │
  Chukul      ──▶│  + FundamentalsClient (EPS, PE, PBV, market cap)                              │
  NepseAlpha  ──▶└───────────────────────────────┬────────────────────────────────────────────────┘
                                                  ▼
                              reconcile_bars()  →  cross-source consensus + confidence
                              adjust_prices()   →  corporate-action back-adjustment
                                                  │
                          ┌────────────────────────┼───────────────────────────┬──────────────────┐
                          ▼                         ▼                           ▼                  ▼
                    SQLite storage          indicators + strategies        Nepal CostEngine    Calendar
                    (idempotent upsert)      (8 strategies incl.             (slabs, SEBON,    (trading days,
                          │                 Supertrend, Ichimoku,            DP, CGT, stops)    holidays)
                          │                 Donchian, Mean-rev)                                  │
                          │                         │                           │                  │
                          └──────────┬──────────────┴─────────────┬─────────────┘──────────────────┘
                                     │                           │
                               ┌─────┴─────┐              PaperPortfolio
                               │           │              (WAC + FIFO CGT)
                         Backtester    Risk sizing
                         (single-sym)  (stop-loss,      Walk-forward
                                       take-profit,     optimisation
                          Portfolio    circuit clamp,   (grid search,
                          (multi-sym)  lot rounding)    expanding/rolling)
                               │           │
                               └─────┬─────┘
                                     ▼
                        reporting (rich + markdown) + Alerter (Telegram, Discord, SMTP)
```

Key modules:

| Module | Responsibility |
|--------|----------------|
| `nepse_trader/models.py` | Pydantic data contracts (PriceBar, IndexValue, Signal, …) |
| `nepse_trader/config.py` | Settings + `config/sources.yaml` + `config/cost_model.yaml` |
| `nepse_trader/ingest/base.py` | Polite HTTP client (throttle, retries, raw-cache) + `SourceClient` |
| `nepse_trader/ingest/*.py` | Per-source clients (ShareSansar primary) |
| `nepse_trader/ingest/reconcile.py` | Cross-source consensus + confidence |
| `nepse_trader/storage/db.py` | SQLite (idempotent daily upserts) |
| `nepse_trader/calendar.py` | NEPSE trading calendar (holidays, next/prev trading day) |
| `nepse_trader/analysis/indicators.py` | SMA, EMA, RSI, MACD, Bollinger, ATR, Supertrend, Donchian, Ichimoku (pure) |
| `nepse_trader/analysis/strategies.py` | SMA cross, RSI, MACD, Bollinger, Supertrend, Ichimoku, Donchian, Mean-reversion + composite voting |
| `nepse_trader/analysis/costs.py` | Nepal commission/SEBON/DP/CGT engine |
| `nepse_trader/analysis/backtest.py` | Event-driven backtester w/ Nepal costs + stop-loss/take-profit |
| `nepse_trader/analysis/risk.py` | Position sizing, stop-loss/take-profit, exposure limits, circuit-limit aware |
| `nepse_trader/analysis/portfolio.py` | Multi-symbol portfolio backtester with equal-weight allocation |
| `nepse_trader/analysis/walkforward.py` | Walk-forward optimisation (expanding/rolling windows, grid search) |
| `nepse_trader/ingest/nepsealpha.py` | NepseAlpha TradingView UDF datafeed client |
| `nepse_trader/ingest/fundamentals.py` | MeroLagani fundamentals (EPS, PE, PBV, market cap, 52W range) |
| `nepse_trader/trading/portfolio.py` | Paper portfolio (WAC, FIFO lots for CGT) |
| `nepse_trader/reporting.py` | Markdown/rich reports + optional webhook alert (Telegram, Discord, SMTP) |
| `nepse_trader/har/analyzer.py` | HAR → ranked endpoints, config snippet, redaction |
| `nepse_trader/config_validation.py` | JSON Schema validation for config YAML files |
| `nepse_trader/pipeline.py` | Daily orchestration |
| `nepse_trader/cli/main.py` | Typer CLI (run-daily, paper, corporate-actions, fundamentals, har) |

## Install

Requires Python ≥ 3.11. Using [`uv`](https://github.com/astral-sh/uv):

```bash
cd nepse-trader
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e ".[dev]"
```

Optional (NEPSE-official ingestion via the MIT library):
```bash
uv pip install --python .venv/bin/python "nepse-scraper"
```

## Quick start

```bash
PY=.venv/bin/python

# 1. Pull a trading day's data from EVERY source and merge -> SQLite
$PY -m nepse_trader.cli.main ingest --date 2026-06-09 --all-sources

# 2. Reconcile across sources (writes a confidence-scored consensus)
$PY -m nepse_trader.cli.main reconcile --date 2026-06-09

# 3. Signals for a symbol with a strategy
$PY -m nepse_trader.cli.main signal NABIL --strategy sma_cross

# 4. Quantitative stats (Sharpe/Sortino/VaR/maxDD/skew/kurtosis)
$PY -m nepse_trader.cli.main stats NABIL,ADBL,HDL

# 5. Backtest a strategy (Nepal costs applied) ...
$PY -m nepse_trader.cli.main backtest NABIL --strategy macd --cash 100000
#    ... or screen ALL strategies across ALL symbols, ranked by Sharpe
$PY -m nepse_trader.cli.main screen --rank-by sharpe --best-only

# 6. Paper trading
$PY -m nepse_trader.cli.main paper buy NABIL --price 500 --qty 100 --date 2026-06-09
$PY -m nepse_trader.cli.main paper status

# 7. THE once-a-day run: ingest(all sources) -> reconcile -> full report bundle
#    (market breadth, movers, reconcile quality, signals, quant stats, leaderboard)
$PY -m nepse_trader.cli.main run-daily --report data/$(date +%F).md

# 8. HAR workflow (discover/verify endpoints from your own capture)
$PY -m nepse_trader.cli.main har analyze har/captures/sharesansar.har
$PY -m nepse_trader.cli.main har to-config har/captures/chukul.har --source chukul
$PY -m nepse_trader.cli.main har redact har/captures/nepsealpha.har
```

The console script `nepse-trader` is also installed (equivalent to
`python -m nepse_trader.cli.main`).

## Nepal cost & tax model

`config/cost_model.yaml` (verified June 2026; update if SEBON/NEPSE revise):

- **Broker commission** (charged on the whole amount at the applicable slab):
  0–50k → 0.36% · 50k–500k → 0.33% · 500k–2m → 0.31% · 2m–10m → 0.27% · >10m → 0.24%,
  with a **Rs 10** minimum.
- **SEBON fee** 0.015% · **DP charge** Rs 25/scrip/settlement.
- **CGT** (sell side, on realized gain): individual **7.5%** (held ≤365d) / **5%** (>365d),
  institutional **10%**. Settlement **T+2**.

Worked example (individual, short-term): BUY 100 @ 1000 → cash out **Rs 100,370**
(basis 1003.70/sh); SELL 100 @ 1200 → CGT Rs 1,439.33, net received **Rs 118,121.67**.

## Daily automation

NEPSE trades **Mon–Fri, 11:00–15:00 NPT** (2026 schedule). Schedule the daily run
after close (data finalizes ~17:45 NPT). Example cron (system local time):

```cron
# 18:15 NPT, Mon–Fri  (adjust to your server's timezone)
15 18 * * 1-5  cd /path/to/nepse-trader && .venv/bin/python -m nepse_trader.cli.main run-daily --report data/$(date +\%F).md
```

## Data sources & reliability

| Source | Role | Notes |
|--------|------|-------|
| **ShareSansar** | **primary** | Permissive `robots.txt`; `/today-share-price?date=` whole-market EOD HTML; clean DataTables JSON for indices/floorsheet/movers |
| MeroLagani | secondary | ASP.NET HTML tables (StockQuote/Indices) |
| Chukul | optional | `api.chukul.com/v1/` JSON — **verify paths via HAR first** |
| NEPSE official | optional | Obfuscated token; via `nepse-scraper` lib or your HAR replay only |

See `har/HAR_CAPTURE_PLAN.md` for the per-site capture playbook.

## Testing

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
```

## Disclaimer

For research and education. Market data may be delayed or inaccurate; always
verify against the official source for anything material. No warranty; not
financial advice; respect each site's terms and NEPSE's data licensing.
