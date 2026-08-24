# How It Works — NEPSE Trader Internals

This explains the algorithms and design decisions behind every stage. It pairs
with [`developerguide.md`](developerguide.md) (how to extend) and
[`how_to_use.md`](how_to_use.md) (how to operate). File references point at the
real modules under `nepse_trader/`.

---

## 1. End-to-end data flow

```
 enabled sources                  cross-source                 analysis
 ┌───────────────┐   PriceBar[]   ┌──────────────┐  Reconciled  ┌───────────────┐
 │ ShareSansar   │──────────────▶ │  reconcile   │────Price[]──▶│ indicators →  │
 │ MeroLagani    │   (per source) │  (consensus) │              │ strategies →  │
 │ Chukul        │                └──────┬───────┘              │ Signal[]      │
 │ NEPSE/HAR     │                       │ upsert               └──────┬────────┘
 └──────┬────────┘                       ▼                             │
        │ upsert (idempotent)      SQLite storage ◀────────────────────┘
        ▼                          price_bars / reconciled_prices /
   data/raw/*.txt                  signals / paper_trades / ingest_log
   (audit cache)                          │
                                          ▼
                              Backtester / PaperPortfolio
                              (Nepal CostEngine on every fill)
                                          │
                                          ▼
                              reporting (rich + markdown) / Alerter
```

`pipeline.DailyPipeline` is the orchestrator that drives this; `cli/main.py`
exposes each stage as a command.

---

## 2. The politeness & ethics layer (`ingest/base.py`)

Every HTTP call goes through `BaseClient`, which is deliberately *defensive about
the sites it reads*, not aggressive:

- **Per-host throttle** (`_HostThrottle`): enforces a minimum wall-clock gap
  (`NEPSE_MIN_REQUEST_INTERVAL`, default 1.5 s) between requests to the same host,
  using a monotonic clock so it can't be fooled by system-time changes.
- **Capped retries with backoff** (`tenacity`): exponential backoff, max 3
  attempts, only for transport errors and rate-limit signals.
- **Back off, never bypass:** a `403` or `429` raises `RateLimitedError`, which
  triggers a backoff and ultimately surfaces the condition. There is no attempt to
  rotate identities, solve challenges, or defeat WAFs. `5xx` is treated as a
  transient transport error; other `4xx` is a hard `FetchError`.
- **Audit cache:** each raw response body is written best-effort to
  `data/raw/<YYYYMMDD>_<urlhash>.txt`. If two sources later disagree, you can trace
  the discrepancy back to exactly what each returned. Cache failures never break
  ingestion (the write is wrapped and swallowed).
- **Honest identity:** a descriptive `User-Agent` that says what the client is.

### Why we don't touch NEPSE's official token
The official `nepalstock.com` API gates each call behind a short-lived token that
the site reconstructs in the browser from five integer "salts" fed through a WASM
module (the `Authorization: Salter …` scheme). That obfuscation exists to gate
NEPSE's own front-end. We **do not** reimplement or bypass it. Instead
`ingest/nepse_official.py` offers two clean paths: (a) lazily delegate to the
optional MIT-licensed `nepse_scraper` library if the user installs it, or (b)
replay a HAR **the user captured from their own session**. Neither path contains
any token-deobfuscation code.

---

## 3. Source discovery via HAR (`har/analyzer.py`)

A HAR file is a JSON log of a browser session (requests, headers, bodies). The
analyzer turns one into a ranked list of likely *data* endpoints:

- `analyze()` walks `log.entries[]`, classifies each as `json_api`, `html_table`,
  or `other`, and scores it. JSON whose payload is an array or a DataTables
  `{data:[…]}`/`{content:[…]}` shape scores highest, boosted when its keys or URL
  contain market keywords (`symbol`, `ltp`, `turnover`, `floorsheet`, …). Static
  assets (`.js/.css/.png/...`) are zeroed out.
- `_json_sample_keys()` drills through common nested shapes (`data`, `content`,
  `floorsheets.content`, `results`) to surface the row schema.
- `decode_content()` handles base64-encoded HAR bodies transparently.
- `to_config_snippet()` emits a ready-to-paste `sources.yaml` block (method, URL,
  query params, sample keys) at `confidence: medium`.
- `redact()` produces a shareable copy: it clears cookies, strips sensitive
  headers (`cookie`, `authorization`, `x-csrf-token`, …), replaces request POST
  bodies, blanks sensitive query-param values **in both the structured list and
  the URL string**, and blanks the *response* bodies of auth/token endpoints
  (matched on the URL path, so market-data endpoints that merely have `accessToken`
  in their query keep their useful response). Market-data response bodies are
  preserved — they're the point of the capture.

---

## 4. Per-source extraction (`ingest/*.py`)

Each client subclasses `SourceClient` and separates **fetching** (network, via
`BaseClient`) from **parsing** (pure `parse_*` functions). This keeps parsers unit
testable with fixtures and makes every fetch failure degrade to `[]` rather than
crashing the pipeline.

- **ShareSansar (primary):** `parse_today_share_price()` parses the server-rendered
  `table#headFixed` with `selectolax`, mapping columns to `PriceBar` (Close, with
  LTP fallback; Prev.Close; Vol; Turnover; Trans.). `_num`/`_int` strip thousands
  commas and `"-"`. DataTables JSON feeds (`/floorsheet`, `/top-gainers`,
  `/indices-sub-indices`) are parsed from `{data:[…]}`, with `_strip_html` removing
  the HTML anchors ShareSansar wraps symbols in.
- **MeroLagani:** ASP.NET HTML. The parser finds the largest table whose header row
  contains "Symbol"/"LTP" and maps columns *by header name* (robust to column
  reordering).
- **Chukul:** fully config-driven JSON. `_pick(d, *keys)` resolves a value from any
  of several aliases (`symbol|ticker|scrip`, `ltp|last_price|lastTradedPrice|close`,
  …), case-insensitively, and `_as_records` normalizes `list` / `{data}` / `{results}`
  shapes — so the same code works whichever exact shape Chukul returns.
- **NEPSE official / HAR replay:** maps the NEPSE `{content:[…]}` today-price shape
  (or a ShareSansar-shaped JSON) to `PriceBar` via a pure, never-raising mapper.

---

## 5. Reconciliation (`ingest/reconcile.py`)

The reason to pull the same data from several sites is to *trust* it. For each
`(symbol, business_date)` group:

1. For each numeric field (`open/high/low/close/previous_close/volume/turnover`),
   collect the `(source, value)` pairs that are non-null.
2. **Greedy clustering:** for each value, gather all values within a *relative*
   tolerance (`|a−b| / max(|a|,|b|) ≤ tol`, default 0.5%). The largest such cluster
   wins; its **mean** is the agreed value.
3. A field is **disputed** if any present value falls outside the winning cluster.
4. **Confidence** = (sources in the close's winning cluster) / (sources present).

So three sources reporting 500.0 / 500.5 / 500.2 yield confidence 1.0 (all within
0.5%); a fourth at 650 lowers confidence to 0.75 and flags `close` as disputed,
while the consensus stays near 500 (the outlier is excluded from the mean). A
single source trivially agrees with itself (confidence 1.0) but you'll typically
gate decisions on having ≥ 2 agreeing sources. `ReconciledPrice.is_trustworthy`
encodes the rule `confidence ≥ 0.5 and no disputed fields`.

---

## 6. Indicators (`analysis/indicators.py`)

Pure, dependency-free functions over `list[float]`. Each returns a list aligned to
the input, with `None` during the warm-up period, so indicators can be zipped with
dated bars safely.

- **SMA** — rolling mean via a running window sum (O(n)).
- **EMA** — seeded with the SMA of the first `period` values, then
  `EMA_i = price_i·k + EMA_{i−1}·(1−k)`, `k = 2/(period+1)`.
- **RSI (Wilder)** — initial average gain/loss over `period`, then Wilder
  smoothing `avg = (avg·(period−1) + current)/period`. Returns 0–100; 100 when
  there are no losses, 0 when no gains.
- **MACD** — `EMA(fast) − EMA(slow)`; the signal line is an EMA of the *defined*
  portion of the MACD line (indices realigned afterwards); histogram = MACD −
  signal. Returns three aligned series.
- **Bollinger** — SMA middle band; **population** standard deviation
  (`Σ(x−mean)²/period`) for the ±`num_std` bands. (Population, not sample — chosen
  for stability and matching common charting defaults.)
- **ATR (Wilder)** — true range smoothed à la RSI.

---

## 7. Strategies (`analysis/strategies.py`)

All strategies share a base that (a) carries the last valid close forward over
gap days for indicator continuity but **masks** those days so no signal is emitted
on a no-close bar, and (b) emits `BUY`/`SELL` only on a **state change**, `HOLD`
otherwise.

- **SMA cross** — state = sign of (fast − slow). The first bar where fast leads
  slow opens a long (BUY); the first bar it drops below exits (SELL). Treating the
  *initial* establishment of the trend as a state change is what lets a series that
  starts mid-uptrend produce a BUY.
- **RSI** — BUY when RSI crosses up out of oversold; SELL when it crosses down out
  of overbought.
- **MACD** — **zero-line crossover** of the MACD line: long when MACD turns
  positive, exit when negative. (A pure signal-line cross is degenerate on a
  constant-slope ramp where the histogram is identically zero, so the signal line
  and histogram are computed for reporting only — this is documented in the class.)
- **Bollinger** — mean-reversion: BUY when close crosses below the lower band,
  SELL when it crosses above the upper band.
- **Composite** — polls each sub-strategy's signal for the date, computes
  `net = (#BUY − #SELL)/N`, and emits BUY/SELL when `net` clears the
  buy/sell thresholds. Strength = `|net|`; the reason lists contributors.

`STRATEGIES` is the registry; `build_strategy(name, **kwargs)` is the factory.

---

## 8. The Nepal cost engine (`analysis/costs.py`)

The fee/tax stack applied to every fill (rates in `config/cost_model.yaml`):

- **Broker commission** — a single *slab* rate on the whole transaction amount,
  not marginal. Slabs (NPR): ≤50k → 0.36%, ≤500k → 0.33%, ≤2m → 0.31%, ≤10m →
  0.27%, >10m → 0.24%, with a **Rs 10** floor. A boundary amount belongs to the
  **lower (higher-rate)** tier — exactly Rs 50,000 is 0.36% — implemented by
  matching the first slab whose inclusive `max_amount` covers the amount (the final
  open slab catches the rest).
- **SEBON fee** — 0.015% of the amount.
- **DP charge** — flat Rs 25 per scrip per settlement.
- **CGT** — charged on the **sell leg, on realized gain only**. Individual: 7.5%
  if held ≤ 365 days, 5% if held > 365 days (a sale on exactly the 365th day is
  short-term); institutional 10%. No CGT on a loss.

`compute(side, price, qty, …)` returns a `CostBreakdown` where for a BUY
`net_amount = gross + fees` (cash out) and for a SELL `net_amount = gross − fees −
CGT` (cash in). Money is rounded to paisa (2 dp) at the end.

**Worked example (verified by tests):** BUY 100 @ 1000 → gross 100,000, commission
330, SEBON 15, DP 25 ⇒ **100,370** out (basis 1003.70/share). SELL 100 @ 1200 →
gross 120,000, fees 439, gain `119,561 − 100,370 = 19,191`, CGT @ 7.5% = 1,439.33
⇒ **118,121.67** in. Net profit **17,751.67**.

---

## 9. Backtester (`analysis/backtest.py`)

Long-only, event-driven, **same-bar close** execution (documented in the code):

- On a BUY when flat, it sizes the position by converging on the actual
  `CostEngine` net cost per share (seeded from the bare price to avoid the flat-DP /
  min-commission distortion a 1-share probe would introduce), reduces cash by the
  buy's `net_amount`, and records the entry basis + date.
- On a SELL when long, it liquidates all shares, passing `buy_cost_basis` and
  `holding_days` so CGT is correct, and records a trade dict
  (`pnl, return_pct, holding_days, fees, cgt`).
- Equity is marked each bar (`cash + shares·close`, falling back to entry price if
  a bar has no close). Any open position is liquidated at the last close for
  `final_equity` — and if the final bar has *no* close, the residual is marked at
  entry price (not zero), so the reported return can't collapse to a spurious −100%.
- Metrics: `total_return_pct`, CAGR (from days/365.25), max drawdown (largest
  peak-to-trough on the equity curve), Sharpe (mean/σ of daily equity returns ×
  √annualization, 0 when σ = 0), win rate, and exposure (fraction of bars holding).

---

## 10. Paper portfolio (`trading/portfolio.py`)

A cash + positions ledger with realistic accounting:

- **WAC** — `avg_cost` is the weighted-average per-share cost *including* buy-side
  fees, so position cost basis is always fee-inclusive.
- **FIFO lots** — each buy pushes a lot (date, qty, cost/share). A sell consumes
  the oldest lots first to determine the basis of the sold quantity *and* the
  holding period (from the oldest contributing lot), which drives short- vs
  long-term CGT.
- **Guards** — rejects non-positive qty/price, oversell, and underfunded buys.
- **Persistence by replay** — trades are written to SQLite; portfolio state is
  reconstructed by replaying them through a fresh ledger (no extra state file to
  drift). The CLI replays with `storage=None` to rebuild, then persists only the
  newly executed trade.

---

## 11. Storage & idempotency (`storage/db.py`)

SQLite (WAL mode). The key invariant is **idempotent daily ingestion**: a price
bar is unique on `(symbol, business_date, source)`, so re-running a day upserts
rather than duplicates. Reconciled prices are keyed `(symbol, business_date)`;
signals on `(symbol, business_date, strategy)`. Every ingest run is logged to
`ingest_log` (source, rows, status, message, timestamp) for an audit trail. Reads
return typed models, not raw rows.

---

## 12. Failure philosophy

The pipeline assumes the open web is flaky and adversarial-by-accident:

- A source that errors is logged to `ingest_log` and skipped; other sources still
  ingest. (`DailyPipeline.ingest` isolates each source in its own try/except.)
- Parsers never raise on malformed input — they return `[]`/`None`, so one bad row
  or a layout change can't take down the run.
- The audit cache and reconciliation confidence give you the tools to *detect* when
  a source has silently started returning wrong data, rather than trusting it blindly.

## 13. Advisor and confidence

`advisor/plan.py` computes entry zones, ATR stops, targets, lot-rounded quantity,
T+2 settlement and fee/tax-aware expected net PnL. `advisor/rashifal.py` composes
the selected card horizon with a four-way `advisor/doses.py` partition over the
same capital. The dose contract is `3/10/22/250` trading days and allocations
must sum to at most one; a card is assigned once, never copied into multiple
headline totals.

`advisor/confidence.py` owns the public scale. Market forecasts are capped below
certainty; only `certain()` may produce `1.0` for arithmetic facts. Historical
confidence uses a prior plus Wilson lower-bound shrinkage, and `blend()` takes
the weakest link. Longer dose horizons receive an explicit confidence haircut.
AI providers can write prose and citations only; deterministic numbers are
already persisted before narrative is attached.

## 14. Prediction journal and outcomes

`save_rashifal()` writes each call before it can be resolved. The journal then
transitions `open -> scored -> reviewed -> retired`. `advisor/outcomes.py` scans
reconciled bars and checks the stop before the target when both occur on one bar;
only `TARGET_HIT` contributes a hit. `UNRESOLVED` and `NO_DATA` remain visible but
never enter calibration. Realized net PnL uses the same `CostEngine` path as
expected PnL, so the journal compares like with like. Distilled lessons are
stored in `prediction_lessons` and indexed into the local SQLite FTS5 corpus.

## 15. MeroShare, auction and modes

`meroshare/` is a read-only mirror. Credentials are resolved from env/`.env` or
an optional keyring, redacted at every boundary, and never persisted. The API
and MCP mask demat identifiers; CSV import is the credential-free fallback. The
integration is explicitly toggleable and failed syncs are atomic, leaving the
last good mirror intact. `advisor/auction.py` calculates bid ceilings and
break-even after Nepal fees; it has no placement path.

Normal mode constructs a local-only pipeline with no network leg. AI mode adds
optional local Claude CLI/OpenRouter/Anthropic providers and RAG evidence; if a
provider or budget is unavailable, the deterministic report survives with a
degradation banner. MCP exposes bounded read-only tools over JSON-RPC stdio.
