# Technology and evaluation standards

NEPSE Trader is an explainable research assistant. Its trading edge has not
been established, and no head-to-head benchmark against commercial AI tools
has been run. A model name, feature count or passing test suite does not prove
that recommendations will make money.

## Comparison with an AI prediction service

Use these criteria when comparing a specific competing service. Verify its
claims from its own published methodology and dated recommendation record;
this table does not claim that every competing tool has these features.

| Criterion | Current application | Evidence needed for a stronger claim |
|---|---|---|
| Market coverage | NEPSE-focused public sources; source disagreement is visible | Complete licensed/current data with measured freshness and errors |
| Explanation | Technical indicators, financial checks and saved entry reasons | Verified financial statements and evidence-backed news/event analysis |
| Financial depth | Dated EPS/book value and quote-based valuation | Cash flow, debt, ROE, bank capital/NPLs and reporting-period verification |
| Funds | Correctly separated from company earnings rules; NAV review requested | Verified NAV, distributions, expenses and fund trading/redemption terms |
| Prediction quality | Versioned prospective journal and simulated outcome measurements | Sustained out-of-sample performance, live execution validation and calibration |
| AI | Optional grounded synthesis, local retrieval, budgets and caching | A trained predictor evaluated against simple baselines without time leakage |
| Personal decisions | Remembered horizon, fixed exits, settlement and recorded trades | Exact per-lot accounting and broker-confirmed execution |
| Hosting | Private local SQLite dashboard; source code is public | Authentication, user isolation and operational testing for shared hosting |

## Delivered efficiency improvements

A cProfile probe on the same local dataset of 385 symbols produced:

| Measurement | Before | After |
|---|---:|---:|
| Full profiled analysis | 66.284 seconds | 24.610 seconds |
| SELECT statements | 1,541 | 811 |
| Chart-state cumulative time | 32.755 seconds | 2.402 seconds |
| Buy/investment results | Baseline | Identical |

This is approximately 2.7× faster full analysis and 47% fewer database reads.
Rolling validity/volume calculations replace repeated windows; one metadata
query replaces repeated history reads, and one cost engine is shared across
the analysis. These are local measurements under a profiler, not a latency
guarantee or a prediction-accuracy improvement. Raw profiles and account-bearing
board snapshots remain in ignored `artifacts/reliability/`.

## How the recommendation track record works

The first fresh published daily/monthly idea is frozen per symbol, horizon and
source market session in the existing prediction journal under `decision_v1`.
Repeated refreshes do not rewrite its reasons, score, zone, stop or target.
Stale or retrospectively supplied boards cannot manufacture a forward record.
Each publication freezes its next future opening session: today's open when
published before opening, otherwise the next trading day. The horizon begins
at that entry, including holidays correctly.

The 100-share simulation enters only inside the saved zone. It waits for T+2
before exits, checks stops first on ambiguous candles, uses conservative gap
prices and models Nepal fees/tax. Returns use the actual opening price rather
than assuming the recommendation quote was executable. Missing required OHLC
sessions do not produce a win. Known corporate actions before exit exclude a
call; an event after a resolved exit cannot rewrite its outcome.

Unfilled entries and corporate-action exclusions are shown separately and
excluded from profitability statistics. Missing/unresolved calls remain pending;
bounded scoring rotates through retries so an old missing-data backlog cannot
starve new calls. Generic advisor-journal scoring is kept separate from this
completed-session, unadjusted-tape evaluator.

The report groups results by original evidence score and shows sample counts,
net profitability, average net return and 95% Wilson intervals. Those intervals
do not account for cross-stock dependence. The holding baseline uses the same
stock and exit date; it is not an index or shared-cash portfolio benchmark.
Actual spread, queue position, slippage, market impact, order rejection and
unrecorded corporate actions are not verified. Simulated results remain research
evidence, not confirmed broker performance.

## What remains before claiming a validated AI edge

1. Verify official financial periods and add sector/fund-specific fundamentals.
2. Collect a sustained prospective record across rising, falling and sideways markets.
3. Use chronological training/validation/test splits with purging for overlapping horizons.
4. Compare a candidate model with current rules, cash and appropriate market/portfolio baselines after realistic costs.
5. Measure calibration, error by sector/horizon, downside risk and confidence intervals on held-out calls.
6. Monitor source drift and model drift; version each policy before its new predictions.

These are remaining evaluation requirements. The application does not currently
claim that a trained model, commercial-tool superiority or calibrated win
probabilities have been delivered.

Outcome measurements use the data available at scoring time. Later source corrections or newly discovered corporate actions may require manual audit; published outcome rows are not automatically revised.
