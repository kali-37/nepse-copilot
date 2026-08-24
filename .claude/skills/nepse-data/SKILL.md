---
name: nepse-data
description: |
  Drive the local NEPSE Trader bot to collect and analyse Nepal Stock Exchange
  (NEPSE) public market data. Use when the user wants to: pull/scrape NEPSE prices
  or indices, reconcile data across Nepali sources (ShareSansar, MeroLagani,
  Chukul), generate the daily report, compute quant stats (Sharpe/Sortino/VaR),
  run or screen backtests, paper-trade with Nepal fees/CGT, or discover a source's
  endpoints from a HAR capture. Triggers: "NEPSE", "ShareSansar", "MeroLagani",
  "Nepali stocks", "daily report", "floorsheet", "share price".
allowed-tools: Bash(*/.venv/bin/python*), Bash(.venv/bin/*), Read, Edit, Write
---

# NEPSE Trader — project skill

This project IS the NEPSE bot. Drive it through its CLI; don't hand-roll scraping.

## Setup (once)
```bash
cd /home/kali_37/nepse-trader
PY=.venv/bin/python
$PY -m pytest -q            # sanity: all tests offline & green
```

## The once-a-day run (the main thing)
```bash
PY=.venv/bin/python
$PY -m nepse_trader.cli.main run-daily --report data/$(date +%F).md
```
This ingests from **all** sources, reconciles into a confidence-scored consensus,
and writes an 8-section markdown report: market overview/breadth, top movers,
reconciliation quality, multi-strategy signals, quant stats, backtest leaderboard,
best strategy per symbol, and paper-portfolio status. Schedule it via cron in the
evening NPT (see `docs/RUNBOOK.md`).

## Common tasks → commands
| Goal | Command |
|------|---------|
| Pull a day from every site, merge | `... ingest --date YYYY-MM-DD --all-sources` |
| Reconcile a day | `... reconcile --date YYYY-MM-DD` |
| Quant stats | `... stats NABIL,ADBL,HDL` |
| One strategy backtest | `... backtest NABIL --strategy macd` |
| Rank all strategies × symbols | `... screen --rank-by sharpe --best-only` |
| Signals for a symbol | `... signal NABIL --strategy sma_cross` |
| Paper trade | `... paper buy NABIL --price 500 --qty 100 --date YYYY-MM-DD` |
| Portfolio status | `... paper status` |
| List/inspect sources | `... sources` |

(Prefix each with `.venv/bin/python -m nepse_trader.cli.main`.)

## Fetch / parse engines
- Default fetch engine is **httpx**. To use the Scrapling (curl_cffi) engine:
  `export NEPSE_FETCH_ENGINE=scrapling`. It runs in **plain mode** — honest
  User-Agent, no stealth headers, **no Cloudflare/WAF/anti-bot solving**.
- HTML parsing auto-uses Scrapling's adaptive `Selector` when installed
  (`NEPSE_PARSE_ENGINE=auto|scrapling|selectolax`), falling back to selectolax.
  Both produce identical rows; Scrapling adds resilience to layout drift.

## When a source breaks (endpoint discovery)
Use the global `scrapling` skill to capture/inspect, but only for endpoint
DISCOVERY on these public sites — **not** to bypass protections:
1. Capture a HAR per `har/HAR_CAPTURE_PLAN.md` into `har/captures/`.
2. `... har analyze har/captures/<site>.har` → ranked endpoints.
3. `... har to-config har/captures/<site>.har --source <name>` → paste into
   `config/sources.yaml`, then re-run `ingest`.
4. `... har redact har/captures/<site>.har` before keeping any HAR.

## Hard rules (do not cross)
- **Public data only.** No login-gated scraping, no NEPSE token reconstruction.
- **Polite.** Keep the throttle; on `403/429` the bot backs off — never bypass,
  never enable stealth/Cloudflare-solving for these sources (they don't need it).
- **No live orders.** Signals and trades are paper only.
- Commercial/redistributed use of NEPSE data needs a license from NEPSE Ltd.

## Companion skills
- **`nepse-risk`** — position sizing & risk math on Nepal mechanics (±10% circuit,
  lots, T+2, slab fees/CGT via the cost engine). Use before any paper buy.
- **`nepse-backtest-protocol`** — keeps strategy selection honest (costs-on,
  trade-count floor, out-of-sample). Use before promoting a strategy into the run.

## Where things live
- Data: `data/nepse.db` (SQLite), raw audit cache `data/raw/`.
- Config: `config/sources.yaml`, `config/cost_model.yaml`.
- Logs: `logs/<component>/<HH-MM-SS>-<YYYY-MM-DD>-<about>.log`. Every CLI run writes
  one file under `logs/cli/`; the daily pipeline summary lands under `logs/pipeline/`;
  each test run writes `logs/tests/<...>-pytest.log`. Tree is tracked (`.gitkeep`),
  the `.log` files are git-ignored. Override the root with `NEPSE_LOG_DIR`.
- Docs: `README.md`, `how_to_use.md`, `how_it_works.md`, `developers_guide.md`,
  `docs/RUNBOOK.md`.
