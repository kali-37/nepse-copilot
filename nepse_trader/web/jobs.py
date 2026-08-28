"""Background jobs for the web dashboard.

The CLI can afford to block: you typed the command, so you sit and watch the
spinner. A browser cannot. ``run-daily`` over the full universe takes minutes,
and an HTTP request open that long is indistinguishable from a hang — the tab
shows nothing, the proxy may time it out, and a reload starts the work again.
So the dashboard POSTs a job, gets an id back immediately, and polls for stages,
counters and log lines.

Three constraints keep this small and honest:

* **One job at a time.** Every job writes to the same SQLite file. Queueing two
  ``run-daily`` runs would let their upserts interleave for no benefit, and
  there is exactly one operator, so a second submit is refused with the id of
  the job already running rather than silently enqueued.
* **Each job owns its database connection.** The request path shares one
  long-lived ``Storage`` opened with ``check_same_thread=False``. Handing that
  to a worker thread would interleave a multi-minute write transaction with
  whatever the UI is reading. A job opens its own ``Storage`` against the same
  WAL database — WAL is what makes one writer plus concurrent readers safe —
  and closes it in a ``finally``.
* **Cancel is cooperative.** There is no way to kill a thread mid-HTTP-request
  safely, so cancel sets an event and the progress callbacks raise
  :class:`JobCancelled` the next time they fire. Long stages that report
  per-symbol progress therefore cancel promptly; a stage sitting in one network
  call finishes that call first.

Nothing here is persisted. Job history lives in memory and dies with the
server, which is the right lifetime for "what is happening right now" — the
durable record of a run is the data it wrote and the ``ingest_log`` rows.
"""

from __future__ import annotations

import logging
import threading
import traceback
import uuid
from collections import OrderedDict, deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from nepse_trader.analysis.strategies import STRATEGIES
from nepse_trader.calendar import is_trading_day
from nepse_trader.config import Settings
from nepse_trader.pipeline import DailyPipeline
from nepse_trader.storage import Storage

log = logging.getLogger("nepse_trader.web.jobs")

#: Log lines kept per job. A full-universe run emits one line per symbol, and
#: the UI only ever shows the tail, so there is no reason to grow without bound.
MAX_LOG_LINES = 400

#: Finished jobs kept for inspection. Older ones are dropped oldest-first.
MAX_HISTORY = 40


class JobBusy(RuntimeError):
    """Another job is already running.

    Carries the running job's id so the caller can redirect the operator to it
    instead of reporting a bare failure.
    """

    def __init__(self, job_id: str, kind: str) -> None:
        super().__init__(f"{kind} job {job_id} is already running")
        self.job_id = job_id
        self.kind = kind


class JobCancelled(RuntimeError):
    """Raised inside a worker once the operator has asked it to stop."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class JobStage:
    """One named step of a job, with an optional item counter.

    ``current``/``total`` are only meaningful when a stage can count its work
    (screening knows its symbol list; a single network fetch does not). Both
    stay at 0 otherwise and the UI shows an indeterminate bar.
    """

    name: str
    label: str
    status: str = "pending"  # pending | running | ok | failed | skipped
    detail: str = ""
    current: int = 0
    total: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "status": self.status,
            "detail": self.detail,
            "current": self.current,
            "total": self.total,
        }


@dataclass
class Job:
    """A unit of background work and everything the UI needs to render it."""

    id: str
    kind: str
    params: dict[str, Any]
    stages: list[JobStage]
    status: str = "queued"  # queued | running | done | failed | cancelled
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str = field(default_factory=_now)
    started_at: str | None = None
    finished_at: str | None = None
    log: deque[str] = field(default_factory=lambda: deque(maxlen=MAX_LOG_LINES))
    cancel_event: threading.Event = field(default_factory=threading.Event)

    @property
    def terminal(self) -> bool:
        return self.status in ("done", "failed", "cancelled")

    def as_dict(self, *, with_log: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "kind": self.kind,
            "params": self.params,
            "status": self.status,
            "stages": [s.as_dict() for s in self.stages],
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "cancel_requested": self.cancel_event.is_set(),
        }
        if with_log:
            payload["log"] = list(self.log)
        return payload


class JobContext:
    """What a handler is given: its own storage, its params, and a way to talk.

    Handlers never touch the shared request-path ``Storage``; they use
    ``ctx.storage`` and ``ctx.pipeline``, both scoped to this thread.
    """

    def __init__(self, job: Job, storage: Storage, settings: Settings, lock: threading.RLock):
        self.job = job
        self.storage = storage
        self.settings = settings
        self._lock = lock
        self._stage: JobStage | None = None

    # ------------------------------------------------------------- params
    @property
    def params(self) -> dict[str, Any]:
        return self.job.params

    def param_date(self, key: str) -> date | None:
        raw = self.params.get(key)
        return date.fromisoformat(raw) if raw else None

    def strategy_list(self, key: str = "strategies") -> list[str]:
        """Parse a ``"all"`` / comma-list strategy parameter, mirroring the CLI."""
        raw = (self.params.get(key) or "all").strip()
        if raw.lower() == "all":
            return list(STRATEGIES)
        wanted = [s.strip() for s in raw.split(",") if s.strip()]
        unknown = [s for s in wanted if s not in STRATEGIES]
        if unknown:
            raise ValueError(f"unknown strategies: {', '.join(unknown)}")
        return wanted or list(STRATEGIES)

    def pipeline(self, *, include_all_sources: bool = False) -> DailyPipeline:
        return DailyPipeline(storage=self.storage, include_all_sources=include_all_sources)

    # --------------------------------------------------------------- comms
    def log_line(self, message: str) -> None:
        with self._lock:
            self.job.log.append(f"{_now()[11:19]}  {message}")
        log.info("job %s (%s): %s", self.job.id, self.job.kind, message)

    def check_cancelled(self) -> None:
        if self.job.cancel_event.is_set():
            raise JobCancelled

    @contextmanager
    def stage(self, name: str) -> Iterator[JobStage]:
        """Mark a stage running for the duration of the block.

        On a clean exit the stage becomes ``ok``; on any exception it becomes
        ``failed`` and the exception propagates so the job as a whole fails.
        Cancellation is not a stage failure — it is recorded as ``skipped``,
        because nothing went wrong with the work itself.
        """
        target = next((s for s in self.job.stages if s.name == name), None)
        if target is None:  # pragma: no cover — handler/stage-list mismatch
            raise KeyError(f"job {self.job.kind} has no stage {name!r}")
        self.check_cancelled()
        with self._lock:
            target.status = "running"
        self._stage = target
        try:
            yield target
        except JobCancelled:
            with self._lock:
                target.status = "skipped"
                target.detail = "cancelled"
            raise
        except Exception as exc:
            with self._lock:
                target.status = "failed"
                target.detail = str(exc) or exc.__class__.__name__
            raise
        else:
            with self._lock:
                target.status = "ok"
        finally:
            self._stage = None

    def skip_remaining(self, detail: str) -> None:
        """Mark every not-yet-started stage as skipped, with a reason."""
        with self._lock:
            for stage in self.job.stages:
                if stage.status == "pending":
                    stage.status = "skipped"
                    stage.detail = detail

    def progress(self, current: int, total: int, label: str = "") -> None:
        """Update the running stage's counter. Also the cancellation check.

        This is shaped to be passed straight to the existing ``on_progress``
        callbacks in :func:`nepse_trader.analysis.screen.screen` and
        :func:`nepse_trader.rag.build.build_corpus`, which both call
        ``(i, total, symbol)``.
        """
        self.check_cancelled()
        stage = self._stage
        if stage is None:  # pragma: no cover — progress outside a stage
            return
        with self._lock:
            stage.current = current
            stage.total = total
            if label:
                stage.detail = label


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------
Handler = Callable[[JobContext], dict[str, Any]]

#: kind -> (stage name, human label) in execution order. The registry builds the
#: stage list from this before the thread starts, so the UI can render the whole
#: shape of a job — including steps not reached yet — from the first poll.
JOB_STAGES: dict[str, list[tuple[str, str]]] = {
    "ingest": [("ingest", "Download from sources")],
    "reconcile": [("reconcile", "Cross-check sources")],
    # No advisor stage: the dashboard already runs the advisor synchronously via
    # POST /api/advisor/run from the Rashifal page, and that path is wired to the
    # shared request-path connection. Driving it from a worker thread would mean
    # a second, thread-unsafe route to the same feature for no gain.
    "run-daily": [
        ("ingest", "Download from sources"),
        ("reconcile", "Cross-check sources"),
        ("analyse", "Signals, stats and backtests"),
    ],
    "rag-index": [
        ("index", "Index stored data"),
        ("news", "Fetch news and announcements"),
    ],
    "screen": [("screen", "Backtest every strategy")],
}


def _job_ingest(ctx: JobContext) -> dict[str, Any]:
    bd = ctx.param_date("business_date")
    all_sources = bool(ctx.params.get("all_sources", True))
    pipe = ctx.pipeline(include_all_sources=all_sources)
    with ctx.stage("ingest") as stage:
        stage.detail = f"{len(pipe.clients)} source(s)"
        ctx.log_line(f"ingesting from {len(pipe.clients)} source(s)")
        report = pipe.ingest(bd)
        stage.detail = f"{report.total_bars} bars from {len(report.per_source)} source(s)"
        for name, count in report.per_source.items():
            ctx.log_line(f"  {name}: {count} bars")
        if report.errors:
            ctx.log_line(f"sources with errors: {', '.join(report.errors)}")
    return {"ingest": report.as_dict()}


def _job_reconcile(ctx: JobContext) -> dict[str, Any]:
    pipe = ctx.pipeline()
    # The last ingested board, not the calendar: weekends and holidays make
    # "today" an empty date, and the job would report 0 symbols reconciled.
    bd = ctx.param_date("business_date") or pipe.storage.latest_price_date() or date.today()
    with ctx.stage("reconcile") as stage:
        prices = pipe.reconcile(bd)
        low = [p for p in prices if not p.is_trustworthy]
        stage.detail = f"{len(prices)} symbols, {len(low)} flagged"
        ctx.log_line(f"reconciled {len(prices)} symbols; {len(low)} low-confidence/disputed")
    return {
        "business_date": bd.isoformat(),
        "reconciled": len(prices),
        "flagged": len(low),
        "rows": [
            {
                "symbol": p.symbol,
                "business_date": p.business_date.isoformat(),
                "open": p.open,
                "high": p.high,
                "low": p.low,
                "close": p.close,
                "volume": p.volume,
                "turnover": p.turnover,
                "confidence": p.confidence,
                "sources_agreeing": [s.value for s in p.sources_agreeing],
                "sources_present": [s.value for s in p.sources_present],
                "disputed_fields": list(p.disputed_fields),
                "is_trustworthy": p.is_trustworthy,
            }
            for p in prices[:200]
        ],
    }


def _job_run_daily(ctx: JobContext) -> dict[str, Any]:
    """ingest -> reconcile -> full analytics, optionally the advisor.

    Mirrors the ``run-daily`` CLI command. The markdown sections come back in
    the result so the dashboard can render the whole report in-page; nothing is
    written to disk unless the caller asks for a report path.
    """
    bd = ctx.param_date("business_date") or date.today()
    if not is_trading_day(bd) and not ctx.params.get("force"):
        reason = f"{bd.isoformat()} is not a NEPSE trading day"
        ctx.log_line(f"skipping — {reason}")
        ctx.skip_remaining(reason)
        return {"skipped": True, "reason": reason, "business_date": bd.isoformat()}

    strategies = ctx.strategy_list()
    top = int(ctx.params.get("top", 25))
    rank_by = str(ctx.params.get("rank_by", "sharpe"))
    cash = float(ctx.params.get("cash", 100_000.0))
    all_sources = bool(ctx.params.get("all_sources", True))
    pipe = ctx.pipeline(include_all_sources=all_sources)

    with ctx.stage("ingest") as stage:
        stage.detail = f"{len(pipe.clients)} source(s)"
        ctx.log_line(f"ingesting from {len(pipe.clients)} source(s) for {bd.isoformat()}")
        ingest_report = pipe.ingest(bd)
        stage.detail = f"{ingest_report.total_bars} bars from {len(ingest_report.per_source)} source(s)"
        for name, count in ingest_report.per_source.items():
            ctx.log_line(f"  {name}: {count} bars")
        if ingest_report.errors:
            ctx.log_line(f"sources with errors: {', '.join(ingest_report.errors)}")

    with ctx.stage("reconcile") as stage:
        prices = pipe.reconcile(bd)
        stage.detail = f"{len(prices)} symbols"
        ctx.log_line(f"reconciled {len(prices)} symbols")

    with ctx.stage("analyse") as stage:
        stage.detail = "loading history"
        ctx.log_line(f"analysing top {top} symbols across {len(strategies)} strategies")
        sections, summary = pipe.daily_report(
            bd,
            strategies=strategies,
            top=top,
            rank_by=rank_by,
            paper_cash=cash,
            on_progress=ctx.progress,
        )
        stage.detail = f"{summary['backtests']} backtests, {summary['actionable_signals']} actionable"
        ctx.log_line(
            f"{summary['actionable_signals']} actionable signal(s), "
            f"{summary['backtests']} backtest(s)"
        )

    report_path = ctx.params.get("report")
    if report_path:
        from nepse_trader.reporting import write_markdown_report

        write_markdown_report(str(report_path), sections)
        ctx.log_line(f"report written to {report_path}")

    return {
        "business_date": bd.isoformat(),
        "summary": summary,
        "ingest": ingest_report.as_dict(),
        "reconciled": len(prices),
        "sections": sections,
        "report_path": str(report_path) if report_path else None,
    }


def _job_rag_index(ctx: JobContext) -> dict[str, Any]:
    from nepse_trader.rag import build_corpus, index_documents

    pipe = ctx.pipeline()
    raw = (ctx.params.get("symbols") or "").strip()
    symbols = [s.strip().upper() for s in raw.split(",") if s.strip()] or None
    recent_days = int(ctx.params.get("recent_days", 10))
    strategies = ctx.strategy_list()
    target = symbols or pipe.storage.symbols()
    if not target:
        raise ValueError("No symbols in the database yet — ingest and reconcile first.")

    with ctx.stage("index") as stage:
        stage.total = len(target)
        ctx.log_line(f"indexing {len(target)} symbol(s)")
        report = build_corpus(
            pipe,
            symbols=symbols,
            recent_days=recent_days,
            strategies=strategies,
            on_progress=ctx.progress,
        )
        stage.detail = f"{report.documents} documents across {report.symbols} symbol(s)"
        ctx.log_line(f"indexed {report.documents} document(s)")
        if not report.uses_fts:
            ctx.log_line("this SQLite build has no FTS5 — search uses the LIKE fallback")
        for key, err in list(report.errors.items())[:10]:
            ctx.log_line(f"  problem {key}: {err}")

    news_written = 0
    if ctx.params.get("news"):
        with ctx.stage("news") as stage:
            from nepse_trader.ingest.news import NewsClient

            ctx.log_line("fetching news and announcements (network)")
            docs = NewsClient().fetch_all(set(pipe.storage.symbols()))
            news_written = index_documents(pipe.storage, docs)
            stage.detail = f"{news_written} documents"
            ctx.log_line(f"indexed {news_written} news/announcement document(s)")
    else:
        ctx.skip_remaining("news not requested")

    return {
        "documents": report.documents,
        "symbols": report.symbols,
        "per_kind": report.per_kind,
        "uses_fts": report.uses_fts,
        "errors": dict(list(report.errors.items())[:20]),
        "news_documents": news_written,
    }


def _job_screen(ctx: JobContext) -> dict[str, Any]:
    pipe = ctx.pipeline()
    strategies = ctx.strategy_list()
    cash = float(ctx.params.get("cash", 100_000.0))
    min_bars = int(ctx.params.get("min_bars", 60))
    rank_by = str(ctx.params.get("rank_by", "sharpe"))
    top = int(ctx.params.get("top", 30))
    symbols = pipe.storage.symbols()
    if not symbols:
        raise ValueError("No symbols in the database yet — ingest and reconcile first.")

    with ctx.stage("screen") as stage:
        stage.total = len(symbols)
        ctx.log_line(f"screening {len(symbols)} symbols x {len(strategies)} strategies")
        rows = pipe.screen_strategies(
            symbols,
            strategies,
            cash=cash,
            min_bars=min_bars,
            rank_by=rank_by,
            on_progress=ctx.progress,
        )
        stage.detail = f"{len(rows)} results"
        ctx.log_line(f"{len(rows)} backtest result(s)")

    return {
        "rank_by": rank_by,
        "count": len(rows),
        "rows": [r.as_dict() for r in rows[:top]],
    }


HANDLERS: dict[str, Handler] = {
    "ingest": _job_ingest,
    "reconcile": _job_reconcile,
    "run-daily": _job_run_daily,
    "rag-index": _job_rag_index,
    "screen": _job_screen,
}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
class JobRegistry:
    """In-memory job store that runs at most one job at a time."""

    def __init__(self, *, max_history: int = MAX_HISTORY) -> None:
        self._jobs: OrderedDict[str, Job] = OrderedDict()
        self._lock = threading.RLock()
        self._running: str | None = None
        self._max_history = max_history
        self._threads: dict[str, threading.Thread] = {}

    # ------------------------------------------------------------ queries
    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def snapshot(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.as_dict() if job else None

    def listing(self, limit: int = 20) -> list[dict[str, Any]]:
        """Newest first, without log bodies — this is the index, not the detail."""
        with self._lock:
            jobs = list(self._jobs.values())[-limit:]
            return [j.as_dict(with_log=False) for j in reversed(jobs)]

    def running_id(self) -> str | None:
        with self._lock:
            return self._running

    # ------------------------------------------------------------- submit
    def submit(self, kind: str, params: dict[str, Any], settings: Settings) -> Job:
        """Start *kind* in a worker thread and return its job immediately.

        Raises :class:`JobBusy` when something is already running and
        :class:`KeyError` for an unknown kind.
        """
        if kind not in HANDLERS:
            raise KeyError(kind)
        with self._lock:
            if self._running is not None:
                running = self._jobs[self._running]
                raise JobBusy(running.id, running.kind)
            job = Job(
                id=uuid.uuid4().hex[:12],
                kind=kind,
                params=dict(params),
                stages=[JobStage(name=n, label=lbl) for n, lbl in JOB_STAGES[kind]],
            )
            self._jobs[job.id] = job
            self._running = job.id
            self._trim()
        thread = threading.Thread(
            target=self._run,
            args=(job, settings),
            name=f"nepse-job-{job.kind}-{job.id}",
            daemon=True,
        )
        self._threads[job.id] = thread
        thread.start()
        return job

    def cancel(self, job_id: str) -> Job | None:
        """Ask a job to stop. Returns the job, or None when the id is unknown.

        Cancelling an already-finished job is a no-op rather than an error: the
        UI cannot know the job finished between its last poll and the click.
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if not job.terminal:
                job.cancel_event.set()
                job.log.append(f"{_now()[11:19]}  cancellation requested")
            return job

    def join(self, job_id: str, timeout: float = 30.0) -> None:
        """Block until a job's thread exits. For tests and shutdown, not routes."""
        thread = self._threads.get(job_id)
        if thread is not None:
            thread.join(timeout)

    def reset(self) -> None:
        """Drop all history. Used between tests so registries never leak state."""
        with self._lock:
            self._jobs.clear()
            self._running = None
            self._threads.clear()

    # ------------------------------------------------------------ internal
    def _trim(self) -> None:
        while len(self._jobs) > self._max_history:
            for job_id, job in list(self._jobs.items()):
                if job.terminal:
                    del self._jobs[job_id]
                    self._threads.pop(job_id, None)
                    break
            else:  # pragma: no cover — every job non-terminal is impossible
                break

    def _run(self, job: Job, settings: Settings) -> None:
        with self._lock:
            job.status = "running"
            job.started_at = _now()
        storage = Storage(settings.db_path)
        ctx = JobContext(job, storage, settings, self._lock)
        try:
            result = HANDLERS[job.kind](ctx)
            with self._lock:
                job.result = result
                job.status = "done"
        except JobCancelled:
            with self._lock:
                job.status = "cancelled"
                job.error = "cancelled by operator"
            ctx.log_line("cancelled")
        except Exception as exc:  # noqa: BLE001 — a job must never kill the server
            detail = str(exc) or exc.__class__.__name__
            with self._lock:
                job.status = "failed"
                job.error = detail
            ctx.log_line(f"failed: {detail}")
            log.warning(
                "job %s (%s) failed: %s\n%s",
                job.id,
                job.kind,
                detail,
                traceback.format_exc(),
            )
        finally:
            storage.close()
            with self._lock:
                job.finished_at = _now()
                if self._running == job.id:
                    self._running = None


#: Process-wide registry. The API module reaches for this directly; there is one
#: server and one database, so a second registry would only be able to violate
#: the one-job-at-a-time rule.
registry = JobRegistry()
