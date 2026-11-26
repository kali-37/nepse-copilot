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
| Explanation | Technical indicators, financial checks and saved entry reasons | Broader verified filings and evidence-backed news and event analysis |
| Financial depth | Dated provider snapshots, matched issuer excerpts and NRB loan quality and capital ratios | Consistent statements across sectors, including cash flow, leverage and return on equity |
| Funds | Correctly separated from company earnings rules; NAV review requested | Verified NAV, distributions, expenses and fund trading/redemption terms |
| Prediction quality | Versioned prospective journal and simulated outcome measurements | Sustained out-of-sample performance, live execution validation and calibration |
| AI | Optional grounded synthesis and an offline, time-ordered model evaluation with explicit activation | A candidate that clears held-out and prospective validation |
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

## Financial evidence

The reviewed mid-July 2026 NRB releases cover the core capital adequacy ratio,
total capital adequacy ratio and non-performing loan ratio for 48 listed
lenders. The three reports are provisional. Evidence carries the issuer's
matched row, reporting date, retrieval and verification timestamps, and
document SHA-256. Sources accessed 2026-11-26.
[Commercial banks](https://www.nrb.org.np/contents/uploads/2026/09/KFI-ASAR-END-2083-Provisional.pdf)
[Development banks](https://www.nrb.org.np/contents/uploads/2026/09/KFI_2083_Asar-B.pdf)
[Finance companies](https://www.nrb.org.np/contents/uploads/2026/09/KFI_2083_Asar_C.pdf)

Reporting-period and document checks also apply to issuer excerpts. Same-period
regulator and issuer figures retain their source scope. A material risk finding
can lower the evidence grade or block a buy, and absent checks remain visible.
Only records already retrieved and verified at the evaluation time can affect
advice. The import retains the precise source versions reviewed for this release.

An issuer verification manifest contains the symbol, official HTTPS
`source_url`, `period_start`, `period_end`, `period_basis` and the source
`period_quote`. Under `metrics`, each key such as `eps` contains a numeric
`value`, `unit`, full source row `quote`, `unit_quote` and `context_quote`
that binds the row and units to that period. Run
`nepse-trader fundamentals verify-statement manifest.json` to fetch, match
and archive the source. The verifier requires a retrievable filing on a
registered issuer host with unambiguous dates, rows and units. The initial
live import covers regulator ratios. Complete verified sector checklists and
issuer filings beyond this coverage remain sparse.

The reviewed Everest filing and Nepal Telecom interim filing remain
unverified in the dashboard. Everest's download path was denied by the
client's robots parser. The Nepal Telecom PDF exceeded the verifier's
download limit and its extracted comparative cells needed review.
Sources inspected 2026-11-26.
[Everest quarterly filing](https://everestbankltd.com/wp-content/uploads/2026/11/1st-Quarterly-Financial-Report-of-Fiscal-year-2083-84.pdf)
[Everest robots policy](https://everestbankltd.com/robots.txt)
[Nepal Telecom filing](https://cms.ntc.net.np/storage/media/F48rpftftCt2ncE6Ip62u35iiC8EP9uqBG09UclI.pdf)

## Validation of trained models

The predictor uses raw price and volume features from a trailing window.
Labels simulate the subsequent session's open, a fixed entry zone, T+2,
conservative stops and targets, and the configured cost and tax model. The
scaler and logistic classifier use the training window. Platt calibration uses
the following window. The final chronological test excludes labels that span
partition boundaries. Missing sessions, unfilled entries and known corporate
actions affect coverage and appear in the report.

The activation gate checks sample size, Brier score and log loss against
training and calibration base rates, discrimination, calibration error and
date-block uncertainty. It also tests fee-adjusted results against chart-rule
and same-stock holding benchmarks where available. Evaluation evidence and
input fingerprints are saved per model. When a model passes and is activated,
its estimate remains a separate field on qualifying buy ideas. The historical
test covers the simulated trade, while live fills and sustained prospective
calibration require separate observations.

### Local evaluation on 26 November 2026

The latest evaluations used classified stocks and reconciled prices available
through 2026-11-26. Lower Brier scores indicate more accurate probabilities.

| Horizon | Held-out trades and dates | Model Brier | Training base-rate Brier | Calibration base-rate Brier | AUC | Activation |
|---|---:|---:|---:|---:|---:|---|
| 3 sessions | 1,232 trades across 44 dates | 0.22129 | 0.21984 | 0.21984 | 0.506 | Blocked |
| 22 sessions | 119 trades across 16 dates | 0.31122 | 0.33643 | 0.30088 | 0.440 | Blocked |

The 3-session model fell short of both frozen base-rate baselines. The
22-session model had insufficient sample and date coverage, fell short of the
calibration base rate, and averaged a 3.68% net loss across 63 selected
simulated trades. Both evaluations are available in the local Research panel.

NEPSE session dates use Monday through Friday starting on 2026-04-06. The
government weekend change and stored exchange sessions agree around the
cutover. Published forecasts retain their original entry and deadline. Any
forecast whose dates conflict with the trading calendar is excluded from
return statistics.
Government decision accessed 2026-11-26.
[Cabinet minute 57/082, item 19](https://www.opmcm.gov.np/content/532/cabinet-chaitra/)

Outcome measurements use the data available at scoring time. Later source corrections or newly discovered corporate actions may require manual audit; published outcome rows are not automatically revised.
