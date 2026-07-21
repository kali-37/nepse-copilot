# Capabilities — NEPSE Trader

What the system can and cannot do, stated precisely. For how to operate it see
[`how_to_use.md`](how_to_use.md); for internals see
[`how_it_works.md`](how_it_works.md).

> **Validated on live data:** a clean run for 2026-05-19 ingested **356 bars from
> ShareSansar + 100 from MeroLagani** (Chukul / NEPSE-official returned 0 without
> setup, as designed), and all **100 symbols covered by both sources agreed on
> the close** within tolerance (reconcile confidence 1.0, zero disputes).

---

## 1. Capability matrix

| Area | Capability | Status |
|------|-----------|--------|
| **Ingestion** | Pull whole-market EOD prices from ShareSansar (HTML) | ✅ live-verified |
| | Pull prices + indices from MeroLagani (HTML) | ✅ live-verified |
| | Pull from Chukul (`/v1/` JSON) | ⚙️ ready, endpoints need HAR verification |
| | Pull NEPSE-official via `nepse-scraper` lib or your HAR | ⚙️ optional, user-enabled |
| | "All sources" mode — scrape every site, merge what responds | ✅ |
| | Per-source failure isolation (one site down ≠ run fails) | ✅ |
| | Historical backfill by date | ✅ (ShareSansar `?date=`) |
| **Data quality** | Cross-source reconciliation with confidence + dispute flags | ✅ live-verified |
| | Idempotent daily storage (re-runs upsert, never duplicate) | ✅ |
| | Raw-response audit cache for traceability | ✅ |
| **Indicators** | SMA, EMA, RSI (Wilder), MACD, Bollinger, ATR | ✅ |
| **Strategies** | SMA cross, RSI, MACD (zero-line), Bollinger, Composite vote | ✅ |
| **Quant stats** | Ann. return/vol, Sharpe, Sortino, max DD, skew, kurtosis, 95% VaR, beta, correlation | ✅ |
| **Backtesting** | Long-only, event-driven, full Nepal costs per fill | ✅ |
| | Strategy × symbol **screening leaderboard** (ranked) | ✅ |
| **Cost/tax** | Commission slabs, SEBON, DP, CGT (short/long/institutional) | ✅ paisa-exact |
| **Paper trading** | WAC positions, FIFO lots, CGT by holding period | ✅ |
| **Reporting** | One-shot daily report (8 sections) in markdown + console | ✅ |
| | Webhook alerts (off unless configured) | ✅ |
| **HAR toolkit** | Analyze captures, emit config, redact secrets | ✅ |
| **Automation** | Single `run-daily` command for cron | ✅ |
| **Live order placement** | — | ❌ by design (no sanctioned API) |

---

## 2. Data & coverage

- **Universe:** the full set of listed securities ShareSansar publishes (~356 on a
  recent day), with a ~100-symbol overlap from MeroLagani used for cross-validation.
- **Granularity:** end-of-day OHLCV, previous close, volume, turnover, trades;
  plus indices and (where exposed) floorsheet transactions and top movers.
- **History:** as deep as you backfill — ShareSansar serves arbitrary past trading
  dates, so you can build years of EOD history.
- **Freshness:** designed for one EOD run per day after ShareSansar finalizes
  (~17:45 NPT). Intraday/live polling is intentionally out of scope (see §8).

---

## 3. Analytical capabilities

- **Technical indicators** — six core indicators as pure, warm-up-aware functions.
- **Strategies** — five built-in (four trend/mean-reversion + a composite voter),
  all long-only, emitting on state changes; extend via a one-class recipe.
- **Quantitative statistics** (`stats` command) — for any symbol set:
  annualized return & volatility, **Sharpe** and **Sortino** ratios, **maximum
  drawdown**, **historical 95% VaR**, **skewness** and **kurtosis** of returns,
  plus **beta/correlation** helpers for relative analysis.

---

## 4. Backtesting & screening

- **Backtester** — long-only, same-bar-close execution, position sizing that
  converges on the true post-fee cost per share; metrics: total return, CAGR, max
  drawdown, **Sharpe**, win rate, exposure. **Every simulated trade pays the full
  Nepal fee + CGT stack**, so results are net, not gross.
- **Screening leaderboard** (`screen` command) — runs the whole strategy panel
  across the whole symbol universe, ranks by Sharpe (or return / CAGR / drawdown /
  win rate), and can collapse to the single best strategy per symbol. This is how
  you "finalize with a backtest" — let the after-cost numbers choose.

---

## 5. Cost & tax fidelity

Paisa-exact, config-driven (`config/cost_model.yaml`), verified by a worked-example
test: commission slabs (0.36/0.33/0.31/0.27/0.24%, Rs 10 floor, boundary→lower
tier), SEBON 0.015%, DP Rs 25, CGT 7.5% (≤365d) / 5% (>365d) / 10% institutional on
realized gain, T+2. Boundary cases (exactly Rs 50,000; exactly 365 days) are handled
correctly and regression-tested.

---

## 6. The once-a-day report

`run-daily` produces a single markdown report with eight sections:
**Market overview** (advancers/decliners/turnover/reconcile quality) ·
**Top movers** · **Reconciliation quality** · **Actionable signals** (multi-strategy) ·
**Quantitative stats** · **Backtest leaderboard** · **Best strategy per symbol** ·
**Paper portfolio**. Plus a machine-readable JSON summary to the console for
logging/alerting. One command, scheduled once a day.

---

## 7. Quality & correctness guarantees

- **191 automated tests, all offline**, plus `ruff` lint clean.
- Adversarially reviewed (multi-dimension, each finding independently verified);
  five confirmed defects fixed with regression tests.
- The headline cost worked example is pinned to the paisa.
- Reconciliation validated against **real, independently scraped** data (100%
  cross-source close agreement on the overlap).

---

## 8. Explicit non-capabilities (by design)

- **No live order placement.** NEPSE has no sanctioned retail trading API; this is
  a research/paper tool only. Nothing here is financial advice.
- **No protection bypass.** It will not reconstruct NEPSE's obfuscated token,
  solve CAPTCHAs, defeat WAFs, or evade rate limits — it backs off on 403/429.
- **No intraday/tick streaming** out of the box (EOD-oriented; a polling/websocket
  layer is a documented future addition).
- **No corporate-action adjustment yet** (bonus/rights/splits) — raw prices are
  stored as published; see [`what_to_add_next.md`](what_to_add_next.md).
- **No guaranteed source uptime.** Sites change layouts and rate-limit; the HAR
  toolkit + multi-source design are the mitigation, not a guarantee.
- **Data licensing.** NEPSE data is licensed by Nepal Stock Exchange Ltd; commercial
  or redistributed use requires a license.

---

## 9. Performance characteristics

- Pure-Python, dependency-light; indicators/stats are O(n) over a symbol's history.
- SQLite (WAL) storage; a full-universe daily ingest + reconcile + report runs in
  seconds-to-low-minutes depending on network and how many sources are enabled.
- Politeness throttle (default 1.5 s/host) bounds request rate by design — the tool
  is built to be a good citizen, not to be fast at the sites' expense.
