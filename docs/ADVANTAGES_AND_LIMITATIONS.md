# Application advantages and current limits

NEPSE Trader combines market data, financial checks and a remembered personal
holding plan. It is a research and manual-trade decision aid. We have not
benchmarked it against other products or established guaranteed returns.

| What it does well | Why that helps |
|---|---|
| Cross-source price reconciliation | Exposes disagreement and keeps the actual published session date. |
| Technical **and** fundamental checks | New buys require recent positive EPS/book value; current valuation affects confidence rather than being decoration. |
| Visible reasons and evidence scores | You can inspect price averages, momentum, volume, earnings, valuation and historical outcomes. |
| Original purchase memory | Entry reasons, confidence, horizon and fixed risk levels survive refreshes, top-ups and removal of old cached advice runs. |
| Stable, explicit holding decisions | Monthly weakness needs three completed sessions; stops and targets remain separate immediate risk conditions. |
| Dated changes and archived trades | Shows what changed and why, including completed sales and previous exit plans. |
| Nepal cost and settlement modelling | Uses modeled fees/CGT, shared cash sizing and T+2 eligibility instead of ignoring costs. |
| Lower-risk investment watchlist | Requires financial data, liquidity coverage, at least a year of history, restrained drawdowns/volatility and positive historical net price growth. |
| Offline operation and private configuration | Your data and credentials remain local; public source code contains no account database. |
| Manual execution | Recording a purchase/sale cannot accidentally place an order or write to MeroShare. |

Current limitations:

- Confidence describes evidence strength, **not a calibrated probability**.
  Historical comparisons and past returns do not guarantee future outcomes.
- Financial assessment uses public EPS/book value and valuation. It does not
  independently verify official statements, cash flow, debt, ROE, bank NPLs,
  capital adequacy or management quality. Snapshot date is not proof of the
  reporting period. Company ratios are not a mutual-fund NAV analysis.
- Fundamentals currently come from one provider. Prices can be delayed or
  missing, selectors can break, and reconciliation does not prove correctness.
- A lower-risk stock can still lose capital. It does not have the same risk
  profile as a bank deposit. A declared dividend percentage is not a confirmed
  cash yield; historical price returns exclude unconfirmed cash dividends.
- Stops/targets are plans, not guaranteed fills. Gaps, circuits, thin liquidity
  and settlement can prevent an exit at the displayed price.
- The manual book uses one aggregate holding plan per symbol. Top-ups preserve
  the original plan; independent strategies and exact tax/settlement per lot
  are not fully represented. Verify estimates against your broker statement.
- Orders remain manual. There is no sanctioned retail broker execution API in
  this application, and recording a trade does not verify the broker executed it.
- SQLite/local hosting serve one user. Shared public hosting needs authentication,
  separate user storage and operational controls; a public repository shares
  code, not a shared account dashboard.

## DOLTI example

A monthly DOLTI purchase gets its own saved 22-session plan. Dropping out of a
new-buy shortlist does not change that holding plan. One weak completed session
shows **Hold, 1/3 confirmations**. Three consecutive weak completed sessions can
produce a dated trend exit. A saved stop breach or target hit can produce an
earlier exit, and the UI shows when settlement allows it. An expired horizon
requests a review rather than ordering a sale.

DOLTI being a monthly trading idea does not establish suitability as a lower-risk
long-term investment. The investment screen applies a different set of financial
and historical-loss checks. Original reasons are copied from the linked dated
recommendation; manual or later-linked purchases explicitly retain unknown
original reasons instead of inventing them.
