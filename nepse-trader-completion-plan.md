# Plan: NEPSE Trader — Full Completion

> Historical sprint plan. See [current completion status](docs/COMPLETION_STATUS.md)
> for implemented features, verification and remaining extensions.

**Generated**: 2026-07-21
**Estimated Complexity**: High
**Total effort**: ~6–8 weeks (single developer)

## Overview

Complete the NEPSE Trader project by implementing all roadmap features
(`what_to_add_next.md`) and engineering-quality upgrades (`make_evenBetter.md`).
Organised into 5 sprints that build on each other.

Key ordering decisions (based on gotcha analysis):
- **Decimal money** moved to Sprint 0 — prevents building new features on float
- **DB migrations** moved to Sprint 0 — Sprint 1 adds tables/columns
- **Corporate actions** broken into granular sub-tasks
- Web dashboard pushed to last sprint to avoid scope creep

## Prerequisites

- Python ≥ 3.11, uv, the existing `.venv`
- `config/sources.yaml` for source configuration
- GitHub account (for CI — optional but recommended)

---

## Sprint 0: Engineering Foundation

**Goal**: Protect the codebase so all subsequent changes are tested and linted
automatically. Fix money precision before adding new features. Ship migration
infrastructure before schema changes.

**Demo/Validation**:
- Push triggers GitHub Actions: `ruff check`, `pytest`, `pyright` all green
- `pre-commit run --all-files` passes
- `hypothesis` finds no invariant violations
- Decimal money in costs/portfolio: worked example exact to paisa
- Migration adds a column without data loss

### Task 0.1: CI pipeline

- **Location**: `.github/workflows/ci.yml` (new)
- **Description**: GitHub Actions workflow on push/PR:
  1. Setup Python 3.11+ with `uv`
  2. `uv pip install --python .venv/bin/python -e ".[dev]"`
  3. `ruff check .`
  4. `pytest -q`
- **Dependencies**: None
- **Acceptance Criteria**:
  - Workflow file present; runs on push + PR to master; caches uv env
- **Validation**: Push a branch, verify check passes

### Task 0.2: Property-based tests (Hypothesis)

- **Location**: `tests/test_properties.py` (new), `pyproject.toml` (add `hypothesis` to `[project.optional-dependencies] dev`)
- **Description**: Hypothesis strategies + invariants:
  - Cost engine: commission is monotonic in amount
  - Reconciliation: agreed close within min/max of source closes
  - Indicators: EMA ≤ max(input), SMA correct at edges
  - Portfolio: WAC avg_cost ≤ max(buy price after fees)
- **Dependencies**: None
- **Acceptance Criteria**: ≥5 property tests, 200+ falsification examples
- **Validation**: `pytest tests/test_properties.py -q`

### Task 0.3: Pre-commit hooks

- **Location**: `.pre-commit-config.yaml` (new), `pyproject.toml` (add `pre-commit` to dev deps)
- **Description**: `pre-commit` config: `ruff check`, `ruff format --check`,
  trailing-whitespace, end-of-file-fixer. HAR secret-scan guard (refuse `*.har`).
- **Dependencies**: None
- **Acceptance Criteria**: `pre-commit run --all-files` passes
- **Validation**: `pre-commit run --all-files`

### Task 0.4: DB migrations framework

- **Location**: `nepse_trader/storage/migrations.py` (new), `nepse_trader/storage/db.py` (wire in at init)
- **Description**: Schema-version table + ordered migration scripts. Each migration
  is a function applying DDL. Auto-runs pending migrations on `Storage.__init__`.
- **Dependencies**: None
- **Acceptance Criteria**:
  - Schema version tracked in DB
  - Migration adds a column without data loss
  - Runs at most once per version; idempotent
- **Validation**: `pytest tests/test_migrations.py -q`

### Task 0.5: Golden-file fixtures & parser tests

- **Location**: `tests/fixtures/*.html|json` (new), `tests/test_sharesansar.py`, `tests/test_merolagani.py`
- **Description**: Commit redacted real responses as fixtures. Golden tests assert
  parsers produce expected model fields. Detect layout drift on CI.
- **Dependencies**: None
- **Acceptance Criteria**: ≥2 fixture files per source; golden test fails on drift
- **Validation**: `pytest tests/test_sharesansar.py tests/test_merolagani.py -q`

### Task 0.6: Decimal for money

- **Location**: `nepse_trader/analysis/costs.py`, `nepse_trader/trading/portfolio.py`, `nepse_trader/models.py` (add `DecimalMoney` type), `nepse_trader/analysis/backtest.py`, `nepse_trader/analysis/screen.py`, `nepse_trader/reporting.py`
- **Description**: Replace `float` with `Decimal` for ALL monetary fields:
  - Add `DecimalMoney` (Decimal rounded to 2dp) as a Pydantic type
  - Update `CostBreakdown`, `PaperTrade`, `Position`, `PaperPortfolio`, `Backtester`
  - Keep indicators/stats as `float` (they're statistical, not ledger)
  - Update `reporting._fmt_num` to handle `Decimal`
  - Update `storage/db.py` to store/read `Decimal` as TEXT (portable across DBs)
  - Verify the worked-example test holds to the paisa
- **Dependencies**: Task 0.4 (migrations — may need schema change for TEXT storage)
- **Acceptance Criteria**:
  - `CostBreakdown.total_fees` is `Decimal`
  - Worked-example test exact to paisa
  - All money fields use `Decimal` internally; `float` only in indicators/stats
- **Validation**: `pytest tests/test_costs.py -q` (paisa-exact); `pytest -q` full suite

---

## Sprint 1: Tier 1 Features

**Goal**: Highest-value features — holiday calendar, corporate actions, alerts,
additional source verification.

**Demo/Validation**:
- `run-daily` on Saturday → "market closed"
- Price series adjusts for a known bonus event
- `--alert telegram` sends report
- `ingest --all-sources` pulls from Chukul

### Task 1.1: Holiday / trading calendar

- **Location**: `nepse_trader/calendar.py` (new), `nepse_trader/pipeline.py` (wire skip), `nepse_trader/analysis/quant.py` (wire `periods_per_year`)
- **Description**: Bikram-Sambat-aware calendar. Detects weekends (Sat), gazetted
  holidays (YAML config), NEPSE-announced closures.
  - `is_trading_day(date) → bool`
  - Pipeline skips non-trading days (log + exit clean)
  - `periods_per_year` from config for annualization
- **Dependencies**: None
- **Acceptance Criteria**:
  - `is_trading_day` for Saturday → False
  - `run-daily` on holiday → "market closed" exit
  - Tests for weekends, known holidays, year boundaries
- **Validation**: `pytest tests/test_calendar.py -q`; manual Saturday run

### Task 1.2.1: Corporate actions — model + storage

- **Location**: `nepse_trader/models.py` (add `CorporateAction`), `nepse_trader/storage/db.py` (add `corporate_actions` table via migration)
- **Description**: Add `CorporateAction` model (`symbol, ex_date, action_type, factor, source`).
  Add `corporate_actions` table with PK `(symbol, ex_date, action_type)`.
  Add migration version for the table.
- **Dependencies**: Task 0.4 (migrations), Task 0.6 (Decimal for factor)
- **Acceptance Criteria**: Model defined; table created via migration
- **Validation**: `pytest tests/test_storage.py -q` (test `upsert_corporate_action`)

### Task 1.2.2: Corporate actions — scraping

- **Location**: `nepse_trader/ingest/corporate_actions.py` (new), `nepse_trader/ingest/sharesansar.php`... actually `nepse_trader/ingest/sharesansar.py` (add `fetch_corporate_actions`)
- **Description**: Scrape corporate action announcements from ShareSansar's
  announcement/bonus pages. Parse bonus %, rights ratio, split factor. Fallback:
  CLI command to manually enter events.
- **Dependencies**: Task 1.2.1
- **Acceptance Criteria**: Parser produces `CorporateAction` list from ShareSansar HTML
- **Validation**: `pytest tests/test_corporate_actions.py -q`

### Task 1.2.3: Corporate actions — adjustment pass

- **Location**: `nepse_trader/ingest/reconcile.py` (add adjustment step), `nepse_trader/models.py` (add `adjusted_close` to `ReconciledPrice`), migration for `reconciled_prices.adjusted_close`
- **Description**: After reconciliation, back-adjust historical closes by the
  corporate-action factor. Add `adjusted_close` column to `reconciled_prices`.
  Indicators/strategies get an option to use adjusted vs raw.
- **Dependencies**: Task 1.2.1, Task 0.4
- **Acceptance Criteria**:
  - Bonus 1:1 → factor 0.5 → pre-event close halved
  - `adjusted_close` populated in reconciled output
  - Existing backtests unaffected (default to raw close)
- **Validation**: `pytest` with synthetic bonus event

### Task 1.2.4: Corporate actions — CLI

- **Location**: `nepse_trader/cli/main.py` (add `corporate-actions` subcommand)
- **Description**: `corporate-actions list` and `corporate-actions add` for manual
  event entry when scraping fails.
- **Dependencies**: Task 1.2.1
- **Acceptance Criteria**: CLI lists stored events; `add` creates a new event
- **Validation**: Manual `nepse-trader corporate-actions add NABIL --type bonus --factor 0.5`

### Task 1.3: Alerting integrations

- **Location**: `nepse_trader/reporting.py` (extend `Alerter`), `nepse_trader/config/alerts.yaml` (new), `nepse_trader/config.py` (parse alert config), `nepse_trader/cli/main.py` (`--alert` flag)
- **Description**: Add pluggable backends to `Alerter`:
  - Telegram: POST to `https://api.telegram.org/bot<TOKEN>/sendMessage`
  - Discord: POST to webhook URL
  - SMTP: via `smtplib` (stdlib, no new dep)
  Gate on `config/alerts.yaml`. `run-daily --alert telegram` sends summary.
- **Dependencies**: None
- **Acceptance Criteria**:
  - `Alerter.send_telegram(token, chat_id, text)` works (mocked)
  - `Alerter.send_discord(webhook_url, text)` works (mocked)
  - `run-daily --alert telegram` posts
  - No new runtime deps
- **Validation**: `pytest tests/test_reporting.py -q`; mocked HTTP tests

### Task 1.4: Verify & enable Chukul + NepseAlpha sources

- **Location**: `har/captures/` (new HARs), `config/sources.yaml` (flip `enabled: true`), `nepse_trader/ingest/nepsealpha.py` (new client)
- **Description**:
  1. Capture HAR from Chukul and NepseAlpha
  2. `har analyze` + `har to-config` to confirm endpoints
  3. Update `config/sources.yaml` with verified paths
  4. Create `NepseAlphaClient` (TradingView UDF datafeed parser)
  5. Register in `pipeline._CLIENT_FACTORIES`
  6. Tests with HAR-captured fixture data
- **Dependencies**: None
- **Acceptance Criteria**:
  - Chukul fetches live data (`ingest --all-sources`)
  - NepseAlpha client exists and parses UDF format
  - HAR files committed (redacted) + config updated
- **Validation**: `pytest tests/test_chukul.py tests/test_nepsealpha.py -q`

---

## Sprint 2: Analytical Upside

**Goal**: Stronger analysis — risk management, more strategies, multi-symbol backtest,
walk-forward optimization, fundamentals.

**Demo/Validation**:
- Backtest with ATR-based stop shows improved Sharpe
- New strategies (Supertrend, Ichimoku) produce signals on real data
- Multi-symbol backtest allocates across 3 names
- Walk-forward sweep produces out-of-sample metrics
- `screen --fundamental pe_lt 20` filters by P/E

### Task 2.1: Risk-managed position sizing & stops

- **Location**: `nepse_trader/analysis/risk.py` (new), `nepse_trader/analysis/strategies.py` (risk params), `nepse_trader/analysis/backtest.py` (wire stops/sizing)
- **Description**: ATR-based sizing layer:
  - `PositionSizer` — fixed-fractional (R = risk_pct × equity → qty)
  - Stop-loss / take-profit in backtester
  - Max exposure cap (% of equity)
  - Lot rounding to 10-share lots
  - Circuit-limit awareness: reject stops beyond ±10%
- **Dependencies**: Task 0.6 (Decimal money in backtester)
- **Acceptance Criteria**: Backtester respects stops; size rounds to lots
- **Validation**: `pytest tests/test_risk.py -q`

### Task 2.2: New strategies

- **Location**: `nepse_trader/analysis/strategies.py` (add classes)
- **Description**: 4 new strategies:
  1. **Supertrend**: ATR-based trend-following
  2. **Ichimoku**: Tenkan/Kijun cross + Chikou confirmation
  3. **Donchian breakout**: 20-day channel breakout
  4. **Mean-reversion z-score**: 2σ z-score reversion
  Register each in `STRATEGIES`.
- **Dependencies**: Task 2.1 (reuses ATR)
- **Acceptance Criteria**: Each emits BUY/SELL on state change; `signal NABIL --strategy supertrend` works; tests with synthetic price paths
- **Validation**: `pytest tests/test_strategies.py -q`; manual `screen` includes new names

### Task 2.3: Multi-symbol portfolio backtest

- **Location**: `nepse_trader/analysis/backtest.py` (add `PortfolioBacktester`), `nepse_trader/analysis/screen.py` (extend)
- **Description**: `PortfolioBacktester` — shares one cash account across symbols,
  allocates per entry, per-name position limits, portfolio-level metrics.
- **Dependencies**: Task 2.1, Task 0.6
- **Acceptance Criteria**: `PortfolioBacktester.run(strategies, {symbol: bars})` returns portfolio metrics; costs use `CostEngine`
- **Validation**: `pytest tests/test_backtest.py -q`; 3-symbol portfolio produces sensible equity curve

### Task 2.4: Walk-forward optimization

- **Location**: `nepse_trader/analysis/optimize.py` (new), `nepse_trader/cli/main.py` (`optimize` command)
- **Description**: Rolling window sweep over strategy params. Grid search, IS vs OOS
  metrics. Overfit detection (IS >> OOS → warn). Pickle best params.
- **Dependencies**: Task 2.3
- **Acceptance Criteria**: `optimize NABIL --strategy sma_cross --fast 10..50 --step 5` runs; reports IS/OOS Sharpe
- **Validation**: `pytest tests/test_optimize.py -q`

### Task 2.5: Fundamentals ingestion

- **Location**: `nepse_trader/ingest/merolagani.py` (fundamentals parsing), `nepse_trader/models.py` (add `Fundamental`), `nepse_trader/storage/db.py` (add `fundamentals` table via migration), `nepse_trader/analysis/screen.py` (`--fundamental` filter)
- **Description**: Parse EPS, P/E, book value, dividends from MeroLagani
  `CompanyDetail`. Store in `fundamentals` table. `screen --fundamental PE<20`.
- **Dependencies**: Task 0.4 (migrations)
- **Acceptance Criteria**: `screen --fundamental pe_lt 20` filters leaderboard
- **Validation**: `pytest tests/test_fundamentals.py -q`

---

## Sprint 3: Robustness & Usability

**Goal**: Make ingestion robust (schema-driven parsing, Retry-After) and the tool
usable day-to-day (export, incremental ingest, floorsheet analytics).

**Demo/Validation**:
- ShareSansar parser uses column spec from config, not hardcoded indices
- 429 responses honour `Retry-After` header
- `export --table reconciled_prices --format csv` produces clean CSV
- Re-running today skips already-fetched sources
- Floorsheet shows net broker buy/sell for NABIL

### Task 3.1: Schema-driven HTML parsing

- **Location**: `nepse_trader/ingest/sharesansar.py`, `nepse_trader/ingest/merolagani.py`, `config/sources.yaml` (add column maps)
- **Description**: Move column-index maps to declarative spec (header-name →
  model field). Generalise MeroLagani's header-based approach to ShareSansar.
  Layout change becomes a config edit, not code change.
- **Dependencies**: None
- **Acceptance Criteria**: Column maps in YAML; parsers read from spec; existing tests pass
- **Validation**: `pytest tests/test_sharesansar.py tests/test_merolagani.py -q`

### Task 3.2: Respect Retry-After and robots.txt

- **Location**: `nepse_trader/ingest/base.py`
- **Description**: Parse `Retry-After` in 429/503 responses. Fetch/check `robots.txt`
  on startup, cache it, reject disallowed paths.
- **Dependencies**: None
- **Acceptance Criteria**: `Retry-After` overrides backoff; disallowed path → `FetchError`
- **Validation**: `pytest tests/test_base.py -q`

### Task 3.3: Data export command

- **Location**: `nepse_trader/cli/main.py` (add `export` command), `nepse_trader/storage/db.py` (add table reader)
- **Description**: `export --table <name> --format csv|parquet`. CSV via stdlib.
  Parquet via optional `pyarrow` dep. Tables: `price_bars`, `reconciled_prices`,
  `signals`, `paper_trades`.
- **Dependencies**: None
- **Acceptance Criteria**: CSV works without pyarrow; Parquet works with it
- **Validation**: Manual `export --table reconciled_prices --format csv`

### Task 3.4: Incremental / smart ingestion

- **Location**: `nepse_trader/pipeline.py` (skip logic), `nepse_trader/storage/db.py` (audit check)
- **Description**: Skip dates already fully ingested per source. Row-count anomaly
  detection vs trailing average. `--force` override.
- **Dependencies**: None
- **Acceptance Criteria**: Second ingest of same date = no-op; anomaly triggers warning
- **Validation**: `pytest tests/test_pipeline.py -q`

### Task 3.5: Floorsheet analytics

- **Location**: `nepse_trader/analysis/floorsheet.py` (new), `nepse_trader/reporting.py` (add section), `nepse_trader/cli/main.py`
- **Description**: Aggregate floorsheet → net broker buy/sell pressure per symbol.
  Add to daily report as "Broker flow" section. CLI `floorsheet` subcommand.
- **Dependencies**: None
- **Acceptance Criteria**: `floorsheet NABIL --date YYYY-MM-DD` shows net flow
- **Validation**: `pytest tests/test_floorsheet.py -q`

---

## Sprint 4: Performance & Scale

**Goal**: Speed up ingestion, add circuit breaker for resilience, add sector
analytics for deeper market insight.

**Demo/Validation**:
- `ingest --all-sources` runs in half the wall-clock time
- Source failing repeatedly is skipped fast
- Sector rotation report highlights strongest sectors
- Coverage ≥90%, pyright green

### Task 4.1: Async, concurrent ingestion

- **Location**: `nepse_trader/ingest/base.py` (add `AsyncBaseClient`), `nepse_trader/pipeline.py` (async ingest), `nepse_trader/cli/main.py` (wire async path)
- **Description**: `httpx.AsyncClient` variant with same throttle/retry/cache.
  `asyncio.gather` for concurrent per-source pulls in pipeline. Sync path kept.
- **Dependencies**: None
- **Acceptance Criteria**: `AsyncBaseClient` with same semantics; concurrent pulls
- **Validation**: `pytest`; wall-clock comparison

### Task 4.2: Per-source circuit breaker

- **Location**: `nepse_trader/ingest/base.py` (add `CircuitBreaker`), `nepse_trader/ingest/base.py` (wire into `SourceClient`)
- **Description**: Track recent failures per source. N of last M failed → skip
  for K runs. Auto-reset after cooldown.
- **Dependencies**: Task 4.1
- **Acceptance Criteria**: Source with 3 consecutive failures skipped on run 4
- **Validation**: `pytest tests/test_circuit_breaker.py -q`

### Task 4.3: Sector & index analytics

- **Location**: `nepse_trader/analysis/sectors.py` (new), `nepse_trader/reporting.py` (add sector section), `nepse_trader/config/sources.yaml` (sector mapping)
- **Description**: Sector breadth (advancers/decliners per sector), sector rotation
  heatmap, index trend, market-cap-weighted internals. Daily report section.
- **Dependencies**: None
- **Acceptance Criteria**: Sector table in daily report; `sectors` CLI command
- **Validation**: `pytest tests/test_sectors.py -q`

### Task 4.4: Coverage measurement & type checking

- **Location**: `pyproject.toml` (add `[tool.coverage]` and `[tool.pyright]`), `.github/workflows/ci.yml` (add coverage step)
- **Description**: `pytest --cov=nepse_trader --cov-fail-under=90`. `pyright` with
  pragmatic config. Fix `Any` gaps in storage and pipeline.
- **Dependencies**: None
- **Acceptance Criteria**: 90%+ coverage; pyright green
- **Validation**: Run both commands

### Task 4.5: Structured JSON logging

- **Location**: `nepse_trader/logging_setup.py` (JSON formatter), `nepse_trader/pipeline.py` (run ID)
- **Description**: JSON log output with per-run UUID. Run metrics persisted to
  `run_metrics` table (via migration). Configurable via `NEPSE_LOG_FORMAT`.
- **Dependencies**: Task 0.4 (migrations)
- **Acceptance Criteria**: `NEPSE_LOG_FORMAT=json` → JSON lines; unique run ID per run
- **Validation**: `NEPSE_LOG_FORMAT=json python -m nepse_trader.cli.main run-daily`

---

## Sprint 5: Production Polish

**Goal**: Deployable, observable, scalable — Docker, web dashboard, Postgres support.

**Demo/Validation**:
- `docker build -t nepse-trader . && docker run ...` works
- Web dashboard serves equity curve and leaderboard
- Postgres storage passes full test suite

### Task 5.1: Docker image

- **Location**: `Dockerfile` (new), `.dockerignore` (new)
- **Description**: Slim Python 3.12-slim image. Bake in venv with uv.
  `run-daily` as entrypoint. `data/` as mountable volume.
- **Dependencies**: None
- **Acceptance Criteria**: Image builds; `docker run` executes `run-daily`
- **Validation**: Build + `docker run --rm -v $(pwd)/data:/app/data nepse-trader run-daily`

### Task 5.2: Web dashboard

- **Location**: `web/` (new), `web/app.py` (FastAPI), `web/templates/` (Jinja2), `pyproject.toml` (add `web` extras: `fastapi`, `uvicorn`, `jinja2`)
- **Description**: Read-only FastAPI dashboard:
  - Daily report viewer (latest + historical)
  - Per-symbol equity curve from backtest/portfolio
  - Leaderboard table
  - Sector heatmap
  - Charts via Chart.js (CDN)
  - **No write paths**
- **Dependencies**: Sprint 4.3 (sector data)
- **Acceptance Criteria**: `uvicorn web.app:app` serves at localhost:8000; report + equity curve + leaderboard render
- **Validation**: Manual browser check

### Task 5.3: Pluggable Postgres storage

- **Location**: `nepse_trader/storage/__init__.py` (extract `Storage` protocol), `nepse_trader/storage/postgres.py` (new), `nepse_trader/storage/db.py` (keep as `SqliteStorage`), `nepse_trader/pipeline.py` (use protocol)
- **Description**: Extract `Storage` ABC/protocol from current SQLite. Implement
  `PostgresStorage` behind same methods. Configurable via `NEPSE_DB_URL`.
  Dependencies: `asyncpg` or `psycopg2` (add to `[project.optional-dependencies] postgres`).
- **Dependencies**: Task 0.4 (migrations must work on Postgres too)
- **Acceptance Criteria**: `Storage` protocol extracted; Postgres passes the same test suite
- **Validation**: `NEPSE_DB_URL=postgresql://... pytest tests/test_storage.py -q`

---

## Testing Strategy

| Sprint | Focus | Key new test files |
|--------|-------|-------------------|
| Sprint 0 | CI, property tests, Decimal, migrations, golden fixtures | `test_properties.py`, `test_migrations.py` |
| Sprint 1 | Calendar, corporate actions, alerts, new sources | `test_calendar.py`, `test_corporate_actions.py`, `test_alerting.py`, `test_nepsealpha.py` |
| Sprint 2 | Risk, new strategies, portfolio backtest, optimize, fundamentals | `test_risk.py`, `test_strategies.py`, `test_backtest.py`, `test_optimize.py`, `test_fundamentals.py` |
| Sprint 3 | Schema parsing, export, floorsheet | `test_export.py`, `test_floorsheet.py` |
| Sprint 4 | Async, circuit breaker, sectors, coverage, logging | `test_circuit_breaker.py`, `test_sectors.py` |
| Sprint 5 | Dashboard, Postgres | `test_storage.py` (Postgres), manual browser |

**Golden rule**: Every module ships with `test_<module>.py`. All tests offline
(mocked HTTP). `pytest -q` and `ruff check .` always green.

---

## Potential Risks & Gotchas (addressed)

1. ~~**Decimal migration breaks cost tests**~~ → **Handled**: Task 0.6 pins the
   worked-example test before migration. Run is comparison-only after.

2. ~~**Migrations in Sprint 5 too late for Sprint 1 schema changes**~~ → **Handled**:
   Migrations moved to Sprint 0 (Task 0.4). Corporate actions and fundamentals
   both use migration versions.

3. ~~**Corporate actions monolithic**~~ → **Handled**: Split into 4 tasks (model +
   storage, scraping, adjustment pass, CLI). Each is independently committable.

4. ~~**Web dashboard scope creep**~~ → **Handled**: Strictly read-only, no write
   paths. Pushed to Sprint 5 so core work isn't blocked by UI.

5. **Corporate action data source reliability**: NEPSE doesn't have a clean
   machine-readable CA feed. *Mitigation*: Manual CLI fallback.

6. **Chukul/NepseAlpha endpoint drift**: Sites may change API paths.
   *Mitigation*: HAR toolkit designed for re-discovery.

7. **Async + circuit breaker interaction**: Concurrent requests complicate
   per-source failure tracking. *Mitigation*: Track by source name, not by client
   instance. Test this explicitly.

8. **Postgres SQL dialect differences**: SQLite uses different SQL than Postgres.
   *Mitigation*: Keep SQL simple; use `Storage` protocol to abstract differences.
   Use SQLAlchemy only if absolutely needed.

---

## Rollback Plan

Each task = one atomic commit. If anything breaks:
1. **Per task**: `git revert <commit>` and redo.
2. **Per sprint**: Revert the last task commit that broke integration.
3. **Full revert**: `git reset --hard <sprint-N-start-tag>`.
4. **Data safety**: No migration runs without backing up `data/nepse.db` first.
   All schema changes are additive (no column removal).
