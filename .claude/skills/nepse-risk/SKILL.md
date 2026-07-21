---
name: nepse-risk
description: |
  Size positions and manage risk for NEPSE (Nepal Stock Exchange) trades using
  Nepal-specific market mechanics. Use when the user asks: "how many shares
  should I buy", position sizing, stop-loss / risk-per-trade, portfolio heat /
  exposure, circuit-limit-aware entries, or whether a paper trade fits their risk
  budget. Triggers: "position size", "how much to buy", "risk per trade",
  "stop loss", "exposure", "circuit", "lot size", "NEPSE risk".
allowed-tools: Bash(*/.venv/bin/python*), Bash(.venv/bin/*), Read
---

# NEPSE risk & position sizing — project skill

Transferable risk methodology (fixed-fractional sizing, portfolio heat, R-multiples)
adapted to **Nepal market mechanics**. This drives the bot's real cost engine —
do NOT hand-compute fees; ask the engine so commission slabs, SEBON, DP and CGT
are exact.

## Nepal mechanics you MUST respect
- **Daily circuit limit:** an individual scrip can move at most **±10%** from its
  prior close in a day (≈±2% intraday batching at the open). A stop or target set
  beyond today's circuit band cannot fill today — size and place accordingly.
- **Lot / odd-lot:** normal market trades in lots (commonly **10 units**); smaller
  quantities are odd-lot and trade in a separate session. Round share counts to a
  sensible lot unless the user is doing odd-lot.
- **Settlement:** **T+2**. Cash from a sell is not deployable until settlement;
  CGT is withheld at source. Don't assume same-day rebuy of sale proceeds.
- **Costs are real and slab-based:** broker commission tiers (≤50k→0.36% …
  >10m→0.24%, Rs10 floor), SEBON 0.015%, DP **Rs25 per scrip per settlement**,
  CGT **7.5%** (≤365 days) / **5%** (>365 days) / **10%** (institutional). The DP
  fee makes very small trades inefficient — flag tickets where fees > ~1% of value.

## Sizing protocol (fixed-fractional, R-based)
1. Pick **risk budget per trade** R = `risk_pct × equity` (default 1%; never > 2%).
2. Get a **stop distance** from the strategy/ATR: `stop_dist = entry − stop`.
   Reject stops wider than today's −10% circuit floor (can't fill).
3. **Raw qty** = `R / stop_dist`, then round **down** to a lot.
4. Verify **round-trip cost** via the cost engine; if cost erodes > ~20% of R,
   the edge is too thin — widen the trade or skip.
5. Check **portfolio heat**: sum of open-position R must stay under a cap
   (default 6% of equity). Refuse the trade if it breaches the cap.

### Ask the engine for exact costs (don't approximate)
```bash
cd /home/kali_37/nepse-trader && PY=.venv/bin/python
$PY -c "
from nepse_trader.analysis.costs import CostEngine
from nepse_trader.models import OrderSide
e = CostEngine()
entry, stop, equity, risk_pct = 500.0, 470.0, 1_000_000.0, 0.01
R = equity * risk_pct
raw = R / (entry - stop)
qty = int(raw // 10 * 10)                         # round down to a 10-unit lot
buy = e.compute(OrderSide.BUY, entry, qty)        # commission+SEBON+DP on the buy leg
print(f'R=Rs{R:,.0f}  raw={raw:.0f}  qty(lot)={qty}  buy_fees=Rs{buy.total_fees:,.0f}')
print(f'fees as pct of risk budget: {buy.total_fees / R * 100:.1f}%')
"
```
`CostEngine.compute(side, price, quantity, *, buy_cost_basis=, holding_days=,
investor=)` returns a `CostBreakdown` (`.total_fees`, `.net_amount`, `.cgt`, …) and
already encodes every slab. The point: **the engine is the source of truth for
money**, this skill is the discipline around it. Read `nepse_trader/analysis/costs.py`
if you need the full signature.

## Fit-check an existing paper portfolio
```bash
$PY -m nepse_trader.cli.main paper status      # current positions / cash / realized PnL
```
Use the open positions to compute current heat before approving a new ticket.

## Hard rules
- **Paper only.** Output a recommended size and the risk math; never place a live
  order.
- Costs/CGT come from the **cost engine**, not from memory.
- If a stop or target lies outside today's **±10% circuit band**, say so — the fill
  is impossible today.
- Be honest about thin edges: when fees dominate R, recommend skipping.
