# Developer Guide — NEPSE Trader

How to build on, extend, and maintain the codebase. Read
[`how_it_works.md`](how_it_works.md) first for the algorithms; this doc is about
the *seams* — the contracts you code against and the recipes for common changes.

---

## 1. Layout

```
nepse_trader/
├── __init__.py
├── models.py            # Pydantic data contracts (the shared vocabulary)
├── config.py            # Settings (env) + sources.yaml + cost_model.yaml loaders
├── pipeline.py          # DailyPipeline orchestrator + build_clients()
├── reporting.py         # markdown/rich reports + Alerter (webhook, off by default)
├── ingest/
│   ├── base.py          # BaseClient (throttle/retry/cache) + SourceClient ABC
│   ├── sharesansar.py   # primary source (HTML + DataTables JSON)
│   ├── merolagani.py    # secondary (ASP.NET HTML)
│   ├── chukul.py        # optional (config-driven JSON)
│   ├── nepse_official.py# optional nepse_scraper adapter + HAR replay
│   └── reconcile.py     # cross-source consensus
├── analysis/
│   ├── indicators.py    # SMA/EMA/RSI/MACD/Bollinger/ATR (pure)
│   ├── strategies.py    # Strategy ABC + concrete strategies + registry
│   ├── backtest.py      # Backtester + BacktestResult
│   └── costs.py         # CostEngine (commission/SEBON/DP/CGT)
├── trading/
│   └── portfolio.py     # PaperPortfolio (WAC, FIFO lots)
├── storage/
│   └── db.py            # SQLite layer (idempotent upserts)
├── har/
│   └── analyzer.py      # HAR analyze / to-config / redact
└── cli/
    └── main.py          # Typer CLI

config/   sources.yaml, cost_model.yaml
har/      HAR_CAPTURE_PLAN.md, captures/ (git-ignored)
docs/     RUNBOOK.md
tests/    one test_*.py per module (166 tests, all offline)
```

---

## 2. Coding standards

- **Python ≥ 3.11.** Start every module with `from __future__ import annotations`.
- **Lint:** `ruff check .` must pass. Config in `pyproject.toml`
  (`select = E,F,I,UP,B,W`; line length 100 with E501 ignored; imports sorted).
- **Types everywhere.** Public functions are fully annotated. Models are Pydantic v2.
- **Separate parsing from I/O.** Network lives in `BaseClient`; parsing lives in
  pure `parse_*` functions/staticmethods that take raw text/dict and return models.
  This is the single most important convention — it's why tests run offline.
- **Defensive ingestion.** Fetch methods must degrade to `[]`/`None` on failure,
  never raise into the pipeline.
- **Money is rounded at the cost layer** (`_round2`), not sprinkled through callers.
- **No new runtime deps** without a strong reason; the stack is intentionally small
  (httpx, pydantic, pyyaml, typer, rich, tenacity, dateutil, selectolax).

---

## 3. The data contracts (`models.py`)

Everything speaks these Pydantic models. Construct with keyword args; `symbol` is
auto-uppercased on `PriceBar`, `FloorsheetEntry`, `Signal`, `PaperTrade`, `Position`.

| Model | Purpose | Key fields |
|-------|---------|-----------|
| `PriceBar` | one security's OHLCV for a date+source | `symbol, business_date, open/high/low/close, previous_close, volume, turnover, trades, source`; `.change`, `.change_percent` |
| `IndexValue` | an index reading | `name, business_date, value, change, change_percent, source` |
| `FloorsheetEntry` | one matched trade | `contract_id, symbol, business_date, buyer_broker, seller_broker, quantity, rate, amount, source` |
| `MarketStatus` | open/closed | `is_open, as_of, session, source` |
| `ReconciledPrice` | cross-source consensus | `…, sources_agreeing, sources_present, disputed_fields, confidence`; `.is_trustworthy` |
| `Signal` | a strategy decision | `symbol, business_date, action, strategy, strength, reason, price, indicators` |
| `PaperTrade` | an executed paper trade | full cost breakdown + `net_amount` |
| `Position` | a holding | `symbol, quantity, avg_cost`; `.cost_basis` |

Enums: `SourceName`, `SignalAction` (BUY/SELL/HOLD), `OrderSide` (BUY/SELL).

---

## 4. Recipe: add a new data source

1. Create `nepse_trader/ingest/yoursite.py`:

   ```python
   from __future__ import annotations
   from datetime import date
   from nepse_trader.config import SourceSpec, load_sources
   from nepse_trader.ingest.base import BaseClient, SourceClient
   from nepse_trader.models import PriceBar, SourceName

   class YourSiteClient(SourceClient):
       name = SourceName.YOURSITE   # add to the SourceName enum first

       def __init__(self, client: BaseClient | None = None, source_spec: SourceSpec | None = None):
           self.client = client or BaseClient()
           self.spec = source_spec or load_sources().get("yoursite")

       def fetch_prices(self, business_date: date | None = None) -> list[PriceBar]:
           try:
               url = self.spec.endpoints["today_price"].url  # or a hardcoded fallback
               res = self.client.fetch(url, params={"date": business_date.isoformat()} if business_date else None)
               return self.parse_prices(res.text, business_date, self.name)
           except Exception:
               return []   # degrade, never crash the pipeline

       @staticmethod
       def parse_prices(raw: str, business_date, source) -> list[PriceBar]:
           ...  # pure: raw -> [PriceBar]; this is what tests exercise
   ```

2. Add `YOURSITE = "yoursite"` to `SourceName` in `models.py`.
3. Add a `yoursite:` block to `config/sources.yaml` (base_url, endpoints, `enabled`).
4. Register the factory in `pipeline._CLIENT_FACTORIES`.
5. Add `tests/test_yoursite.py`: feed fixture HTML/JSON to `parse_prices` (no
   network) + one `respx` test that mocks the endpoint.

The HTTP `BaseClient` gives you throttling, retries, 403/429 backoff and the audit
cache for free — always fetch through it. Discover the real endpoints with the HAR
toolkit (`har analyze` / `to-config`) rather than guessing.

---

## 5. Recipe: add a new strategy

1. Subclass `Strategy` in `analysis/strategies.py`:

   ```python
   class SupertrendStrategy(Strategy):
       name = "supertrend"
       def __init__(self, period: int = 10, multiplier: float = 3.0):
           self.period, self.multiplier = period, multiplier

       def generate(self, bars: list[PriceBar]) -> list[Signal]:
           closes, has_close = self._closes(bars)   # carries gap days forward, masks them
           out: list[Signal] = []
           prev_state = None
           for i, bar in enumerate(bars):
               if not has_close[i]:
                   continue
               # ... compute state from indicators ...
               action = ...  # emit BUY/SELL only on state change, else HOLD
               out.append(self._emit(bar, action, strength, reason, {"...": value}))
           return out
   ```

2. Register it in `STRATEGIES = {...}`. `build_strategy("supertrend")` then works
   and the CLI picks it up automatically (the help string lists `STRATEGIES`).
3. Add `tests/test_strategies.py` cases: craft a synthetic price path that forces a
   known crossover and assert BUY-then-SELL on the right dates, HOLD elsewhere,
   `0 ≤ strength ≤ 1`, and that `indicators` is populated.

Conventions: long-only, emit on **state change** only (see the SMA/Bollinger
examples), and never emit on a no-close day (`has_close[i]` gate).

---

## 6. Recipe: add a new indicator

Add a pure function to `analysis/indicators.py` returning a list aligned to the
input with `None` during warm-up:

```python
def wma(values: Sequence[float], period: int) -> list[Number]:
    out: list[Number] = [None] * len(values)
    weights = list(range(1, period + 1)); denom = sum(weights)
    for i in range(period - 1, len(values)):
        window = values[i - period + 1 : i + 1]
        out[i] = sum(w * v for w, v in zip(window, weights, strict=True)) / denom
    return out
```

Test exact values against hand-computed expectations (see `tests/test_indicators.py`).

---

## 7. Config system (`config.py`)

- `get_settings()` → `Settings` (cached; env-driven, prefix `NEPSE_`). In tests
  that change env, call `get_settings.cache_clear()`.
- `load_sources(path=None)` → `SourcesConfig`; `.get(name)` → `SourceSpec` with an
  `endpoints: dict[str, EndpointSpec]`.
- `load_cost_model(path=None)` → `CostModel` (slabs + rates).

Endpoints and the cost model are YAML so they can be tuned (e.g. after a HAR
refresh, or a SEBON rate change) without code edits.

---

## 8. Storage invariants (`storage/db.py`)

- Idempotent: `price_bars` PK `(symbol, business_date, source)`; reconciled PK
  `(symbol, business_date)`; signals PK `(symbol, business_date, strategy)`.
- Use the typed read helpers (`price_history`, `reconciled_history`,
  `bars_for_date`, `paper_trades`) rather than raw SQL in callers.
- All writes are parameterized (no string interpolation) — keep it that way.
- If you add a table, add a migration to `nepse_trader/storage/migrations.py`, add typed read/write methods, and a test
  in `tests/test_storage.py`.

---

## 9. Testing

- Run: `.venv/bin/python -m pytest -q` (166 tests) and `.venv/bin/ruff check .`.
- **All tests are offline.** Network is mocked with `respx`; parsing is tested with
  inline fixtures; time-sensitive logic uses explicit dates (or `freezegun`).
- One `test_<module>.py` per module. New code ships with its tests in the same PR.
- Prefer testing the pure `parse_*`/math functions directly (fast, exact) and add
  one integration test through the client/pipeline for wiring.
- The headline invariant test is the cost worked example (`tests/test_costs.py`) —
  if you touch `costs.py` or `cost_model.yaml`, that must still hold to the paisa.

---

## 10. The orchestrator (`pipeline.py`)

`DailyPipeline` wires storage + clients + cost engine:

- `ingest(date)` → pulls each enabled client, upserts, logs, isolates failures.
- `reconcile(date)` → consensus over `bars_for_date`, upserts `reconciled_prices`.
- `reconciled_bars(symbol)` → reconciled history as `PriceBar[]` for indicators.
- `signals_for(symbol, strategy, **kw)` / `latest_signals(symbols, strategy)`.
- `replay_portfolio(cash)` → rebuilds a `PaperPortfolio` from stored trades.

`build_clients()` maps `settings.enabled_sources` → client instances, respecting
each source's `enabled` flag in `sources.yaml`.

---

## 11. Gotchas & conventions

- **Symbols are uppercased by the models** — don't re-normalize in callers.
- **`_closes()` masks gap days** — a None close carries forward for indicator math
  but `has_close[i]` is False so no signal is emitted there. Respect this in new
  strategies.
- **MACD is a zero-line cross by design** (documented in the class) — not a
  signal-line cross. Don't "fix" it to a histogram cross; it's intentional.
- **CGT boundary is `> 365` days** for long-term, and **commission slab boundaries
  belong to the lower (higher-rate) tier**. There are regression tests for both.
- **Paper state is replay-derived** — keep `--cash` consistent; don't add a second
  source of truth.
- **HAR redaction** must strip new secret-bearing fields if you extend it; the
  redaction test asserts a known token is absent from the whole dumped HAR.

---

## 12. Suggested contribution workflow

1. Branch from `master`.
2. Make the change + tests; keep modules' parse/fetch separation.
3. `ruff check .` and `pytest -q` green.
4. If you added/verified an endpoint, update `config/sources.yaml` (and note the
   `confidence`).
5. Update the relevant doc (`how_it_works.md` for algorithms, `how_to_use.md` for
   commands). Open a PR.

See [`what_to_add_next.md`](what_to_add_next.md) for a prioritized backlog and
[`make_evenBetter.md`](make_evenBetter.md) for engineering-quality upgrades.
