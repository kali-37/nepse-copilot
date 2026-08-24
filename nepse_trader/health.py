"""One read-only health report over everything the toolkit owns.

The daily loop has a lot of moving parts — thirteen migrations, several data
sources, a document corpus, an LLM budget, a read-only MeroShare mirror, a
prediction journal — and each one fails quietly in its own way. A stale
database, a source that stopped parsing, an exhausted token budget and a
half-applied schema all present as "the advice looks wrong", so this module puts
every one of those questions in a single place and answers them the same way.

Three rules hold throughout:

**Nothing here writes, fetches, or spends.** Every check is a local read.
:func:`record_snapshot` is the one exception and it only ever writes the report
it was handed, on explicit request.

**A check never raises.** :func:`system_health` wraps each check so that a
broken check reports itself as ``fail`` instead of taking the whole report with
it — a health report that crashes is the one report you cannot afford to lose.

**No credential, and no account identifier, ever appears in the output.** The
MeroShare check reports *which field names* are missing and never their values,
the same contract :mod:`nepse_trader.meroshare.credentials` already keeps.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from nepse_trader.calendar import is_trading_day, previous_trading_day
from nepse_trader.config import Settings, get_settings, load_sources
from nepse_trader.storage.app_settings import read_bool
from nepse_trader.storage.migrations import MIGRATIONS, has_fts5

log = logging.getLogger("nepse_trader.health")

OK = "ok"
WARN = "warn"
FAIL = "fail"
OFF = "off"

# Worst-wins ordering for the overall verdict. ``off`` is deliberately below
# ``ok``: a feature nobody enabled is not a problem, so it must not be able to
# drag the overall status down.
_SEVERITY = {OFF: 0, OK: 1, WARN: 2, FAIL: 3}

# A reconciled close more than this many trading days old means the daily job is
# not running, as opposed to "today's EOD data has not published yet".
STALE_AFTER_TRADING_DAYS = 3
# Share of recent ingest attempts allowed to fail before it stops being noise.
INGEST_ERROR_WARN_RATIO = 0.25
INGEST_LOG_WINDOW = 20
# Past this fraction of the daily LLM caps, AI mode is close to degrading.
BUDGET_WARN_RATIO = 0.8


@dataclass
class Check:
    """One named question with a verdict, a sentence, and its raw numbers.

    ``detail`` is written for a person reading a terminal; ``metrics`` is what
    the web page and the MCP tool chart. Keeping both means neither caller has
    to re-derive the other's version.
    """

    name: str
    status: str
    detail: str
    metrics: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _worst(statuses: list[str]) -> str:
    if not statuses:
        return OK
    return max(statuses, key=lambda s: _SEVERITY.get(s, 0))


def _trading_days_between(start: date, end: date) -> int:
    """Trading days strictly after *start* up to and including *end*."""
    if end <= start:
        return 0
    count = 0
    cursor = start
    while cursor < end:
        cursor = cursor.fromordinal(cursor.toordinal() + 1)
        if is_trading_day(cursor):
            count += 1
    return count


# --------------------------------------------------------------------------- #
# Individual checks. Each takes what it needs and returns exactly one Check.
# --------------------------------------------------------------------------- #


def check_schema(conn: sqlite3.Connection) -> Check:
    """Every migration in the registry applied, and nothing unknown applied."""
    expected = [version for version, _ in MIGRATIONS]
    try:
        applied = {
            str(row[0]) for row in conn.execute("SELECT version FROM schema_version")
        }
    except sqlite3.Error:
        return Check(
            "schema",
            FAIL,
            "no schema_version table — this database was never migrated",
            {"expected": len(expected), "applied": 0},
        )

    missing = [version for version in expected if version not in applied]
    unknown = sorted(applied - set(expected))
    metrics = {
        "expected": len(expected),
        "applied": len(applied),
        "latest_expected": expected[-1],
        "missing": missing,
        "unknown": unknown,
    }
    if missing:
        return Check(
            "schema",
            FAIL,
            f"{len(missing)} migration(s) not applied: {', '.join(missing)}",
            metrics,
        )
    if unknown:
        # A newer build wrote rows this build does not know about. Read paths
        # still work, so this is a warning rather than a failure.
        return Check(
            "schema",
            WARN,
            f"database is ahead of this build: {', '.join(unknown)}",
            metrics,
        )
    return Check(
        "schema", OK, f"all {len(expected)} migrations applied ({expected[-1]})", metrics
    )


def check_database(storage: Any) -> Check:
    """The database exists, is readable, and holds price rows."""
    path = Path(storage.db_path)
    size_mb = round(path.stat().st_size / (1024 * 1024), 2) if path.exists() else 0.0
    stats = storage.db_stats()
    tables = len(
        [
            row
            for row in storage._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        ]
    )
    metrics = {
        "path": str(path),
        "size_mb": size_mb,
        "tables": tables,
        "symbols": stats.get("symbols_with_data", 0),
        "price_bar_rows": stats.get("price_bar_rows", 0),
        "reconciled_rows": stats.get("reconciled_rows", 0),
        "signal_rows": stats.get("signal_rows", 0),
        "sources_with_data": stats.get("sources_with_data", 0),
    }
    if not metrics["price_bar_rows"]:
        return Check(
            "database",
            WARN,
            "database is empty — run 'ingest' before expecting analysis to work",
            metrics,
        )
    if not metrics["reconciled_rows"]:
        return Check(
            "database",
            WARN,
            f"{metrics['price_bar_rows']:,} raw rows but nothing reconciled — run 'reconcile'",
            metrics,
        )
    return Check(
        "database",
        OK,
        f"{metrics['symbols']} symbols, {metrics['reconciled_rows']:,} reconciled rows, "
        f"{size_mb} MB",
        metrics,
    )


def check_freshness(storage: Any, *, today: date | None = None) -> Check:
    """How far behind the newest reconciled close is, counted in trading days."""
    today = today or datetime.now(UTC).date()
    stats = storage.db_stats()
    latest = stats.get("reconciled_date_latest")
    reference = previous_trading_day(today)
    metrics: dict[str, Any] = {
        "latest_reconciled_date": latest,
        "last_trading_day": reference.isoformat(),
        "trading_days_behind": None,
        "avg_confidence": stats.get("latest_avg_confidence"),
        "disputed": stats.get("latest_disputed"),
        "symbols_on_latest": stats.get("latest_symbols"),
    }
    if not latest:
        return Check("freshness", WARN, "no reconciled prices at all", metrics)

    latest_date = date.fromisoformat(str(latest))
    behind = _trading_days_between(latest_date, reference)
    metrics["trading_days_behind"] = behind
    if behind == 0:
        return Check("freshness", OK, f"current as of {latest} (last trading day)", metrics)
    if behind <= STALE_AFTER_TRADING_DAYS:
        return Check(
            "freshness",
            OK,
            f"{latest} is {behind} trading day(s) behind — within the publishing lag",
            metrics,
        )
    return Check(
        "freshness",
        WARN,
        f"{latest} is {behind} trading days behind {reference} — the daily job may not be running",
        metrics,
    )


def check_ingest(conn: sqlite3.Connection) -> Check:
    """The error rate over the most recent ingest attempts, per source."""
    rows = [
        dict(row)
        for row in conn.execute(
            "SELECT source, status, rows, message, ran_at FROM ingest_log "
            "ORDER BY id DESC LIMIT ?",
            (INGEST_LOG_WINDOW,),
        )
    ]
    metrics: dict[str, Any] = {
        "window": INGEST_LOG_WINDOW,
        "attempts": len(rows),
        "errors": 0,
        "last_run_at": rows[0]["ran_at"] if rows else None,
        "failing_sources": [],
    }
    if not rows:
        return Check("ingest", WARN, "no ingest has ever run", metrics)

    errors = [row for row in rows if str(row["status"]) != "ok"]
    metrics["errors"] = len(errors)
    metrics["failing_sources"] = sorted({str(row["source"]) for row in errors})
    ratio = len(errors) / len(rows)
    if ratio > INGEST_ERROR_WARN_RATIO:
        return Check(
            "ingest",
            WARN,
            f"{len(errors)} of the last {len(rows)} attempts failed "
            f"({', '.join(metrics['failing_sources'])}) — a source layout may have changed",
            metrics,
        )
    return Check(
        "ingest",
        OK,
        f"{len(rows) - len(errors)} of the last {len(rows)} attempts succeeded, "
        f"last run {metrics['last_run_at']}",
        metrics,
    )


def check_config(settings: Settings) -> Check:
    """YAML config parses against its schema, and at least one source is on."""
    from nepse_trader.config_validation import validate_all

    errors = validate_all()
    try:
        sources = load_sources().sources
    except Exception as exc:  # noqa: BLE001 - a broken YAML is the finding
        return Check("config", FAIL, f"sources.yaml could not be loaded: {exc}", {})

    enabled_in_yaml = sorted(name for name, spec in sources.items() if spec.enabled)
    wired = sorted(set(settings.enabled_sources) & set(enabled_in_yaml))
    metrics = {
        "schema_errors": errors,
        "sources_configured": len(sources),
        "enabled_in_yaml": enabled_in_yaml,
        "enabled_in_env": list(settings.enabled_sources),
        "effective_sources": wired,
        "mode": settings.analysis_mode,
        "online": settings.online,
    }
    if errors:
        return Check("config", FAIL, f"{len(errors)} config schema error(s)", metrics)
    if not wired:
        return Check(
            "config",
            WARN,
            "no source is both enabled in sources.yaml and listed in NEPSE_ENABLED_SOURCES",
            metrics,
        )
    return Check(
        "config",
        OK,
        f"{len(wired)} effective source(s): {', '.join(wired)}; mode={settings.analysis_mode}, "
        f"{'online' if settings.online else 'offline'}",
        metrics,
    )


def check_rag(conn: sqlite3.Connection) -> Check:
    """Corpus size, per-kind coverage, and whether ranked search is available."""
    from nepse_trader.rag.index import DocumentIndex

    index = DocumentIndex(conn)
    total = index.count()
    metrics = {
        "documents": total,
        "per_kind": index.kinds(),
        "uses_fts": index.uses_fts,
        "fts5_available": has_fts5(conn),
    }
    if not total:
        return Check("rag", WARN, "document corpus is empty — run 'rag index'", metrics)
    if not index.uses_fts:
        return Check(
            "rag",
            WARN,
            f"{total:,} documents, but searching with LIKE — this SQLite build has no FTS5, "
            "so ranking is unavailable",
            metrics,
        )
    return Check(
        "rag",
        OK,
        f"{total:,} documents across {len(metrics['per_kind'])} kind(s), FTS5 ranking active",
        metrics,
    )


def check_ai(conn: sqlite3.Connection, settings: Settings) -> Check:
    """Whether AI mode could actually answer, and how much budget is left.

    Reads the router's status, which builds providers but performs no network or
    subprocess call: ``available`` is a configuration probe by contract.
    """
    if settings.analysis_mode != "ai":
        return Check(
            "ai",
            OFF,
            "analysis mode is 'normal' — no provider is consulted",
            {"mode": settings.analysis_mode},
        )

    from nepse_trader.ai import LLMRouter

    status = LLMRouter(conn, settings).status()
    usable = {
        tier: [leg["name"] for leg in legs if leg["available"]]
        for tier, legs in status["tiers"].items()
    }
    budget = status["budget"]
    metrics = {
        "mode": settings.analysis_mode,
        "online": status["online"],
        "usable_providers": usable,
        "budget": budget,
        "cache": status["cache"],
    }
    if not any(usable.values()):
        return Check(
            "ai",
            WARN,
            "AI mode is on but no provider is configured — runs will degrade to normal mode",
            metrics,
        )
    if not status["online"]:
        return Check(
            "ai",
            OFF,
            "AI mode is on but offline — deterministic output only, by request",
            metrics,
        )

    calls, max_calls = budget["calls"], max(1, budget["max_calls"])
    tokens, max_tokens = budget["tokens"], max(1, budget["max_tokens"])
    used = max(calls / max_calls, tokens / max_tokens)
    summary = (
        f"{', '.join(sorted({n for names in usable.values() for n in names}))} usable; "
        f"{calls}/{budget['max_calls']} calls and {tokens:,}/{budget['max_tokens']:,} tokens spent today"
    )
    if used >= 1.0:
        return Check("ai", WARN, f"daily budget exhausted — {summary}", metrics)
    if used >= BUDGET_WARN_RATIO:
        return Check("ai", WARN, f"daily budget nearly spent — {summary}", metrics)
    return Check("ai", OK, summary, metrics)


def check_meroshare(conn: sqlite3.Connection, settings: Settings) -> Check:
    """The read-only mirror: toggle, credential completeness, last sync.

    Reports field *names* only. No credential value, and no demat number, is
    read here — the mirror stores a hash and a masked suffix by design.
    """
    from nepse_trader.meroshare import resolve_credentials, sync_status

    stored, updated_at = read_bool(conn, "meroshare_enabled")
    enabled = stored if stored is not None else bool(settings.meroshare_enabled)
    state = sync_status(conn)
    metrics: dict[str, Any] = {
        "enabled": enabled,
        "toggle_source": "database" if stored is not None else "env",
        "toggle_updated_at": updated_at,
        "holdings": state["holdings"],
        "transactions": state["transactions"],
        "last_status": state["last_status"],
        "last_success_at": state["last_success_at"],
        "last_attempt_at": state["last_attempt_at"],
        "attempts": state["attempts"],
        "missing_credentials": [],
    }
    if not enabled:
        return Check(
            "meroshare",
            OFF,
            f"mirror disabled ({metrics['toggle_source']}); "
            f"{state['holdings']} holding(s) held from the last sync",
            metrics,
        )

    resolution = resolve_credentials(settings)
    metrics["missing_credentials"] = resolution.credentials.missing()
    metrics["credential_source"] = resolution.credentials.source
    if not resolution.complete:
        return Check(
            "meroshare",
            WARN,
            "mirror enabled but credentials incomplete; missing: "
            f"{', '.join(metrics['missing_credentials'])} "
            "(or use 'meroshare import' for a credential-free CSV path)",
            metrics,
        )
    if state["last_status"] and state["last_status"] != "ok":
        return Check(
            "meroshare",
            WARN,
            f"last sync failed at {state['last_attempt_at']}; "
            f"{state['holdings']} holding(s) retained from {state['last_success_at']}",
            metrics,
        )
    if not state["attempts"]:
        return Check("meroshare", OK, "enabled and configured; never synced yet", metrics)
    return Check(
        "meroshare",
        OK,
        f"{state['holdings']} holding(s) mirrored, last success {state['last_success_at']}",
        metrics,
    )


def check_journal(conn: sqlite3.Connection) -> Check:
    """Prediction lifecycle backlog: what is open, scored-but-unreviewed, retired."""
    rows = {
        str(row["status"]): int(row["n"])
        for row in conn.execute("SELECT status, COUNT(*) AS n FROM predictions GROUP BY status")
    }
    overdue = conn.execute(
        "SELECT COUNT(*) AS n FROM predictions WHERE status='open' AND deadline < ?",
        (datetime.now(UTC).date().isoformat(),),
    ).fetchone()["n"]
    calibration = conn.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(resolved), 0) AS resolved FROM calibration"
    ).fetchone()
    metrics = {
        "by_status": rows,
        "total": sum(rows.values()),
        "overdue_open": int(overdue),
        "calibration_rows": int(calibration["n"]),
        "resolved_predictions": int(calibration["resolved"]),
    }
    if not metrics["total"]:
        return Check(
            "journal",
            OK,
            "no predictions recorded yet — the journal fills up as the advisor runs",
            metrics,
        )
    if overdue:
        return Check(
            "journal",
            WARN,
            f"{overdue} open prediction(s) past their deadline — run 'journal score' on them",
            metrics,
        )
    awaiting = rows.get("scored", 0)
    if awaiting:
        return Check(
            "journal",
            OK,
            f"{metrics['total']} prediction(s); {awaiting} scored and awaiting review",
            metrics,
        )
    return Check(
        "journal",
        OK,
        f"{metrics['total']} prediction(s), {metrics['resolved_predictions']} resolved into calibration",
        metrics,
    )


def check_paper(storage: Any) -> Check:
    """The replay-derived paper account, if anything was ever traded."""
    trades = storage.paper_trades()
    metrics: dict[str, Any] = {"trades": len(trades)}
    if not trades:
        return Check("paper", OFF, "no paper trades recorded", metrics)

    from nepse_trader.trading.portfolio import PaperPortfolio

    portfolio = PaperPortfolio(initial_cash=100_000.0)
    for trade in trades:
        if trade.side.value == "BUY":
            portfolio.buy(trade.symbol, trade.price, trade.quantity, trade.business_date, trade.strategy)
        else:
            portfolio.sell(trade.symbol, trade.price, trade.quantity, trade.business_date, trade.strategy)
    metrics.update(
        {
            "cash": float(portfolio.cash),
            "positions": len(portfolio.positions),
            "realized_pnl": float(portfolio.realized_pnl),
        }
    )
    return Check(
        "paper",
        OK,
        f"{len(trades)} trade(s) replayed: cash {portfolio.cash:.2f}, "
        f"{len(portfolio.positions)} position(s), realized {portfolio.realized_pnl:.2f}",
        metrics,
    )


# --------------------------------------------------------------------------- #
# The report
# --------------------------------------------------------------------------- #

CHECK_ORDER = (
    "schema",
    "database",
    "freshness",
    "ingest",
    "config",
    "rag",
    "ai",
    "meroshare",
    "journal",
    "paper",
)


def _guarded(name: str, fn) -> Check:
    """Run one check; turn its own breakage into a ``fail`` row, not an exception."""
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - a broken check is itself the finding
        log.warning("health check %s raised %s", name, type(exc).__name__)
        return Check(name, FAIL, f"check raised {type(exc).__name__}: {exc}", {})


def system_health(
    storage: Any,
    settings: Settings | None = None,
    *,
    today: date | None = None,
) -> dict[str, Any]:
    """Every check, in a stable order, plus the worst-wins overall verdict.

    *storage* is an open :class:`~nepse_trader.storage.Storage`; nothing is
    written and no network client is constructed.
    """
    settings = settings or get_settings()
    conn = storage._conn
    checks = [
        _guarded("schema", lambda: check_schema(conn)),
        _guarded("database", lambda: check_database(storage)),
        _guarded("freshness", lambda: check_freshness(storage, today=today)),
        _guarded("ingest", lambda: check_ingest(conn)),
        _guarded("config", lambda: check_config(settings)),
        _guarded("rag", lambda: check_rag(conn)),
        _guarded("ai", lambda: check_ai(conn, settings)),
        _guarded("meroshare", lambda: check_meroshare(conn, settings)),
        _guarded("journal", lambda: check_journal(conn)),
        _guarded("paper", lambda: check_paper(storage)),
    ]
    counts = {OK: 0, WARN: 0, FAIL: 0, OFF: 0}
    for check in checks:
        counts[check.status] = counts.get(check.status, 0) + 1
    return {
        "status": _worst([c.status for c in checks]),
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "counts": counts,
        "checks": [c.as_dict() for c in checks],
    }


def problems(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Only the checks that need a human — what a cron job should print."""
    return [c for c in report["checks"] if c["status"] in (WARN, FAIL)]


# --------------------------------------------------------------------------- #
# Snapshot history — the only write path in this module, and only on request.
# --------------------------------------------------------------------------- #


def record_snapshot(conn: sqlite3.Connection, report: dict[str, Any]) -> int:
    """Persist *report* and return its row id.

    Called only when a caller explicitly asks (``health --record``, or the API's
    ``?record=true``), so polling the report never grows the database.
    """
    counts = report.get("counts", {})
    cursor = conn.execute(
        """INSERT INTO health_snapshots
               (captured_at, status, ok, warn, fail, off, report)
           VALUES (?,?,?,?,?,?,?)""",
        (
            report["generated_at"],
            report["status"],
            int(counts.get(OK, 0)),
            int(counts.get(WARN, 0)),
            int(counts.get(FAIL, 0)),
            int(counts.get(OFF, 0)),
            json.dumps(report, default=str),
        ),
    )
    conn.commit()
    return int(cursor.lastrowid or 0)


def snapshot_history(conn: sqlite3.Connection, *, limit: int = 30) -> list[dict[str, Any]]:
    """Recent snapshots, newest first, without their full JSON payload.

    The payload is the bulky part and a trend view never needs it; use
    :func:`snapshot` for one complete report.
    """
    rows = conn.execute(
        "SELECT id, captured_at, status, ok, warn, fail, off FROM health_snapshots "
        "ORDER BY captured_at DESC, id DESC LIMIT ?",
        (max(1, int(limit)),),
    ).fetchall()
    return [dict(row) for row in rows]


def snapshot(conn: sqlite3.Connection, snapshot_id: int) -> dict[str, Any] | None:
    """One stored report in full, or None when that id was never recorded."""
    row = conn.execute(
        "SELECT report FROM health_snapshots WHERE id = ?", (snapshot_id,)
    ).fetchone()
    if row is None:
        return None
    raw = row["report"] if hasattr(row, "keys") else row[0]
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None

