# NEPSE Trader — Operations Runbook

Day-to-day operation, scheduling, and troubleshooting. Read the top-of-`README`
ethics/scope note first — this tool reads **public** data politely and does
**not** place live orders or bypass any site protection.

## 1. Daily lifecycle

NEPSE trades **Sunday–Thursday, 11:00–15:00 NPT** (UTC+5:45); Friday and
Saturday are non-trading days (`nepse_trader/calendar.py`). EOD data on
ShareSansar finalizes roughly **17:45 NPT**. So the daily job should run in the
early evening NPT.

```bash
PY=.venv/bin/python

# Full loop for today (ingest -> reconcile -> signals -> markdown report)
$PY -m nepse_trader.cli.main run-daily --strategies sma_cross --report data/$(date +%F).md

# Or step by step (useful when debugging a single stage):
$PY -m nepse_trader.cli.main ingest --date 2026-06-09
$PY -m nepse_trader.cli.main reconcile --date 2026-06-09
$PY -m nepse_trader.cli.main signal NABIL --strategy macd
```

### Backfill several past trading days
ShareSansar's `today-share-price` accepts a `date`, so you can backfill:
```bash
for d in 2026-06-02 2026-06-03 2026-06-04 2026-06-05 2026-06-08 2026-06-09; do
  $PY -m nepse_trader.cli.main ingest --date "$d"
  $PY -m nepse_trader.cli.main reconcile --date "$d"
done
```
You need a few weeks of history before SMA(50)/RSI(14)/MACD warm up enough to
emit signals or backtest meaningfully.

## 2. Scheduling (cron)

`cron` runs in the server's local time — convert from NPT (UTC+5:45). The 7-day
limit on the in-app scheduler does **not** apply to system cron.

```cron
# Example: server in UTC. 18:00 NPT = 12:15 UTC. Sunday–Thursday (cron 0-4).
15 12 * * 0-4  cd /path/to/nepse-trader && .venv/bin/python -m nepse_trader.cli.main run-daily --report data/$(date +\%F).md >> data/cron.log 2>&1
```

A non-trading day (weekend/holiday) simply ingests 0 rows and the job is a no-op —
safe to leave scheduled year-round. NEPSE holidays follow the Bikram Sambat
calendar and ad-hoc government declarations; the bot does not hardcode them.

## 3. Sources & enabling/disabling

`config/sources.yaml` controls which sources are tried and their endpoints.
`NEPSE_ENABLED_SOURCES` (env) controls the set the pipeline iterates.

- **ShareSansar** is the primary source and is enabled by default.
- **MeroLagani / Chukul / NEPSE-official** are disabled by default. Enable a
  source by setting `enabled: true` on it in `sources.yaml` **and** including its
  name in `NEPSE_ENABLED_SOURCES` (e.g. `export NEPSE_ENABLED_SOURCES=sharesansar,merolagani`).
- For **Chukul**, first verify the real `/v1/` paths via a HAR capture (they ship
  as low-confidence guesses). For **NEPSE-official**, either `pip install
  nepse-scraper` or use the HAR-replay client — we never reconstruct its token.

Check current wiring any time:
```bash
$PY -m nepse_trader.cli.main sources
```

## 4. HAR endpoint refresh (when a source breaks)

These sites change layout/endpoints periodically. When a source suddenly returns
0 rows or wrong data:

1. Capture a fresh HAR per `har/HAR_CAPTURE_PLAN.md` (DevTools → Network → Save
   all as HAR with content) into `har/captures/`.
2. Discover endpoints:
   ```bash
   $PY -m nepse_trader.cli.main har analyze har/captures/sharesansar.har
   $PY -m nepse_trader.cli.main har to-config har/captures/sharesansar.har --source sharesansar
   ```
3. Paste the snippet into `config/sources.yaml`, adjust, and re-run `ingest`.
4. Before keeping any HAR in the repo, **redact** it:
   ```bash
   $PY -m nepse_trader.cli.main har redact har/captures/sharesansar.har
   ```
   (`har/captures/*.har` is git-ignored regardless.)

## 5. Paper trading

State is rebuilt by **replaying recorded trades** from SQLite, so keep `--cash`
consistent across calls (default Rs 100,000).

```bash
$PY -m nepse_trader.cli.main paper buy  NABIL --price 1000 --qty 100 --date 2026-06-09 --cash 200000
$PY -m nepse_trader.cli.main paper sell NABIL --price 1200 --qty 100 --date 2026-07-15 --cash 200000
$PY -m nepse_trader.cli.main paper status --cash 200000
```
Buys are rejected if cash is insufficient (fees included); sells are rejected if
you don't hold the shares. CGT is computed FIFO on the realized gain using the
holding period of the oldest lot.

## 6. Troubleshooting

| Symptom | Likely cause | Action |
|---------|--------------|--------|
| `ingest` returns 0 bars | weekend/holiday, or source layout changed | confirm the date is a trading day; if a weekday, re-capture HAR (§4) |
| `403`/`429` in logs | source is rate-limiting | the client backs off automatically; increase `NEPSE_MIN_REQUEST_INTERVAL`, run less often. **Do not** try to evade it |
| `No signals for X` | not enough reconciled history | backfill more trading days (§1) |
| reconcile shows many low-confidence rows | only one source enabled, or sources disagree | enable a second source, or inspect `data/raw/` cached responses |
| SSL error vs nepalstock | NEPSE ships an incomplete cert chain | use the `nepse-scraper` lib (handles `verify_ssl=False`) rather than direct calls |
| NEPSE-official returns nothing | `nepse-scraper` not installed | `pip install nepse-scraper`, or use HAR replay |

Useful env vars (prefix `NEPSE_`): `DB_PATH`, `RAW_CACHE_DIR`, `REQUEST_TIMEOUT`,
`MIN_REQUEST_INTERVAL`, `MAX_RETRIES`, `USER_AGENT`, `ENABLED_SOURCES`,
`PRICE_AGREEMENT_TOLERANCE`.

## 7. Data audit trail

Every raw HTTP response is cached under `data/raw/<YYYYMMDD>_<hash>.txt` (best
effort) and every ingest run is logged to the `ingest_log` table. When two
sources disagree on a price, you can trace the discrepancy back to exactly what
each returned. The reconciled consensus and its `confidence` live in the
`reconciled_prices` table.
```sql
SELECT symbol, close, confidence, sources_agreeing, disputed_fields
FROM reconciled_prices WHERE business_date = '2026-06-09' AND confidence < 1.0;
```

## 8. Health checks

### 8.1 The `health` command

`health` runs ten checks over the local installation. It is read-only, makes no
network call, and contacts no LLM provider — safe to run at any time, including
from cron.

```bash
$PY -m nepse_trader.cli.main health              # ten checks, human-readable
$PY -m nepse_trader.cli.main health --problems   # warnings and failures only
$PY -m nepse_trader.cli.main health --json       # machine-readable
$PY -m nepse_trader.cli.main health --record     # store in health_snapshots
$PY -m nepse_trader.cli.main health --history 10 # last 10 recorded verdicts
```

Checks run in a fixed order and each answers one question:

| Check | Question | `warn` when | `fail` when |
|-------|----------|-------------|-------------|
| `schema` | Are all migrations applied and nothing unknown? | unknown version applied | a registered migration is missing |
| `database` | Does the DB open and hold price rows? | zero price rows | file missing or unreadable |
| `freshness` | How stale is the newest reconciled close? | > 3 trading days behind | no reconciled rows at all |
| `ingest` | Recent per-source error rate | some sources failing | every recent attempt failed |
| `config` | Does YAML parse; is a source enabled? | no source enabled | YAML invalid against schema |
| `rag` | Corpus size, per-kind coverage, FTS5 availability | thin corpus / missing kinds | FTS5 search unavailable |
| `ai` | Could AI mode actually answer? | budget nearly spent | configured but no usable leg |
| `meroshare` | Toggle, credential completeness, last sync | mirror stale | enabled with incomplete credentials |
| `journal` | Open and scored-but-unreviewed backlog | backlog growing | — |
| `paper` | The replay-derived paper account | replay inconsistency | — |

The overall verdict is worst-wins across the ten. Two invariants are test-locked
and worth knowing before you interpret a report:

- **`off` ranks *below* `ok`** in `_SEVERITY` (`off:0, ok:1, warn:2, fail:3`).
  A feature you never enabled reports `off` and can never drag the overall
  verdict down. An `ok` report with several `off` rows is healthy.
- **A check that raises fails only itself.** `_guarded` converts an exception
  into a `fail` row for that check; the other nine still run and still report.

`health` exits non-zero when any check failed, which makes it a usable cron
gate. `--problems` prints nothing on a healthy system, so cron only mails you
when something is actually wrong:

```cron
# Health gate 20 minutes before the daily run
55 11 * * 0-4  cd /path/to/nepse-trader && .venv/bin/python -m nepse_trader.cli.main health --problems --record >> data/health.log 2>&1
```

Recording is opt-in on every surface (CLI `--record`, API `?record=true`, the
web Health page). Nothing is written to `health_snapshots` otherwise. Once a few
snapshots exist, `--history` surfaces slow rot — a corpus quietly shrinking, a
source failing a little more each week — that a single point-in-time report
cannot show.

Credentials never reach the report. Two tests plant a known secret and assert it
appears in neither an individual check's raw numbers nor `repr(report)`.

### 8.2 API surface

`/api/health` is a bare liveness probe — deliberately cheap, safe for an uptime
monitor to poll. The ten-check report lives at `/api/health/report`, and
`/api/health/history` returns recorded snapshots.

### 8.3 Verifying the installation itself

```bash
.venv/bin/python -m pytest -q          # 1284 tests, all offline
.venv/bin/ruff check .                 # lint
$PY -m nepse_trader.cli.main sources   # confirm config loads
```

Never pass `-p no:logging` to pytest — it disables the `caplog` fixture and
`tests/test_meroshare.py` errors at setup. That is a pytest invocation problem,
not a code defect.

## 9. Advisor operations

The safe scheduled path is deterministic and offline:

```bash
$PY -m nepse_trader.cli.main run-daily --advisor --advisor-offline --report data/$(date +%F).md
$PY -m nepse_trader.cli.main journal history --status open
$PY -m nepse_trader.cli.main journal calibration
```

Use `--advisor-mode ai` only when prose is useful; add `--advisor-online` only
when live RAG/provider access is intended. A missing provider or spent budget
must produce a visible degradation banner, not change the deterministic card.
Review and retire calls only after the outcome and lesson are recorded.

## 10. MeroShare and auction safety

MeroShare sync is strictly read-only. Set `NEPSE_MEROSHARE_ENABLED=true` and
credentials in env/`.env` or an optional OS keyring, then use `meroshare sync`.
For a credential-free path, use `meroshare import --file holdings.csv`. Toggle
the integration with `meroshare toggle on|off`. Credentials are never logged or
stored, failed syncs do not clear the last good holdings, and web/API/MCP output
only exposes a masked demat suffix.

Auction advice reports a fee-aware recommended bid and walk-away price. It is a
calculation for manual decision-making; there is no bid-placement code.

## 11. MCP setup

Copy `.mcp.json.example` to `.mcp.json`, replace the checkout path if needed,
and point the client at the project `.venv/bin/python`. The server reads the
local SQLite database without source clients, keeps all diagnostics on stderr,
and exposes bounded read-only tools (`backtest`, `screen`, `portfolio`,
`meroshare_holdings`, `rashifal`, `doses`, plus market/history/search tools).
