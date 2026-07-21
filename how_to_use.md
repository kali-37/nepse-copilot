# How To Use — NEPSE Trader

A practical, command-by-command guide for operators. For internals see
[`how_it_works.md`](how_it_works.md); for extending the code see
[`developerguide.md`](developerguide.md); for troubleshooting see
[`docs/RUNBOOK.md`](docs/RUNBOOK.md).

> **Scope:** reads *public* NEPSE market data politely for personal/research use.
> No live orders. No bypassing site protections. Commercial use of NEPSE data
> needs a license from Nepal Stock Exchange Ltd. Nothing here is financial advice.

---

## 1. Install

Requires Python ≥ 3.11. With [`uv`](https://github.com/astral-sh/uv):

```bash
cd nepse-trader
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e ".[dev]"
```

Everything below assumes `PY=.venv/bin/python`. The installed console script
`nepse-trader` is equivalent to `python -m nepse_trader.cli.main`.

Verify the install:
```bash
PY=.venv/bin/python
$PY -m pytest -q            # 191 tests, all offline
$PY -m nepse_trader.cli.main --help
```

---

## 2. The mental model (30 seconds)

```
ingest  →  reconcile  →  signal / backtest  →  paper trade
(pull)     (agree)       (decide)              (simulate w/ Nepal fees)
```

1. **ingest** pulls today's (or a past day's) public prices into a local SQLite DB.
2. **reconcile** cross-checks the sources into one trusted price + a confidence score.
3. **signal / backtest** run technical strategies over the reconciled history.
4. **paper** simulates buying/selling with the real Nepal cost + tax model.

`run-daily` chains 1→3 in one command.

---

## 3. Command reference

### `sources` — see what's wired up
```bash
$PY -m nepse_trader.cli.main sources
```
Shows which sources are enabled (in settings) and on/off (in `config/sources.yaml`),
their base URLs, and endpoint counts. ShareSansar is the enabled primary by default.

### `ingest` — pull public data into the DB
```bash
$PY -m nepse_trader.cli.main ingest --date 2026-06-09     # a specific trading day
$PY -m nepse_trader.cli.main ingest                       # today
```
Prints a JSON summary (`per_source` row counts, any `errors`, totals). A failing
source is logged and skipped — it never aborts the run. Zero rows usually means a
weekend/holiday, or a source's layout changed (then re-capture a HAR — see §7).

### `reconcile` — build the trusted consensus
```bash
$PY -m nepse_trader.cli.main reconcile --date 2026-06-09
```
Groups the day's bars by symbol, finds the largest cluster of sources that agree
(within 0.5% by default), writes a consensus price with a `confidence` (share of
sources agreeing on close) and a list of `disputed_fields`. Flags low-confidence
rows in yellow.

### `signal` — generate strategy signals for a symbol
```bash
$PY -m nepse_trader.cli.main signal NABIL --strategy sma_cross
$PY -m nepse_trader.cli.main signal NABIL --strategy rsi --period 14
$PY -m nepse_trader.cli.main signal NABIL --strategy macd
$PY -m nepse_trader.cli.main signal NABIL --strategy bollinger
```
Strategies: `sma_cross`, `rsi`, `macd`, `bollinger`. Tunable params:
`--fast`, `--slow`, `--period`, `--signal` (only the ones a strategy uses).
Reads the symbol's **reconciled** history, so ingest + reconcile a few weeks first
(indicators need warm-up). Prints the last 15 signals and the latest action.

### `stats` — quantitative statistics per symbol
```bash
$PY -m nepse_trader.cli.main stats NABIL,ADBL,HDL
$PY -m nepse_trader.cli.main stats              # top 25 stored symbols
```
Annualized return & volatility, **Sharpe**, **Sortino**, max drawdown, **95% VaR**,
skewness and kurtosis over each symbol's reconciled history. `--periods` sets the
annualization factor (default 252).

### `backtest` — evaluate one strategy with Nepal costs
```bash
$PY -m nepse_trader.cli.main backtest NABIL --strategy sma_cross --fast 20 --slow 50 --cash 100000
$PY -m nepse_trader.cli.main backtest NABIL --strategy macd --fraction 0.5
```
Long-only, same-bar-close execution, full broker/SEBON/DP/CGT applied on every
fill. Reports total return, CAGR, max drawdown, Sharpe, number of trades, win
rate and exposure. `--fraction` deploys only part of cash per entry.

### `screen` — backtest leaderboard across all symbols & strategies
```bash
$PY -m nepse_trader.cli.main screen --rank-by sharpe --top 30
$PY -m nepse_trader.cli.main screen --best-only           # best strategy per symbol
$PY -m nepse_trader.cli.main screen --strategies sma_cross,macd --rank-by total_return_pct
```
Runs the whole strategy panel over every symbol with enough history and ranks the
results (Nepal costs already applied). `--rank-by` ∈ `sharpe | total_return_pct |
cagr_pct | max_drawdown_pct | win_rate_pct`. This is how you "finalize with a
backtest" — let the after-cost numbers choose.

### `run-daily` — the once-a-day report (the main command)
```bash
$PY -m nepse_trader.cli.main run-daily --report data/$(date +%F).md
$PY -m nepse_trader.cli.main run-daily --strategies sma_cross,macd --rank-by cagr_pct
```
Ingests from **all sources**, reconciles, then assembles a full markdown report
with eight sections: market overview/breadth, top movers, reconciliation quality,
multi-strategy actionable signals, per-symbol quant stats, the backtest leaderboard,
the best strategy per symbol, and your paper-portfolio status. Prints a JSON
headline summary to the console. This is the one command to schedule daily (§8).
`--enabled-only` restricts to configured sources; `--top` caps symbols analysed.

### `paper` — simulate trading
```bash
$PY -m nepse_trader.cli.main paper buy  NABIL --price 1000 --qty 100 --date 2026-06-09 --cash 200000
$PY -m nepse_trader.cli.main paper sell NABIL --price 1200 --qty 100 --date 2026-07-15 --cash 200000
$PY -m nepse_trader.cli.main paper status --cash 200000
```
- Buys are rejected if cash is insufficient (fees included).
- Sells are rejected if you don't hold the shares.
- CGT is computed FIFO on the realized gain using the oldest lot's holding period.
- State is rebuilt by **replaying** recorded trades from SQLite, so **keep `--cash`
  consistent** across calls (default Rs 100,000).

> Sanity check: BUY 100 @ 1000 → cash out **100,370**; SELL 100 @ 1200 → cash in
> **118,121.67** (CGT 1,439.33), realized PnL **17,751.67** — matches the official
> worked example to the paisa.

### `har` — discover/verify endpoints from your own captures
```bash
$PY -m nepse_trader.cli.main har analyze   har/captures/sharesansar.har
$PY -m nepse_trader.cli.main har to-config har/captures/chukul.har --source chukul
$PY -m nepse_trader.cli.main har redact    har/captures/nepsealpha.har
```
`analyze` ranks candidate data endpoints; `to-config` emits a `sources.yaml`
snippet; `redact` strips cookies, auth headers, POST bodies, sensitive query
params, and auth-endpoint response bodies so a HAR is safe to keep. See
[`har/HAR_CAPTURE_PLAN.md`](har/HAR_CAPTURE_PLAN.md).

---

## 4. A first full session

```bash
PY=.venv/bin/python
M="$PY -m nepse_trader.cli.main"

# Backfill ~6 weeks of trading days (Mon–Fri), then reconcile each
for d in $(seq 0 60); do
  D=$(date -d "2026-06-09 -$d day" +%F)        # GNU date
  $M ingest --date "$D" >/dev/null
  $M reconcile --date "$D" >/dev/null
done

$M signal NABIL --strategy sma_cross --fast 20 --slow 50
$M backtest NABIL --strategy sma_cross --fast 20 --slow 50 --cash 100000
$M paper buy NABIL --price 1010 --qty 50 --date 2026-06-09 --cash 100000
$M paper status
```

---

## 5. Reading the outputs

- **Reconciliation confidence** — `1.0` means every present source agreed on the
  close within tolerance; `< 1.0` or non-empty `disputed_fields` means sources
  disagreed — treat that symbol's price as soft.
- **Signal action** — `BUY`/`SELL` fire only on a state change (a crossover);
  `HOLD` otherwise. `strength` (0–1) scales with the signal's conviction.
- **Backtest metrics** — `total_return_pct` is net of all Nepal fees & CGT;
  `max_drawdown_pct` is the worst peak-to-trough; `sharpe` annualizes daily
  equity returns; `exposure_pct` is the fraction of days holding a position.

---

## 6. Configuration

Settings come from environment variables (prefix `NEPSE_`) or a `.env` file:

| Variable | Default | Meaning |
|----------|---------|---------|
| `NEPSE_DB_PATH` | `data/nepse.db` | SQLite database path |
| `NEPSE_RAW_CACHE_DIR` | `data/raw` | Where raw HTTP responses are cached (audit) |
| `NEPSE_ENABLED_SOURCES` | `sharesansar,chukul,nepse_official` | Sources the pipeline iterates |
| `NEPSE_MIN_REQUEST_INTERVAL` | `1.5` | Min seconds between requests to the same host |
| `NEPSE_REQUEST_TIMEOUT` | `20` | HTTP timeout (s) |
| `NEPSE_MAX_RETRIES` | `3` | Retry attempts (with backoff) |
| `NEPSE_USER_AGENT` | descriptive UA | Identify yourself honestly |
| `NEPSE_PRICE_AGREEMENT_TOLERANCE` | `0.005` | Relative tolerance for "sources agree" |

Endpoints and the cost model live in YAML you can edit without touching code:
`config/sources.yaml` (per-source endpoints, enable flags) and
`config/cost_model.yaml` (commission slabs, SEBON/DP/CGT rates).

To enable a second source (e.g. MeroLagani):
```bash
# 1) set enabled: true on merolagani in config/sources.yaml
# 2) include it in the iteration set
export NEPSE_ENABLED_SOURCES=sharesansar,merolagani
$PY -m nepse_trader.cli.main ingest --date 2026-06-09
```

---

## 7. When a source breaks (HAR refresh)

Sites change layouts. If `ingest` returns 0 rows on a trading day or wrong data:

1. Capture a fresh HAR per [`har/HAR_CAPTURE_PLAN.md`](har/HAR_CAPTURE_PLAN.md)
   into `har/captures/`.
2. `har analyze` it, then `har to-config --source <name>` and paste the snippet
   into `config/sources.yaml`.
3. `har redact` before keeping any HAR around (they're git-ignored regardless).

---

## 8. Scheduling

NEPSE (2026) trades **Mon–Fri, 11:00–15:00 NPT**; ShareSansar EOD finalizes
~17:45 NPT. Run the daily job in the evening NPT. Example cron (server in UTC,
18:00 NPT = 12:15 UTC):

```cron
15 12 * * 1-5  cd /path/to/nepse-trader && .venv/bin/python -m nepse_trader.cli.main run-daily --report data/$(date +\%F).md >> data/cron.log 2>&1
```

A weekend/holiday simply ingests 0 rows — safe to leave scheduled year-round.

---

## 9. Quick FAQ

- **"No signals for X"** → not enough reconciled history; backfill more days.
- **`403`/`429` in logs** → the source is rate-limiting; the client backs off
  automatically. Run less often / raise `NEPSE_MIN_REQUEST_INTERVAL`. Don't evade it.
- **NEPSE-official returns nothing** → `pip install nepse-scraper`, or use HAR replay.
- **SSL error vs nepalstock** → NEPSE ships an incomplete cert chain; use the
  `nepse-scraper` library which handles it.
- **Where's my data?** → `data/nepse.db` (SQLite) and `data/raw/` (cached responses).
