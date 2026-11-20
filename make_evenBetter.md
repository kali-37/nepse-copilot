# Make It Even Better — Engineering Quality Upgrades

> Historical engineering proposals. Many items below are now implemented;
> [current completion status](docs/COMPLETION_STATUS.md) is the live status reference.

[`what_to_add_next.md`](what_to_add_next.md) covers *features*. This doc covers
*engineering quality* — the changes that make the codebase more correct, faster,
safer, and easier to work in. Ordered by impact-to-effort.

---

## 1. Correctness & financial precision

### 1.1 Use `Decimal` for money — **high impact**
**Problem:** all monetary math is `float`. We round to paisa at the cost layer,
which is fine today (the worked example is exact), but floats can bite at scale
(accumulated rounding across thousands of trades, slab boundaries).
**Fix:** introduce a `Money` type (or `decimal.Decimal` with a fixed context) in
`analysis/costs.py` and `trading/portfolio.py`; keep indicators/stats in float
(they're statistical, not ledger). Pydantic supports `Decimal` natively.

### 1.2 Property-based tests (Hypothesis) — **high impact, low effort**
**Why:** the cost engine, reconciliation clustering, and indicators have
invariants that example tests can miss (e.g. "commission is monotonic in amount",
"reconciled close lies within the min/max of agreeing sources", "EMA ≤ max(input)").
**Fix:** add `hypothesis` to dev deps and a `tests/test_properties.py`.

### 1.3 Golden-file tests for parsers — **medium**
**Why:** HTML/JSON layouts drift. Commit a few *redacted* real responses as
fixtures and assert the parsers still produce the expected models — this catches
silent breakage the unit fixtures won't.
**Fix:** `tests/fixtures/*.html|json` + parser golden tests.

---

## 2. CI / DX

### 2.1 CI pipeline — **high impact, low effort**, `.github/workflows/ci.yml`
Run `ruff check`, `pytest`, and a type-check on every push/PR. Cache the `uv`
environment. Gate merges on green. This is the highest-leverage single change.

### 2.2 Static typing in CI — **medium**
Add `mypy` (or `pyright`) with a pragmatic config and fix the gaps. The code is
already fully annotated, so this is mostly turning on the check and tightening a
few `Any`s (e.g. `_construct`, storage row access).

### 2.3 Coverage measurement — **low**
`pytest --cov=nepse_trader` with a floor (e.g. 90%). Surface untested branches —
the defensive `except` paths especially.

### 2.4 Pre-commit hooks — **low**
`pre-commit` running ruff (lint+format) so style never reaches review.

---

## 3. Robustness & resilience

### 3.1 Async, concurrent ingestion — **high impact**, `ingest/base.py`
**Why:** sources are fetched sequentially today. With `httpx.AsyncClient` the
per-source pulls run concurrently (still throttled per host), cutting daily-run
wall-clock substantially as more sources come online.
**Fix:** an async `BaseClient` variant + `asyncio.gather` in the pipeline; keep the
sync path for the CLI simplicity.

### 3.2 Per-source circuit breaker — **medium**
**Why:** a source that's failing should be skipped fast (and surfaced) rather than
retried every run. Track recent failures in `ingest_log` and short-circuit.
**Fix:** a small breaker around each client in `DailyPipeline.ingest`.

### 3.3 Respect `Retry-After` and `robots.txt` programmatically — **medium**
**Why:** we throttle and back off, but we don't yet parse `Retry-After` headers or
fetch/honor `robots.txt` at runtime (we checked it manually). Doing both in code
makes the politeness guarantees enforceable, not just documented.
**Fix:** honor `Retry-After` in the backoff; add a cached `robots.txt` check before
first request to a host.

### 3.4 Schema-driven HTML parsing — **medium**, `ingest/sharesansar.py`, `merolagani.py`
**Why:** column-position parsing is brittle. Move all column maps to a declarative
spec (header-name → model field) so a layout change is a config edit, not a code
change. (MeroLagani already maps by header — generalize it.)

---

## 4. Scale & storage

### 4.1 Pluggable storage backend (Postgres) — **L**
**Why:** SQLite is perfect for one user; a shared/large deployment wants Postgres.
**Fix:** define a `Storage` protocol and a Postgres implementation behind the same
typed read/write methods; the rest of the code is already storage-agnostic.

### 4.2 Compress & rotate the raw audit cache — **S**
`data/raw/*.txt` grows unbounded. Gzip on write and prune older than N days.

### 4.3 Migrations — **S**
A tiny schema-version table + ordered migration scripts, so adding columns
(e.g. adjusted close, corporate actions) is safe on existing DBs.

---

## 5. Security & ethics hardening

### 5.1 Secret scanning on HAR commits — **S**
The redactor is good; add a `pre-commit` guard that refuses to commit any
`*.har` (even redacted) and scans for token-shaped strings, so a secret can never
slip in via a capture.

### 5.2 Configurable, conservative politeness defaults — **S**
Surface per-source rate limits in `sources.yaml` and default them conservatively;
log a clear notice whenever the throttle delays a request.

### 5.3 SBOM + pinned deps — **S**
Pin exact versions (a lockfile) and generate an SBOM for supply-chain hygiene.

---

## 6. Packaging & distribution

### 6.1 Docker image — **S**, `Dockerfile`
A slim image with the venv baked in and `run-daily` as the entrypoint — drop-in
for a cron container or a scheduled cloud job.

### 6.2 Publish to PyPI — **S**
The project is already a proper `pyproject` package with a console script; add a
release workflow.

### 6.3 Versioned config & cost-model changelog — **S**
Stamp `cost_model.yaml` with an `effective_date` and keep a changelog, so historical
backtests can use the fee schedule that was actually in force.

---

## 7. Observability

- **Structured logging** (JSON) with per-run IDs, so daily runs are queryable.
- **Run metrics** persisted (bars/source, reconcile confidence distribution,
  leaderboard top) to a `run_metrics` table → trend the bot's own health.
- **Anomaly alerts**: warn when a source's row count or average confidence drops
  sharply vs the trailing average (early detection of silent breakage).

---

## Suggested order of attack

1. **CI + property tests** (2.1, 1.2) — cheap, protects everything else.
2. **Decimal money** (1.1) — correctness at the core.
3. **Async ingestion + circuit breaker** (3.1, 3.2) — makes "all sources" fast and robust.
4. **Schema-driven parsing + golden tests** (3.4, 1.3) — durability against layout drift.
5. **Docker + Postgres + migrations** (6.1, 4.1, 4.3) — when you go from one user to many.

Each is independently shippable and keeps `pytest` + `ruff` green.
