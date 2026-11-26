# Official financial evidence and model validation — 26 November 2026

- Research shows official financial evidence by symbol, with reporting dates,
  source documents, SHA-256 and missing checks. The reviewed NRB reports cover
  capital ratios and non-performing loans for 48 listed lenders. The import
  is repeatable and preserves first availability for point-in-time decisions.
- Issuer excerpt verification and sector checks affect buy and investment
  assessment when the relevant evidence is available. Provider estimates retain
  their source and valuation basis.
- The current market calendar uses Monday through Friday from 6 April 2026.
  Existing forecasts retain their published dates and invalid dates are
  excluded from simulated return statistics.
- Both local models ran through 26 November 2026 data. The 3-session model
  failed to beat base-rate forecasts on 1,232 held-out trades across 44 dates.
  The 22-session model had 119 held-out trades across 16 dates, missed the
  calibration baseline, and averaged a 3.68% net loss on 63 selected simulations.
  Both are saved in **Research** with activation blocked.

The public-source refresh completed for 26 November and the production
dashboard showed the research and symbol evidence views in Chromium at 390 px
with no JavaScript exceptions or horizontal overflow.
Local verification passed 1,539 Python tests with one skip and 212 frontend
tests. Ruff, frontend lint and the production build passed.
[Technology and evaluation standards](TECHNOLOGY_AND_EVALUATION.md)

## Previous release: recommendation evidence and efficiency — 25 November 2026

This release improves measurement and computation without claiming a validated
investment edge or superiority over commercial AI tools.

- Fresh buy ideas are permanently logged before outcomes under `decision_v1`.
  The first publication per symbol/horizon/market session retains its evidence
  score, reasons, entry zone and fixed exits. Past/stale boards cannot create a
  retrospective successful track record.
- Publication time in Kathmandu freezes the first future opening session,
  including today's open before 11:00 and the next trading day afterward. Horizon
  deadlines start from that entry. The 100-share simulator uses actual opens
  inside saved zones, completed OHLC, T+2, conservative stops/gaps and fees.
  Missing data, unfilled entries and corporate actions are disclosed separately.
  Generic journal scoring cannot bypass this evaluator, and bounded retries
  rotate instead of starving newer calls.
- **Recommendation track record** shows outcome counts, net profitability by
  original score group and Wilson intervals. The baseline holds the same stock
  to each modeled exit date. It is not an index benchmark or actual broker fill.
- Mutual funds receive fund/NAV-specific review instead of false company-EPS
  deterioration warnings. Verified fund NAV ingestion remains unavailable.
- Same-dataset profiling fell from 66.284s/1,541 SELECTs to 24.610s/811 SELECTs.
  Buy ideas and investment candidates were identical. Rolling calculations,
  shared fee configuration and one quote-metadata read remove repeated work;
  concurrent first reconciliation uses the normal retry path.
- Market forecasts remain capped at 0.90. Misleading deposit-safety wording was
  removed. Optional AI synthesis remains grounded research, not a trained model
  whose predictive edge has been proven.

Sparse-history company/fund detail pages display unavailable statistics as
unknown instead of crashing; drawdown warnings use the loss magnitude. The
statistics panel states its observation count and labels annualization as
historical rather than a forecast.

Verification: **1483 Python tests passed, 1 skipped; 197 frontend tests passed**.
Ruff, frontend lint, TypeScript/build and npm audit pass. Local timing results
are profiler measurements, not runtime guarantees. See
[technology and evaluation standards](TECHNOLOGY_AND_EVALUATION.md) for
methodology and remaining validation requirements.

## Previous release: fundamental decisions and purchase continuity — 24 November 2026

The requested decision features are implemented. Open
http://127.0.0.1:8000/ for daily/monthly ideas, the lower-risk research watchlist
and personal hold/exit advice. Company pages show the fundamental assessment
and dated trade/advice history.

- New buys require recent positive EPS and book value. Current P/E and
  price/book reduce confidence when valuations raise concern; missing, stale
  or unsupported financial data blocks a new buy. Visible reasons explain
  the technical, liquidity and financial evidence.
- Recording a purchase copies its linked, dated recommendation into permanent
  entry memory. Original reasons, source confidence, horizon and exit levels
  survive refreshes, top-ups and partial sales. Unrecorded reasons remain unknown.
- A monthly holding needs three consecutive completed weak sessions for a
  trend exit; daily plans need two and long-term plans five. Saved stops and
  targets remain immediate exit conditions, with settlement eligibility shown.
  Confirmed exits persist until a recorded sale or explicit plan review. Horizon
  expiry requests review rather than forcing a sale.
- A lower-risk investment watchlist checks profitability, valuation, liquidity,
  at least a year of observed history, drawdowns, volatility and positive
  historical price growth after modeled fees. It is unsized research and makes
  no promised return or deposit-safety claim.
- Fundamentals updates invalidate cached advice. Repeated refreshes do not
  duplicate action history; confirmed dates restore review deadlines for holdings
  initially imported without purchase dates. Recently sold stocks have a
  re-entry cooldown.
- Concurrent advice rebuilds preserve the completed refresh report and use
  publication order. An older request cannot overwrite newly saved cash,
  holdings or plans. If market updates prevent advice publication after a
  mutation, the API explicitly says the change was saved and requests an
  advice retry; repeated trade IDs remain idempotent.

See [advantages and limitations](ADVANTAGES_AND_LIMITATIONS.md) for the delivered
strengths and the remaining financial-data, execution and hosting limits.

The live refresh on 24 November returned 700 source price rows, reconciled 350
symbols for the published **2026-11-24** session, repaired 272 history rows,
updated 14 financial snapshots and loaded 52,387 broker contracts. One symbol's
history was unavailable; successful data was retained. Account data and trade
records were preserved.

Verification: **1,460 Python tests passed, 1 skipped on Python 3.12; 191 frontend
tests passed**. Ruff, frontend lint, TypeScript and the production build pass;
npm audit reports zero vulnerabilities. Browser checks found no horizontal
overflow at 390px, no page exceptions, one refresh control and working company
fundamental assessments. Purchase/exit checks use isolated test databases.
GitHub CI checks clean Python 3.11/3.12 installs and the frontend.

## Earlier release: public repository and CI preparation — 20 November 2026

The Python 3.11/3.12 CI failure is fixed: Ruff and test tools are in uv's default
`dev` group, the matrix explicitly selects its Python interpreter, and JSON
Schema validation is now a declared runtime dependency. Clean environments
pass **1,429 tests with 2 optional skips on each Python version**. Node 24 passes
**186 frontend tests**, lint, build, and an npm audit with **zero vulnerabilities**.

Personal `.env` variants, databases, raw captures, account exports, screenshots,
logs, backups, cloud credentials and generated analysis maps are ignored by Git
and excluded from Docker. Previously tracked runtime/generated files are
untracked while local copies remain available. Credential values are excluded
from Settings representations/JSON; AI errors redact echoed keys. CI and
pre-commit include a staged-file privacy check. Historical blobs and runtime
logs were checked against configured credentials without printing their values;
no actual credential matches were found.

[how_to_proceed.md](../how_to_proceed.md) documents cloning, private configuration,
the local dashboard and contributing. The committed environment template has
blank credential fields, and the declared MIT license is included. GitHub
visibility and private Actions status require an authenticated GitHub API
session; SSH push access alone cannot change repository settings.

# Decision dashboard — 20 November 2026

Open http://127.0.0.1:8000/ for the simple dashboard. `/rashifal` starts with
monthly ideas; `/holdings` focuses on personal exit advice. Research, paper
trading, AI, journal and operations remain under **Research & tools**.

The dashboard now includes:

- Daily (3 trading sessions) and monthly (22 sessions) buy candidates, charts,
  entry zones, fixed risk levels, quantities, modeled Nepal fees and net gain
  at target. Both lists share a single available-cash budget. Thin, stale,
  unaffordable and weak setups do not force a recommendation.
- Differentiated confidence based on completed, non-overlapping comparable
  historical setups plus current trend, momentum, RSI, volume, source agreement
  and data quality. Historical entries are next-session fills; exits respect
  T+2 settlement. Intraday candles do not count as completed expiries. These
  numbers are evidence scores, not calibrated or guaranteed win probabilities.
- Personal sell/hold/review advice for recorded and mirrored holdings. Purchase
  records save entry-anchored stops/targets, instead of moving those levels on
  every refresh. Existing holdings can receive an exit plan without adding a
  second purchase. Unknown cost or settlement dates remain explicitly unknown.
  Corporate-action changes require confirmation of current units and levels.
- **I bought this / I sold** forms for trades already executed manually.
  Records update quantities, cost basis and available cash atomically, reject
  overselling, and use retry IDs to avoid duplicate purchases. They place no
  broker orders and write nothing to MeroShare.
- **Refresh today** downloads enabled public sources, reconciles their actual
  published dates, repairs insufficient history in bounded batches, analyses
  charts and fee-aware outcomes, refreshes shortlisted company/broker context,
  and saves advice. Progress survives page reloads while the server is running;
  individual source failures are reported without discarding successful data.
  Offline mode reads saved evidence and refuses network refresh.
- Warm light styling, compact primary navigation, dark mode, keyboard-accessible
  forms and responsive layouts. Market overview and advanced research remain
  available without crowding the main buying/selling screen.

Verification: **1,412 Python tests passed, 1 skipped; 186 frontend tests passed**.
Ruff, frontend lint and production build pass. Browser checks exercise recorded
purchase → triggered exit → sale on a separate test database. The live refresh
returned 347 ShareSansar and 347 Chukul price rows, 10 company snapshots and
40,837 broker contracts. November 20 is Friday: the displayed published session
is correctly **2026-11-19**, not a relabelled “today” quote.

Screenshots are in `artifacts/ui/`. Docker daemon verification and a PostgreSQL
backend remain outside this dashboard scope.

## Previous core delivery — 19 November 2026

The dashboard runs locally at `http://127.0.0.1:8000/`. The Analytics page is
`/analytics`; downloads, reconciliation and indexing are on `/operations`.

## Delivered

- Published history ingestion from ShareSansar and Chukul, via CLI and jobs.
  Dates come from responses, with Chukul timestamps converted to Nepal time.
  Repeating a download upserts the same sessions. Range filtering, cancellation,
  malformed rows and per-symbol failure isolation are covered by tests.
- Corporate-action adjustment is computed, stored and read by analysis. Raw
  prices remain available. Late/corrected events recompute from original prices;
  future events do not adjust a current history. Bonus/split ratios use their
  correct factors. Rights/dividends require a confirmed factor to adjust prices.
- Dated fundamentals are stored for offline display, sector classification,
  RAG and P/E, price/book, EPS and sector screening filters. Missing valuations
  are excluded when a filter is active; later snapshots do not filter past data.
- Shared-cash portfolio research with lot rounding, Nepal fees, next-session
  signals, delayed exits and optional periodic rebalancing. Equal-allocation
  research remains available and carries values across missing sessions.
- Walk-forward CLI/API/UI: validated windows, RSI parameter grid correction,
  warmed indicators, default-parameter strategies and separate validation fills.
- Broker-flow aggregation over deduplicated contracts; source fallback to the
  verified public Chukul floorsheet. Contract IDs verify business dates.
  Sector breadth uses stored classifications and labels missing data explicitly.
- Persistent source cooldowns, explicit-date incremental skipping, force
  refresh, row-count warnings, actual concurrent async source fallbacks,
  robots rules, Retry-After handling and compressed audit-cache retention.
  Long server-requested delays defer the host instead of blocking a worker.
  Existing uncompressed captures are preserved.
- JSON logs with run IDs, persisted daily-report metrics, query indexes,
  frontend CI, responsive analytics and lazy-loaded page bundles.
- Exact FIFO acquisition cost and partial-sale residuals. Display average cost
  is rounded; tax/profit accounting uses the actual paid inventory basis.

## Real data loaded

At the completion check the database contained 385,330 source price bars and
193,071 reconciled sessions across 348 stored symbols, from 2024-01-01 through
2026-11-19. There are 658 distinct trading dates and 341 symbols with at least
60 sessions. A symbol may have fewer observations because it was recently
listed or did not trade. The coverage card reports current numbers.

Chukul's old `api.chukul.com` hostname no longer resolves. Its replacement
public price, history and floorsheet URLs were observed in the deployed
frontend and verified. NepseAlpha's old history URL returns HTTP 403 and remains
disabled. The official NEPSE adapter remains opt-in. No access gate is bypassed.

The live broker download loaded 40,837 matched contracts for 2026-11-19,
producing 11,276 symbol/broker pairs. The page shows the 100 strongest net buying
and 100 strongest net selling pairs when the result is large. Offline indexing
built 5,913 searchable documents and 735,558 stored signal rows. Five company
fundamental snapshots and an offline advisor run are also saved; additional
company snapshots can be downloaded from Operations.

Only confirmed, recorded corporate actions adjust the history. Ingested prices
alone do not establish complete corporate-action coverage.

## Run it

```bash
.venv/bin/python -m uvicorn nepse_trader.web.api:app --host 127.0.0.1 --port 8000
.venv/bin/python -m nepse_trader.cli.main backfill all --since 2024-01-01
.venv/bin/python -m nepse_trader.cli.main backfill all --since 2024-01-01 --source chukul
.venv/bin/python -m nepse_trader.cli.main adjust-prices
.venv/bin/python -m nepse_trader.cli.main optimize NABIL --strategy sma_cross
.venv/bin/python -m nepse_trader.cli.main portfolio-backtest NABIL,EBL,NTC --cash 1000000
.venv/bin/python -m nepse_trader.cli.main screen --max-pe 20 --max-pbv 3
.venv/bin/python -m nepse_trader.cli.main rag index
```

Use **Download fundamentals** and **Download broker trades** in Operations to
populate their local tables. Downloads explicitly use the network; research
uses the stored database. `NEPSE_ONLINE=false` blocks every ingestion request.

## Deployment and separate work

`Dockerfile`, `.dockerignore` and `compose.yaml` are present. Compose configuration
validates. Image build could not be checked on this host because Docker's daemon
is stopped and starting it requires an interactive sudo password.

Once Docker is running:

```bash
docker compose up --build -d
# A scheduled daily job can use the same image and persistent volumes:
docker compose run --rm dashboard python -m nepse_trader.cli.main run-daily
```

SQLite remains the active backend. PostgreSQL, ML/pairs/Monte Carlo research,
Python coverage/type-check gates, PyPI release automation and historical fee
schedule versioning remain separate extensions. The original sprint plan and
engineering proposal documents are historical, not current completion checklists.

## Verification

- Python: 1,386 passed, 1 skipped.
- Frontend: 175 passed across 19 files.
- Ruff, frontend lint, TypeScript/production build and Compose configuration pass.
- Live dashboard and research endpoints responded successfully. Desktop and
  phone layouts were inspected. Code review verified FIFO residual/cash identities
  and the source, validation-fold and missing-quote regressions.
- Docker image build remains unverified for the host prerequisite above.
