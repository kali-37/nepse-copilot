# How To Use — NEPSE Trader

This is the plain-language guide. It assumes nothing about programming. Every
command is written out in full so you can copy it, paste it, and press Enter.

If you want to know *how* it works inside, read
[`how_it_works.md`](how_it_works.md). If you want to change the code, read
[`developers_guide.md`](developers_guide.md). If something is broken and you
want the fastest fix, read [`docs/RUNBOOK.md`](docs/RUNBOOK.md) or jump to
[§24 When something looks wrong](#24-when-something-looks-wrong).

> **What this is allowed to do:** it reads *public* NEPSE market data, politely,
> for your own personal research. It never places a real order. It never tries
> to get around a website's protections. Commercial use of NEPSE data needs a
> licence from Nepal Stock Exchange Ltd. Nothing this software prints is
> financial advice.

---

## 1. What this thing is

It is a program that runs on your own computer and does five things:

1. **Fetches** the day's share prices from public Nepali market websites.
2. **Cross-checks** them against each other, so you know when two sites
   disagree about a price.
3. **Analyses** them — trend signals, risk statistics, historical simulations.
4. **Prices everything honestly** — every number includes broker commission,
   SEBON fee, DP charge, and capital gains tax at real Nepal rates.
5. **Writes it down** — a daily report, a prediction journal you can grade
   later, and a web dashboard you can click through.

Everything lives in one file on your disk (`data/nepse.db`). Nothing is uploaded
anywhere. There is no account, no cloud, no subscription.

Two words you will see constantly:

- **Reconciled** — a price that two or more sources agreed on. This is the only
  kind of price the analysis will touch.
- **Deterministic** — the same inputs always give the same answer. Every price,
  quantity, fee, tax and stop-loss in this tool is deterministic. The optional
  AI only writes explanatory sentences; it never changes a number.

---

## 2. Install once

You need Python 3.11 or newer. The easy path uses
[`uv`](https://github.com/astral-sh/uv):

```bash
cd nepse-trader
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e ".[dev]"
```

Every command below starts with `.venv/bin/python -m nepse_trader.cli.main`,
which is long. Make a shortcut once per terminal session:

```bash
alias nt=".venv/bin/python -m nepse_trader.cli.main"
```

Now `nt health` means the same as the long version. **This guide uses `nt`
everywhere.** To make the shortcut permanent, add that `alias` line to the end
of your `~/.zshrc` (or `~/.bashrc`).

Check it worked:

```bash
nt --help
```

You should see a list of about two dozen commands. If you do, you are done
installing.

---

## 3. First five minutes

Run these four commands in order. Total time: about two minutes.

```bash
nt health                 # is everything wired up correctly?
nt ingest                 # fetch today's prices
nt reconcile              # cross-check them
nt dashboard              # what do I have now?
```

If `nt ingest` reports zero rows, check the date. NEPSE trades **Sunday through
Thursday**. On a Friday, Saturday, or a public holiday there is genuinely
nothing to fetch, and zero rows is the correct answer, not a bug.

One day of data is not enough to analyse anything. Indicators need history. To
get about six weeks of it, run this once and let it work (it is polite and slow
on purpose — roughly 1.5 seconds between requests):

```bash
for d in $(seq 0 60); do
  D=$(date -d "-$d day" +%F)
  nt ingest --date "$D" >/dev/null 2>&1
  nt reconcile --date "$D" >/dev/null 2>&1
done
```

Then you have a real database, and everything in the rest of this guide will
produce output.

---

## 4. Reading the health check

`nt health` is the command to run first whenever anything seems off. It asks ten
questions about your own installation. It is read-only, it makes **no network
calls**, and it never contacts an AI provider — it is safe to run at any time.

```bash
nt health
```

### The four verdicts

| Verdict | Colour | What it means | Do you need to act? |
|---------|--------|---------------|---------------------|
| `ok` | green | Working as intended. | No. |
| `warn` | yellow | Working, but degraded — stale data, a backlog, a thin corpus. | Soon. |
| `fail` | red | Broken. This part cannot do its job. | Yes, now. |
| `off` | grey | You deliberately did not enable this feature. | **No.** |

**`off` is not a problem.** If you never turned on MeroShare or AI mode, those
checks report `off`, and that is the correct, healthy answer. `off` deliberately
ranks *below* `ok` in severity, so an unused feature can never drag your overall
verdict down. A report that says `ok` overall with three `off` rows is a
perfectly healthy installation.

The overall verdict is **worst-wins**: one `fail` anywhere makes the whole report
`fail`. And if one check itself crashes, only that row turns `fail` — the other
nine still run and still report.

### The ten checks

They always appear in this order:

| # | Check | The question it answers |
|---|-------|-------------------------|
| 1 | `schema` | Are all 14 database upgrades applied, and nothing unknown? |
| 2 | `database` | Does the database file exist, open, and contain price rows? |
| 3 | `freshness` | How many trading days behind is my newest reconciled price? |
| 4 | `ingest` | What share of recent fetches failed, per source? |
| 5 | `config` | Does my YAML config parse, and is at least one source enabled? |
| 6 | `rag` | How big is the searchable document corpus, and does search work? |
| 7 | `ai` | If I asked AI mode a question, could it actually answer? |
| 8 | `meroshare` | Is the mirror on, are credentials complete, when did it last sync? |
| 9 | `journal` | How many predictions are open, or scored but never reviewed? |
| 10 | `paper` | What does the replayed paper account look like? |

On `freshness`: more than **three trading days** behind is a `warn`. That is the
threshold, and it counts trading days, not calendar days — a long Dashain break
will not make your data look stale.

### The four flags

```bash
nt health --problems      # only the warnings and failures — nothing else
nt health --json          # machine-readable, for scripts
nt health --record        # save this verdict into the database
nt health --history 10    # show the last 10 saved verdicts
```

`--problems` is the one to use in a cron job: on a healthy system it prints
nothing at all, so you only get mail when something is actually wrong.

Recording is **opt-in everywhere** — nothing is written to your database unless
you pass `--record`. Once you have recorded a few, `--history` shows you the
trend, which is how you notice slow rot (a corpus quietly shrinking, a source
failing more often each week).

`nt health` **exits non-zero** if any check failed. That makes it usable as a
gate in a script:

```bash
nt health --problems && nt run-daily --report data/$(date +%F).md
```

---

## 5. Getting market data

```bash
nt sources                       # which websites am I set up to read?
nt ingest                        # fetch today
nt ingest --date 2026-06-09      # fetch one specific past trading day
nt reconcile --date 2026-06-09   # cross-check that day
```

**`ingest`** visits each enabled source, reads the day's price table, and stores
every row it finds. It prints a summary: how many rows per source, and any
errors. If one site is down or has changed its layout, it is logged and skipped —
one broken source never stops the others.

**`reconcile`** is the step that makes the data trustworthy. It groups the day's
rows by symbol, finds the largest group of sources that agree on the price
(within 0.5% by default), and writes one consensus price. It also records:

- **confidence** — the share of sources that agreed. `1.0` means everyone
  agreed. Less than `1.0` means someone disagreed.
- **disputed fields** — exactly which numbers they disagreed about.

A yellow row in the reconcile output means low confidence. Treat that symbol's
price as soft that day, and go look at `data/raw/` to see what each site
actually returned.

**Always reconcile after you ingest.** Every analysis command reads reconciled
prices only. Ingesting without reconciling means the analysis sees nothing new.

---

## 6. Looking at the market

```bash
nt dashboard
```

One screen: how many symbols and bars you have stored, the date range covered,
your reconciliation quality, and your paper portfolio's current state. This is
the "where am I" command.

---

## 7. Signals and strategies

A **signal** is one strategy's opinion about one symbol on one day: `BUY`,
`SELL`, or `HOLD`, plus a strength from 0 to 1.

```bash
nt signal NABIL
nt signal NABIL --strategy macd
nt signal NABIL --strategy rsi --period 14
nt signal NABIL --strategy sma_cross --fast 20 --slow 50
```

`BUY` and `SELL` only appear when something *changes* — a line crosses, a band
is broken. Most days, on most symbols, you will correctly see `HOLD`.

There are eight strategies. In plain language:

| Strategy | What it watches | It says BUY when… |
|----------|-----------------|-------------------|
| `sma_cross` | Two moving averages, one fast one slow | the fast average crosses above the slow one |
| `rsi` | How overbought or oversold the price is | the price was oversold and is turning back up |
| `macd` | The gap between two averages, and its own average | that gap crosses above its signal line |
| `bollinger` | A band drawn around the average price | the price falls out of the bottom of the band |
| `supertrend` | A trailing stop line that follows volatility | the price flips to the upside of that line |
| `ichimoku` | A Japanese multi-line trend cloud | the price and the lines all line up bullish |
| `donchian` | The highest high and lowest low over N days | the price breaks above the recent high |
| `mean_reversion` | How far the price has strayed from normal | the price has strayed unusually far below |

Tuning flags are `--fast`, `--slow`, `--period`, `--signal`. Each strategy only
uses the ones that apply to it; the rest are ignored.

**No strategy is better than another in the abstract.** Which one fits a given
symbol is an empirical question, and §8 and §9 are how you answer it with
numbers instead of opinions.

---

## 8. Backtesting

A backtest replays history and asks: if I had actually traded this strategy,
what would I have ended up with — after every fee and tax?

```bash
nt backtest NABIL --strategy sma_cross --fast 20 --slow 50 --cash 100000
nt backtest NABIL --strategy macd --fraction 0.5
```

It is long-only, it fills at the same bar's close, and it applies the full
Nepal cost stack on every single fill. The numbers it reports:

| Metric | Meaning |
|--------|---------|
| `total_return_pct` | What you made or lost, **after all fees and CGT** |
| `cagr_pct` | The same, expressed as a per-year rate |
| `max_drawdown_pct` | The worst peak-to-trough fall along the way |
| `sharpe` | Return per unit of wobble — higher is steadier |
| `trades` | How many round trips it took |
| `win_rate_pct` | Share of trades that made money |
| `exposure_pct` | Share of days you were actually holding something |

Read `max_drawdown_pct` before you read `total_return_pct`. A strategy that
made 40% but fell 60% along the way is one you would have abandoned in the
middle, which means you would never have collected the 40%.

To compare everything at once instead of one at a time:

```bash
nt screen --rank-by sharpe --top 30
nt screen --best-only                              # best strategy per symbol
nt screen --strategies sma_cross,macd --rank-by total_return_pct
nt screen --min-bars 120                           # only well-covered symbols
```

`--rank-by` accepts `sharpe`, `total_return_pct`, `cagr_pct`,
`max_drawdown_pct`, or `win_rate_pct`. This is how you let after-cost numbers
choose a strategy for you, rather than choosing one because it sounded clever.

---

## 9. Quality statistics

```bash
nt stats NABIL,ADBL,HDL
nt stats                       # top 25 stored symbols
nt stats --periods 252         # annualisation factor
```

Per symbol: annualised return and volatility, **Sharpe** and **Sortino** ratios,
maximum drawdown, **95% Value at Risk**, skewness and kurtosis.

The one to actually look at is **95% VaR**: on the worst 1 day in 20, this is
roughly how much of that position's value moved against you. If that number is
larger than you are willing to lose in a day, the position is too big — before
any question of whether the strategy is any good.

---

## 10. Paper trading

Paper trading records pretend trades with real arithmetic. Nothing reaches a
broker; there is no order-placing code in this project at all.

```bash
nt paper buy  NABIL --price 1000 --qty 100 --date 2026-06-09 --cash 200000
nt paper sell NABIL --price 1200 --qty 100 --date 2026-07-15 --cash 200000
nt paper status --cash 200000
```

Rules it enforces on you:

- A buy is refused if you do not have the cash — **fees included**.
- A sell is refused if you do not hold the shares.
- Capital gains tax is computed FIFO, using the *oldest lot's* holding period,
  because that is how Nepal actually assesses it.

**Keep `--cash` the same on every call.** Your portfolio is not stored as a
balance; it is rebuilt from scratch each time by replaying your recorded trades
against that starting cash. Change the number and you are asking about a
different portfolio.

The arithmetic, checked to the paisa:

> BUY 100 @ 1,000 → cash out **100,370**
> SELL 100 @ 1,200 → cash in **118,121.67** (CGT **1,439.33**)
> Realised profit **17,751.67**

That is not a rounded illustration. It matches the official worked example
exactly, and there is a test that fails if it ever stops matching.

---

## 11. The daily run

One command does the whole loop and writes a report:

```bash
nt run-daily --report data/$(date +%F).md
```

It ingests from every source, reconciles, and then writes eight sections:
market overview and breadth, top movers, reconciliation quality, actionable
signals across strategies, per-symbol statistics, the backtest leaderboard, the
best strategy per symbol, and your paper portfolio.

Useful variations:

```bash
nt run-daily --strategies sma_cross,macd --rank-by cagr_pct
nt run-daily --top 50                    # analyse more symbols
nt run-daily --enabled-only              # only configured sources
nt run-daily --advisor --advisor-offline # also produce the prescription (§12)
```

To have it run itself every evening, add this to your crontab (`crontab -e`).
NEPSE trades **Sunday–Thursday**, which is `0-4` in cron. ShareSansar's
end-of-day data settles around 17:45 NPT, so 18:00 NPT — 12:15 UTC — is a good
time:

```cron
15 12 * * 0-4  cd /path/to/nepse-trader && .venv/bin/python -m nepse_trader.cli.main run-daily --report data/$(date +\%F).md >> data/cron.log 2>&1
```

A holiday just ingests zero rows and does nothing, so it is safe to leave this
scheduled all year. Pair it with `nt health --problems` if you want to be told
when something rots.

---

## 12. Advice — rashifal, advise, doses

This is the opinionated part. Given your capital, it produces concrete cards:
buy this, this many shares, at this price, with this stop, expecting this net
result after fees and tax.

```bash
nt rashifal --equity 100000 --save --report data/rashifal.md
nt doses --latest
nt advise --equity 100000 --horizon month
```

`rashifal` and `advise` are the same command under two names. `doses` shows the
four allocation slices.

Your capital is **one pool split four ways** by time horizon. Not four separate
pots — four nested slices of the same money:

| Dose | Horizon | Trading days | Share of capital |
|------|---------|--------------|------------------|
| day | today-ish | 3 | 10% |
| week | this week | 10 | 20% |
| month | this month | 22 | 30% |
| year | the long hold | 250 | 40% |

Each card belongs to exactly one horizon. The bulk of the money sits in the
slowest slice, deliberately.

### Reading the confidence number

Every card carries a confidence from 0 to 1. It is **not** a probability that
you will make money. It is built by a **weakest-link** rule: the card's
confidence is dragged down to its worst input. Thin history, disputed prices,
low agreement between sources, a stale corpus — the *worst* of these sets the
number, not the average.

So a low confidence tells you *the evidence is thin*, not *the market will fall*.
Those are different statements and only the first one is something this software
can actually know.

`1.00` is reserved for pure arithmetic — a fee calculation, a break-even. It is
never given to a market forecast. Directional cards are capped at **0.9**. The
`0.95`–`0.99` band is labelled "still money in the bank" and is only reached by
things that are nearly definitional. Every directional card is a forecast, and
forecasts are wrong sometimes.

### AI mode

```bash
nt rashifal --mode ai              # AI writes prose; no network
nt rashifal --mode ai --online     # AI may also retrieve live
```

AI mode adds *sentences*. It cannot add, remove, or change a price, a quantity,
a stop, a fee, a tax, or a confidence number. The card is computed first and the
prose is written around it afterwards. Offline is the default: no network calls
happen unless you type `--online` yourself.

The prose is also screened by a forbidden-phrase filter, so the AI cannot
promise you a guaranteed return even if it wants to.

---

## 13. Prediction journal

The point of the journal is that predictions are recorded **before** the result
is known, so you cannot quietly rewrite history in your own favour.

```bash
nt journal history --status open
nt journal score PREDICTION_ID
nt journal review PREDICTION_ID --text "why this went the way it did"
nt journal distill PREDICTION_ID --lesson "the transferable lesson"
nt journal retire PREDICTION_ID
nt journal calibration
```

The lifecycle runs one way: `open → scored → reviewed → retired`. You cannot
skip a step.

Two scoring rules that matter, because they are the ones that stop you fooling
yourself:

1. **The stop is checked before the target.** If the price hit your stop and
   only then reached your target, that is a loss. In the real world you were
   already out.
2. **Only `TARGET_HIT` counts as a hit.** "Went vaguely the right way" is not a
   hit. `UNRESOLVED` and `NO_DATA` are excluded from calibration entirely
   rather than being counted as wins.

`nt journal calibration` is then the honest scoreboard: your real hit rate, and
your expected outcomes against your realised ones. Retired predictions stay in
the history. Distilled lessons become searchable (§16), so past mistakes can
surface next time something similar comes up.

---

## 14. Auction bid ceiling

When shares are auctioned, the question is how high you can bid and still make
money after every fee and tax.

```bash
nt auction advise NABIL --units 500 --min-bid-price 900 --market-price 1000
nt auction advise NABIL --units 500 --min-bid-price 900 --market-price 1000 \
   --horizon-days 22 --confidence 0.7 --edge-buffer-pct 0.15
nt auction list
```

It gives you a fee-neutral break-even price and a **walk-away price** — the
number above which bidding stops making sense. `--edge-buffer-pct` (default
0.1) keeps your recommended bid a conservative margin below break-even.

**This is a calculator, not a bidder.** There is no code in this project that
submits an auction bid. You take the number and decide for yourself.

---

## 15. Fundamentals and corporate actions

```bash
nt fundamentals show NABIL
nt corporate-actions list
nt corporate-actions add            # record a bonus, split or dividend
```

Corporate actions matter more than they sound: a bonus share issue makes a
price series look like it crashed when nothing happened. Recording the action
is what lets the analysis tell a real fall from a cosmetic one.

---

## 16. Searching your own data

The tool builds a searchable corpus out of what it already knows, so you can
ask questions in words instead of SQL.

```bash
nt rag index                                   # build it (offline)
nt rag index --news                            # also fetch news (network)
nt rag search "why did banking stocks fall"
nt rag search "NABIL" --kinds price,signal --limit 5
nt rag search "dividend" --since 2026-06-01 --full
```

Ten kinds of document are indexed: `price`, `indicator`, `quant`, `signal`,
`reconcile`, `fundamental`, `corporate_action`, `news`, `report`, `web`. Restrict
with `--kinds`, narrow with `--symbols` and `--since`, and add `--online` to
reach the live web when your local results are thin.

Re-run `nt rag index` after a backfill, or your searches will keep describing
last month's market.

---

## 17. AI mode

AI is entirely optional. The tool is fully usable with no AI provider
configured, and that configuration reports `off`, not `fail`, in `nt health`.

```bash
nt ai models      # which providers are configured, and which actually work
nt ai budget      # today's usage against your caps, plus cache size
nt ai test        # send one tiny prompt and report what answered
```

Budget caps exist so a stuck loop cannot spend your money: by default 40 calls
and 400,000 tokens per day, and 2 deep passes per week. Responses are cached for
a week, so repeating a question is free.

To turn it on, set one of these in your `.env` file:

```bash
NEPSE_OPENROUTER_API_KEY=sk-...
# or
NEPSE_ANTHROPIC_API_KEY=sk-ant-...
# or, if you already have the Claude CLI installed and logged in:
NEPSE_CLAUDE_CLI_PATH=claude
```

When a provider is missing or the budget is spent, you get a visible
degradation banner and the deterministic numbers unchanged. It never silently
substitutes a guess.

---

## 18. MeroShare mirror

This copies your **real** holdings in, so advice can be about what you actually
own instead of a hypothetical portfolio.

```bash
nt meroshare toggle on
nt meroshare connect                          # shows the disclosure, tests login
nt meroshare sync --yes
nt meroshare holdings
nt meroshare status
nt meroshare toggle off
```

**It is strictly read-only.** There is no code here that applies for an IPO,
submits an ASBA form, places an order, or bids in an auction. Sync reads
holdings, WACC, and transaction history. That is the entire surface.

### What is done with your data

- Your password is **never** written to the database, never written to a log,
  and never returned by the API or the web UI.
- Your full demat number is never exposed either — every surface shows only a
  masked last-four.
- A failed sync leaves your last good holdings alone rather than wiping them.
- Credentials live in your `.env`, or in your operating system's keyring if you
  set `NEPSE_MEROSHARE_USE_KEYRING=true`.

There are automated tests that plant a known fake password and then assert it
appears in neither the health report's raw numbers nor anywhere in its printed
form. If that ever stops being true, the test suite fails.

### The no-credential path

If you would rather not put your CDSC password anywhere at all, export a CSV
from the MeroShare website by hand and import it:

```bash
nt meroshare import --file holdings.csv
```

Same result. No credentials involved.

---

## 19. Exporting

```bash
nt export csv --out-dir exports
nt export parquet --tables price_bars,reconciled_prices
```

Exportable tables: `price_bars`, `reconciled_prices`, `signals`, `index_values`,
`ingest_log`, `corporate_actions`, `paper_trades`. CSV opens in any spreadsheet;
Parquet is for pandas or polars and needs `polars` installed.

---

## 20. The web dashboard

If you prefer clicking to typing:

```bash
.venv/bin/python -m uvicorn nepse_trader.web.api:app --port 8000
cd web && npm install && npm run dev
```

Then open the address Vite prints (usually `http://localhost:5173`). Ten pages:

| Page | What is on it |
|------|---------------|
| Dashboard | Market overview, breadth, movers, your portfolio |
| Symbols | Every symbol you have data for, searchable |
| Symbol detail | One symbol: price chart, signals, statistics, fundamentals |
| Portfolio | Paper positions and realised results |
| Backtest | Run a backtest or a screen from a form |
| Rashifal | The four-horizon prescription as cards |
| Auction | The bid-ceiling calculator |
| MeroShare | Mirrored holdings, and a comparison against paper |
| Research | Search your corpus; read news |
| Health | The ten checks, with history |
| Settings | Watchlist and MeroShare toggles |

The Health page is the same ten checks as `nt health`, with the same colours,
plus the recorded history as a trend. Recording is opt-in there too.

---

## 21. Using it from an AI assistant (MCP)

MCP lets an AI assistant call this tool's read-only functions directly.

```bash
cp .mcp.json.example .mcp.json
# edit .mcp.json: point it at this checkout's .venv/bin/python
nt mcp serve
```

Fifteen bounded read-only tools are exposed: market data, symbol history,
search, backtest, screen, portfolio, MeroShare holdings, rashifal, doses, and
more. Every one is read-only, and all diagnostics go to stderr so the protocol
channel stays clean.

---

## 22. When a website changes (HAR)

Data sites redesign themselves without warning. When `nt ingest` returns zero
rows on a real trading day, or returns obvious nonsense, the site moved and you
need to show the tool where it went.

```bash
nt har analyze   har/captures/sharesansar.har
nt har to-config har/captures/chukul.har --source chukul
nt har redact    har/captures/nepsealpha.har
```

1. In your browser, open DevTools → Network, load the page with the data, and
   "Save all as HAR with content" into `har/captures/`.
2. `har analyze` ranks which requests actually carried the data.
3. `har to-config` prints a `config/sources.yaml` snippet to paste in.
4. **`har redact` before you keep any HAR anywhere.** A raw HAR contains your
   cookies and session tokens. Redacting strips cookies, auth headers, POST
   bodies, sensitive query parameters, and auth response bodies.

Full walkthrough: [`har/HAR_CAPTURE_PLAN.md`](har/HAR_CAPTURE_PLAN.md).

---

## 23. All the settings

Settings come from environment variables prefixed `NEPSE_`, or from a `.env`
file in the project root, which is easier. Everything has a working default —
you can run the whole tool without setting a single one.

### Where things live

| Setting | Default | What it does |
|---------|---------|--------------|
| `NEPSE_DB_PATH` | `data/nepse.db` | The one database file |
| `NEPSE_RAW_CACHE_DIR` | `data/raw` | Cached raw responses, for auditing |
| `NEPSE_LOG_DIR` | `logs` | Per-run log files |
| `NEPSE_SOURCES_FILE` | `config/sources.yaml` | Source and endpoint definitions |
| `NEPSE_COST_MODEL_FILE` | `config/cost_model.yaml` | Commission slabs, SEBON/DP/CGT rates |

### Fetching politely

| Setting | Default | What it does |
|---------|---------|--------------|
| `NEPSE_ENABLED_SOURCES` | `sharesansar,chukul,nepse_official` | Which sources the pipeline iterates |
| `NEPSE_MIN_REQUEST_INTERVAL` | `1.5` | Minimum seconds between requests to one host |
| `NEPSE_REQUEST_TIMEOUT` | `20` | Give up on a request after this many seconds |
| `NEPSE_MAX_RETRIES` | `3` | Retry attempts, with backoff |
| `NEPSE_USER_AGENT` | descriptive string | How you identify yourself. Keep it honest |
| `NEPSE_FETCH_ENGINE` | `httpx` | HTTP client to use |
| `NEPSE_PARSE_ENGINE` | `auto` | HTML parsing backend |
| `NEPSE_SCRAPLING_IMPERSONATE` | *(empty)* | Optional browser profile for the scrapling engine |

**Do not lower `MIN_REQUEST_INTERVAL`.** It is the difference between reading a
public site politely and hammering it.

### Analysis

| Setting | Default | What it does |
|---------|---------|--------------|
| `NEPSE_PRICE_AGREEMENT_TOLERANCE` | `0.005` | How close two prices must be to count as agreeing (0.5%) |
| `NEPSE_ANALYSIS_MODE` | `normal` | `normal` or `ai` |
| `NEPSE_ONLINE` | `true` | Master switch for whether network calls are permitted at all |
| `NEPSE_WATCHLIST` | *(empty)* | Symbols to prefer when a command is not given any |
| `NEPSE_ADVISOR_MAX_SYMBOLS` | `25` | Cap on symbols the advisor considers |

### AI providers

| Setting | Default | What it does |
|---------|---------|--------------|
| `NEPSE_LLM_BULK_PROVIDERS` | *(list)* | Provider chain for cheap, high-volume calls |
| `NEPSE_LLM_SYNTHESIS_PROVIDERS` | *(list)* | Provider chain for the important calls |
| `NEPSE_OPENROUTER_API_KEY` | *(empty)* | Your OpenRouter key |
| `NEPSE_OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | OpenRouter endpoint |
| `NEPSE_OPENROUTER_MODELS` | *(list)* | Which OpenRouter models to try |
| `NEPSE_ANTHROPIC_API_KEY` | *(empty)* | Your Anthropic key |
| `NEPSE_ANTHROPIC_MODEL` | `claude-opus-5` | Anthropic model to use |
| `NEPSE_CLAUDE_CLI_PATH` | `claude` | Use an installed Claude CLI instead of a key |
| `NEPSE_CLAUDE_CLI_MODEL` | *(empty)* | Model override for the CLI path |
| `NEPSE_LLM_TIMEOUT` | `180` | Seconds before giving up on a provider |

### AI spending caps

| Setting | Default | What it does |
|---------|---------|--------------|
| `NEPSE_LLM_MAX_CALLS_PER_DAY` | `40` | Hard cap on calls per day |
| `NEPSE_LLM_MAX_TOKENS_PER_DAY` | `400000` | Hard cap on tokens per day |
| `NEPSE_LLM_MAX_DEEP_PASSES_PER_WEEK` | `2` | Cap on the expensive deep analysis |
| `NEPSE_LLM_CACHE_TTL_HOURS` | `168` | How long an answer is reused (one week) |

These are ceilings, not budgets to aim at. When one is hit, you get a banner and
the deterministic numbers, not a degraded guess.

### Search and MeroShare

| Setting | Default | What it does |
|---------|---------|--------------|
| `NEPSE_RAG_MAX_DOCUMENTS` | `8` | Documents pulled into one answer |
| `NEPSE_RAG_MAX_EVIDENCE_CHARS` | `12000` | Character ceiling on packed evidence |
| `NEPSE_RAG_ENABLE_WEB` | `true` | Allow web search as a fallback |
| `NEPSE_RAG_WEB_SEARCH_URLS` | *(list)* | Sites the web fallback is allowed to read |
| `NEPSE_MEROSHARE_ENABLED` | `false` | Master switch for the mirror |
| `NEPSE_MEROSHARE_BASE_URL` | CDSC API | The CDSC endpoint |
| `NEPSE_MEROSHARE_DP_ID` | *(empty)* | Your DP ID |
| `NEPSE_MEROSHARE_USERNAME` | *(empty)* | Your MeroShare username |
| `NEPSE_MEROSHARE_PASSWORD` | *(empty)* | Your password — prefer the keyring below |
| `NEPSE_MEROSHARE_USE_KEYRING` | `false` | Read credentials from the OS keyring instead |
| `NEPSE_MEROSHARE_KEYRING_SERVICE` | `nepse-trader-meroshare` | Keyring service name |

That is all 43 settings.

---

## 24. When something looks wrong

Run `nt health` first. It will often name the problem outright. If not:

| What you see | Why | What to do |
|--------------|-----|------------|
| `ingest` found 0 rows | It is Friday, Saturday, or a holiday | Nothing. NEPSE trades Sunday–Thursday |
| `ingest` found 0 rows on a Sunday–Thursday | The site changed its layout | Re-capture a HAR (§22) |
| "No signals for X" | Not enough reconciled history to warm up an indicator | Backfill more days (§3) |
| Analysis ignores data you just fetched | You ingested but did not reconcile | Run `nt reconcile --date ...` |
| `403` or `429` in the logs | The site is rate-limiting you | It backs off on its own. Run less often, or raise `NEPSE_MIN_REQUEST_INTERVAL`. Do not try to evade it |
| Lots of low-confidence reconcile rows | Only one source is enabled, or sources genuinely disagree | Enable a second source; inspect `data/raw/` |
| Health says `freshness: warn` | Your newest price is more than 3 trading days old | Run `nt ingest` and `nt reconcile` |
| Health says `schema: fail` | The database is on an older layout than the code | Migrations apply on the next normal command; run any command once |
| Health says `ai: off` or `meroshare: off` | You never enabled them | Nothing. `off` is a healthy answer |
| Paper portfolio looks wrong | A different `--cash` than last time | Use the same `--cash` on every call (§10) |
| SSL error against nepalstock | NEPSE serves an incomplete certificate chain | Use the `nepse-scraper` library, which handles it |
| NEPSE-official returns nothing | `nepse-scraper` is not installed | `pip install nepse-scraper`, or use HAR replay |

Your evidence is always on disk: `logs/` has a file per run, `data/raw/` has the
literal bytes each site returned, and the `ingest_log` table records every
attempt. When two sources disagreed on a price, you can go and read exactly what
each one said.

To confirm the installation itself is sound:

```bash
.venv/bin/python -m pytest -q      # 1284 tests, all offline
.venv/bin/ruff check .             # lint
```

---

## 25. What it will never do

Worth stating plainly, because these are design decisions and not gaps waiting
to be filled:

- **It will never place a real order.** No broker integration exists.
- **It will never apply for an IPO, submit an ASBA form, or bid in an auction.**
  MeroShare is read-only. Auction advice is a calculator you act on yourself.
- **It will never bypass a site's protections.** No CAPTCHA solving, no rate-limit
  evasion, no reconstructing tokens the site did not hand over.
- **It will never let AI change a number.** Prices, quantities, stops, fees,
  taxes and confidences are computed deterministically. AI writes prose around
  them, and the prose is screened.
- **It will never upload your data.** It is one SQLite file on your own disk.
- **It will never log or expose your credentials.** Not in logs, not in the API,
  not in the web UI, not in the health report — and there are tests that prove it.
- **It will never claim certainty about the market.** `1.00` confidence is
  reserved for arithmetic. Directional calls are capped at `0.9`, and the journal
  exists specifically to show you how often they were wrong.

It is a research instrument. Every number it gives you is an input to your own
judgement, not a substitute for it.
