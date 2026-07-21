---
name: nepse-backtest-protocol
description: |
  Disciplined backtesting & strategy-selection protocol for NEPSE so results are
  trustworthy, not overfit. Use when the user wants to choose/validate a trading
  strategy, compare strategies, "which strategy is best", avoid curve-fitting, run
  out-of-sample / walk-forward checks, or interpret a backtest's Sharpe / drawdown.
  Triggers: "backtest", "which strategy", "overfit", "walk forward",
  "out of sample", "validate strategy", "is this edge real".
allowed-tools: Bash(*/.venv/bin/python*), Bash(.venv/bin/*), Read
---

# NEPSE backtest protocol — project skill

The bot already has an event-driven backtester with **Nepal costs/CGT applied**
(`backtest`, `screen`). This skill is the *methodology* that keeps its output
honest. A high in-sample Sharpe is not an edge until it survives this protocol.

## Why discipline matters on NEPSE specifically
- **Thin, illiquid tape:** many scrips have gaps/halts and low float. A strategy
  can look great by trading days that wouldn't actually fill. Prefer symbols with
  consistent turnover; treat single-symbol wins skeptically.
- **Costs dominate small edges:** commission slabs + DP Rs25 + CGT are charged on
  every round trip. Always backtest with costs ON (the engine does this) — a
  "profitable" strategy gross can be a loser net.
- **Short history per symbol** after reconciliation — guard `min_bars` so stats
  aren't computed on a handful of points.

## The protocol (run in order)
1. **Universe sanity** — list reconciled symbols and bar counts; drop anything
   below `min_bars` (default 60). Don't rank on stubs.
2. **Panel screen, ranked** — backtest every strategy × symbol with costs:
   ```bash
   cd /home/kali_37/nepse-trader && PY=.venv/bin/python
   $PY -m nepse_trader.cli.main screen --rank-by sharpe --min-bars 60
   ```
3. **Per-symbol best, then suspicion check** — `--best-only` gives the winner per
   symbol. For each winner ask: how many trades? A Sharpe from **<~20 trades** is
   noise, not edge. Few-trade winners are rejected regardless of Sharpe.
   ```bash
   $PY -m nepse_trader.cli.main screen --rank-by sharpe --best-only --min-bars 60
   ```
4. **Out-of-sample split (the real test)** — never trust one in-sample number.
   The current `backtest` CLI runs the symbol's **full** reconciled history (no
   date-window flag yet), so do the split deliberately: ingest/reconcile only an
   *early* window, screen on it, then reconcile the *later* window and re-check the
   winner. The edge must persist (Sharpe stays positive, drawdown comparable). A
   strategy that only works in one regime is overfit.
   ```bash
   $PY -m nepse_trader.cli.main backtest NABIL --strategy macd   # full history
   ```
   > Gap worth closing: add `--from/--to` to `backtest` so OOS is a one-liner.
   > Until then, split via the date range you ingest.
5. **Cross-check with quant stats** — a strategy whose equity curve has worse
   drawdown/vol than buy-and-hold is not worth the turnover:
   ```bash
   $PY -m nepse_trader.cli.main stats NABIL,ADBL,HDL
   ```
6. **Decide & record** — only promote a strategy that (a) ranks well **net of
   costs**, (b) has enough trades, (c) **survives out-of-sample**, (d) beats
   buy-and-hold on risk-adjusted return. Write the chosen `symbol→strategy` map
   into the daily run; everything else is research, not signal.

## Red flags that mean "do not deploy"
- Best result comes from **one symbol** or **one lucky year**.
- **< ~20 trades** behind the Sharpe.
- Edge **vanishes net of costs** (compare gross vs net).
- Equity curve is **drawdown-heavier** than simply holding the index.
- Parameter that only works at one exact value (no plateau) → curve-fit.

## Hard rules
- **Costs always on.** Never quote a gross backtest as if it were tradeable.
- **Out-of-sample or it didn't happen.** In-sample Sharpe alone never promotes a
  strategy.
- **Paper only** — this selects what the daily report *signals*; it never places
  a live order.
- State sample size and the OOS result alongside any recommendation — no naked
  Sharpe numbers.
