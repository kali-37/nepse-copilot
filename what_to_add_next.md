# What To Add Next — NEPSE Trader Roadmap

> Historical roadmap. History ingestion, adjustments, fundamentals filters,
> portfolio/walk-forward surfaces, broker/sector views and ingestion reliability
> are now implemented. See [current completion status](docs/COMPLETION_STATUS.md).

A prioritized, concrete backlog. Each item states **why**, a rough **effort**
(S ≤ 1 day, M ≤ 1 week, L > 1 week), and **where** in the codebase it lands. Items
are ordered by value-to-effort within each tier.

---

## Tier 1 — highest value, do first

### 1.1 Corporate-action adjustment (bonus / rights / splits) — **L**, `ingest/` + `analysis/`
**Why:** NEPSE issues frequent bonus shares and rights — unadjusted price series
produce fake gaps that wreck indicators, backtests, and CGT. This is the single
biggest correctness gap for Nepal specifically.
**Where:** a new `corporate_actions` table + an adjustment pass that back-adjusts
`reconciled_prices` (and a parallel "adjusted close" column). Source the events
from ShareSansar/MeroLagani announcement pages (capture via HAR first).

### 1.2 Verify & enable Chukul + NepseAlpha sources — **M**, `ingest/chukul.py`, new `ingest/nepsealpha.py`
**Why:** more independent sources = stronger reconciliation and resilience ("all
data regardless of website"). Chukul is a real `/v1/` JSON API; NepseAlpha has a
TradingView UDF datafeed with clean OHLC history.
**Where:** capture HARs (`har/HAR_CAPTURE_PLAN.md`), confirm paths with
`har to-config`, flip `enabled: true`, add a NepseAlpha client + tests.

### 1.3 Holiday / trading-calendar awareness — **M**, new `calendar.py`
**Why:** today the bot infers "closed" from 0 rows. A real Bikram-Sambat-aware
calendar (weekends + gazetted + ad-hoc holidays) lets `run-daily` skip cleanly,
backfill only real trading days, and annualize stats with the correct period count.
**Where:** a calendar module + an optional holiday feed; wire into `pipeline` and
the `periods_per_year` used by `quant`.

### 1.4 Alerting integrations (Telegram / Discord / email) — **S–M**, `reporting.py`
**Why:** a daily report is only useful if it reaches you. The `Alerter` already has
a webhook seam; add first-class Telegram/Discord/SMTP senders gated on config.
**Where:** extend `Alerter` with pluggable backends; `run-daily --alert`.

---

## Tier 2 — strong analytical upside

### 2.1 Multi-symbol portfolio backtest — **L**, `analysis/backtest.py`
**Why:** the current backtester is single-symbol. A portfolio engine (capital
allocation, rebalancing, per-name position limits) lets you test real strategies,
not just per-ticker signals.
**Where:** a `PortfolioBacktester` that consumes signals across symbols and shares
one cash account, reusing `CostEngine` and the metrics code.

### 2.2 Risk-managed position sizing & stops — **M**, `analysis/strategies.py` + backtest
**Why:** entries without risk management overstate performance. Add ATR-based
sizing, fixed-fractional risk, stop-loss / take-profit, and max-exposure caps.
**Where:** a sizing/risk layer the backtester and paper portfolio both consult.

### 2.3 Walk-forward optimization & parameter sweeps — **M**, new `analysis/optimize.py`
**Why:** picking strategy params on the full history overfits. Walk-forward (train
on a window, test out-of-sample, roll) gives honest, finalized parameters.
**Where:** a sweep harness over `build_strategy` params + the screener, reporting
in-sample vs out-of-sample metrics.

### 2.4 More strategies — **S each**, `analysis/strategies.py`
Supertrend, Ichimoku, Donchian breakout, mean-reversion z-score, dual-momentum.
Each is a one-class addition + registry entry + tests (see the developer guide).

### 2.5 Fundamentals ingestion (EPS, P/E, book value, dividends) — **M**, `ingest/`
**Why:** enables value/quality screens and fundamental filters on technical signals.
**Where:** MeroLagani `CompanyDetail` and Chukul fundamentals endpoints → a
`fundamentals` table + a `screen --fundamental` filter.

---

## Tier 3 — usability, reach, and scale

### 3.1 Web dashboard — **L**, new `web/` (FastAPI + charts)
Serve the daily report, equity curves, the leaderboard, and per-symbol charts.
Read-only over the existing SQLite DB; no new write paths.

### 3.2 Sector & index analytics — **M**, `analysis/` + `reporting.py`
Sector breadth, sector rotation, index/sub-index trend, market-cap-weighted
internals — NEPSE is very sector-driven, so this is high-signal.

### 3.3 Data export (CSV / Parquet) — **S**, `cli/main.py`
`export --table reconciled_prices --format parquet` for downstream analysis in
pandas/R.

### 3.4 Incremental / smart ingestion — **S**, `pipeline.py`
Skip dates already fully ingested; detect when a source silently changed shape
(row-count anomaly vs the audit cache) and warn.

### 3.5 Floorsheet analytics (broker flow) — **M**, `ingest/` + `analysis/`
Aggregate the floorsheet into net broker buy/sell pressure per symbol — a popular,
genuinely NEPSE-specific signal.

---

## Tier 4 — research extensions

- **ML signal layer** (`analysis/ml.py`): features from indicators/quant stats →
  a simple classifier for next-day direction, with strict walk-forward validation.
- **Pairs / statistical arbitrage:** use the existing `correlation`/`beta` to find
  cointegrated pairs within sectors.
- **Regime detection:** volatility/trend regimes to gate strategy selection.
- **Monte-Carlo / bootstrap** on the equity curve for confidence intervals on
  backtest metrics.

---

## How to pick up an item

1. Read the relevant module + its tests (one `test_*.py` per module).
2. Keep the parse/fetch separation and the "degrade to `[]`, never crash" rule.
3. Add tests in the same change; keep `pytest` + `ruff` green.
4. If it touches money/tax, the cost worked-example test must still hold to the paisa.
5. Update the docs (`how_it_works.md` / `how_to_use.md`) and this roadmap.

For engineering-quality upgrades (CI, typing, async, Decimal money, packaging),
see [`make_evenBetter.md`](make_evenBetter.md).
