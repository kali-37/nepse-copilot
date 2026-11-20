"""The background job engine and the operations endpoints it drives.

Two halves. The first exercises :mod:`nepse_trader.web.jobs` directly with
handlers registered for the duration of a test, so the concurrency contract —
one job at a time, cooperative cancel, a failing handler that never kills the
server — is tested without waiting on real ingestion. The second drives the new
routes through ``TestClient``.

Nothing here reaches the network. The job kinds that would (``ingest``,
``rag-index --news``) are never submitted; the registry is tested with stub
handlers instead, and the real handlers are covered by the pipeline tests.
"""

from __future__ import annotations

import threading
import time
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from nepse_trader.config import Settings
from nepse_trader.models import PriceBar, ReconciledPrice, SourceName
from nepse_trader.storage import Storage
from nepse_trader.web import jobs as jobs_mod
from nepse_trader.web.api import app
from nepse_trader.web.jobs import (
    HANDLERS,
    JOB_STAGES,
    JobBusy,
    JobRegistry,
)

_BAR_COUNT = 80


def _bars(symbol: str = "NABIL") -> list[PriceBar]:
    out: list[PriceBar] = []
    for i in range(_BAR_COUNT):
        close = 100.0 + (i % 17) * 1.5
        out.append(
            PriceBar(
                symbol=symbol,
                business_date=date(2026, 1, 1) + timedelta(days=i),
                open=close - 1,
                high=close + 2,
                low=close - 2,
                close=close,
                previous_close=close - 1,
                volume=1000 + i,
                turnover=float(close * 1000),
                source=SourceName.SHARESANSAR,
                fetched_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
            )
        )
    return out


def _reconciled(symbol: str = "NABIL") -> list[ReconciledPrice]:
    return [
        ReconciledPrice(
            symbol=b.symbol,
            business_date=b.business_date,
            open=b.open,
            high=b.high,
            low=b.low,
            close=b.close,
            previous_close=b.previous_close,
            volume=b.volume,
            turnover=b.turnover,
            sources_agreeing=[SourceName.SHARESANSAR],
            sources_present=[SourceName.SHARESANSAR],
            disputed_fields=[],
            confidence=1.0,
        )
        for b in _bars(symbol)
    ]


@pytest.fixture
def seeded(tmp_path):
    """A temp database with one symbol's history, plus matching Settings."""
    db = tmp_path / "ops.db"
    storage = Storage(db)
    storage.upsert_price_bars(_bars())
    storage.upsert_reconciled(_reconciled())
    settings = Settings(_env_file=None, db_path=db)
    yield storage, settings
    storage.close()


@pytest.fixture
def client(seeded):
    """A TestClient over the seeded database, with a clean job registry."""
    storage, settings = seeded
    from nepse_trader.web.api import _state

    _state["storage"] = storage
    _state["settings"] = settings
    jobs_mod.registry.reset()
    with TestClient(app) as c:
        yield c
    jobs_mod.registry.reset()
    _state.clear()


@pytest.fixture
def stub_handlers():
    """Register throwaway job kinds, and remove them again afterwards.

    Editing the module-level ``HANDLERS``/``JOB_STAGES`` is deliberate: it is how
    the registry discovers work, so registering a stub is the only way to test
    the registry rather than the pipeline.
    """
    added: list[str] = []

    def register(kind: str, stages: list[tuple[str, str]], handler) -> None:
        JOB_STAGES[kind] = stages
        HANDLERS[kind] = handler
        added.append(kind)

    yield register
    for kind in added:
        JOB_STAGES.pop(kind, None)
        HANDLERS.pop(kind, None)


# ---------------------------------------------------------------------------
# JobRegistry
# ---------------------------------------------------------------------------
class TestJobRegistry:
    def test_a_job_runs_to_completion_and_keeps_its_result(self, seeded, stub_handlers):
        _, settings = seeded

        def handler(ctx):
            with ctx.stage("only") as stage:
                stage.detail = "working"
                ctx.log_line("hello from the worker")
            return {"answer": 42}

        stub_handlers("t-ok", [("only", "The only step")], handler)
        registry = JobRegistry()
        job = registry.submit("t-ok", {}, settings)
        registry.join(job.id)

        snapshot = registry.snapshot(job.id)
        assert snapshot["status"] == "done"
        assert snapshot["result"] == {"answer": 42}
        assert snapshot["stages"][0]["status"] == "ok"
        assert snapshot["stages"][0]["detail"] == "working"
        assert snapshot["error"] is None
        assert snapshot["finished_at"] is not None
        assert any("hello from the worker" in line for line in snapshot["log"])

    def test_the_job_owns_a_different_connection_than_the_request_path(
        self, seeded, stub_handlers
    ):
        """A worker must never share the request-path Storage."""
        shared, settings = seeded
        seen: dict[str, object] = {}

        def handler(ctx):
            with ctx.stage("only"):
                seen["storage"] = ctx.storage
                seen["symbols"] = ctx.storage.symbols()
            return {}

        stub_handlers("t-conn", [("only", "Look at storage")], handler)
        registry = JobRegistry()
        job = registry.submit("t-conn", {}, settings)
        registry.join(job.id)

        assert registry.snapshot(job.id)["status"] == "done"
        assert seen["storage"] is not shared
        # ...and it still sees the same data, because it is the same file.
        assert seen["symbols"] == ["NABIL"]

    def test_a_second_submit_is_refused_with_the_running_id(self, seeded, stub_handlers):
        _, settings = seeded
        release = threading.Event()

        def handler(ctx):
            with ctx.stage("only"):
                release.wait(5)
            return {}

        stub_handlers("t-busy", [("only", "Wait")], handler)
        registry = JobRegistry()
        first = registry.submit("t-busy", {}, settings)
        try:
            with pytest.raises(JobBusy) as exc:
                registry.submit("t-busy", {}, settings)
            assert exc.value.job_id == first.id
            assert exc.value.kind == "t-busy"
        finally:
            release.set()
            registry.join(first.id)
        # The slot frees up once the job finishes.
        assert registry.running_id() is None

    def test_cancel_stops_at_the_next_progress_checkpoint(self, seeded, stub_handlers):
        _, settings = seeded
        started = threading.Event()

        def handler(ctx):
            with ctx.stage("only"):
                started.set()
                for i in range(2000):
                    ctx.progress(i, 2000, f"item {i}")
                    time.sleep(0.002)
            return {"finished": True}

        stub_handlers("t-cancel", [("only", "Long loop")], handler)
        registry = JobRegistry()
        job = registry.submit("t-cancel", {}, settings)
        assert started.wait(5)
        registry.cancel(job.id)
        registry.join(job.id)

        snapshot = registry.snapshot(job.id)
        assert snapshot["status"] == "cancelled"
        assert snapshot["error"] == "cancelled by operator"
        assert snapshot["result"] is None
        # Cancelling is not a stage failure — nothing went wrong with the work.
        assert snapshot["stages"][0]["status"] == "skipped"
        assert snapshot["cancel_requested"] is True

    def test_cancelling_between_stages_leaves_the_next_one_untouched(
        self, seeded, stub_handlers
    ):
        """Entering a stage checks for cancellation, so later work never starts."""
        _, settings = seeded
        first_done = threading.Event()
        proceed = threading.Event()

        def handler(ctx):
            with ctx.stage("a"):
                first_done.set()
                proceed.wait(5)
            with ctx.stage("b"):  # never entered
                raise AssertionError("stage b should not have run")

        stub_handlers("t-between", [("a", "First"), ("b", "Second")], handler)
        registry = JobRegistry()
        job = registry.submit("t-between", {}, settings)
        assert first_done.wait(5)
        registry.cancel(job.id)
        proceed.set()
        registry.join(job.id)

        snapshot = registry.snapshot(job.id)
        assert snapshot["status"] == "cancelled"
        # The first stage finished cleanly before the cancel landed.
        assert snapshot["stages"][0]["status"] == "ok"
        assert snapshot["stages"][1]["status"] == "pending"

    def test_cancelling_an_unknown_job_returns_none(self):
        assert JobRegistry().cancel("nope") is None

    def test_cancelling_a_finished_job_is_a_no_op(self, seeded, stub_handlers):
        _, settings = seeded
        stub_handlers("t-quick", [("only", "Quick")], lambda ctx: {})
        registry = JobRegistry()
        job = registry.submit("t-quick", {}, settings)
        registry.join(job.id)

        again = registry.cancel(job.id)
        assert again is not None
        assert again.status == "done"
        assert again.cancel_event.is_set() is False

    def test_a_raising_handler_fails_the_job_without_killing_the_server(
        self, seeded, stub_handlers
    ):
        _, settings = seeded

        def handler(ctx):
            with ctx.stage("only"):
                raise ValueError("no symbols in the database yet")

        stub_handlers("t-boom", [("only", "Explode")], handler)
        registry = JobRegistry()
        job = registry.submit("t-boom", {}, settings)
        registry.join(job.id)

        snapshot = registry.snapshot(job.id)
        assert snapshot["status"] == "failed"
        assert snapshot["error"] == "no symbols in the database yet"
        assert snapshot["stages"][0]["status"] == "failed"
        assert snapshot["stages"][0]["detail"] == "no symbols in the database yet"
        # The slot is released, so the operator can try again.
        assert registry.running_id() is None

    def test_an_exception_with_no_message_still_reports_something(
        self, seeded, stub_handlers
    ):
        _, settings = seeded

        def handler(ctx):
            raise RuntimeError

        stub_handlers("t-silent", [("only", "Silent")], handler)
        registry = JobRegistry()
        job = registry.submit("t-silent", {}, settings)
        registry.join(job.id)
        assert registry.snapshot(job.id)["error"] == "RuntimeError"

    def test_skip_remaining_marks_untouched_stages(self, seeded, stub_handlers):
        _, settings = seeded

        def handler(ctx):
            ctx.skip_remaining("not a trading day")
            return {"skipped": True}

        stub_handlers(
            "t-skip", [("a", "First"), ("b", "Second")], handler
        )
        registry = JobRegistry()
        job = registry.submit("t-skip", {}, settings)
        registry.join(job.id)

        snapshot = registry.snapshot(job.id)
        assert snapshot["status"] == "done"
        assert [s["status"] for s in snapshot["stages"]] == ["skipped", "skipped"]
        assert snapshot["stages"][0]["detail"] == "not a trading day"

    def test_unknown_kind_is_a_key_error(self, seeded):
        _, settings = seeded
        with pytest.raises(KeyError):
            JobRegistry().submit("does-not-exist", {}, settings)

    def test_the_log_is_a_bounded_ring_buffer(self, seeded, stub_handlers):
        _, settings = seeded
        overshoot = jobs_mod.MAX_LOG_LINES + 50

        def handler(ctx):
            with ctx.stage("only"):
                for i in range(overshoot):
                    ctx.log_line(f"line {i}")
            return {}

        stub_handlers("t-log", [("only", "Chatty")], handler)
        registry = JobRegistry()
        job = registry.submit("t-log", {}, settings)
        registry.join(job.id)

        lines = registry.snapshot(job.id)["log"]
        assert len(lines) == jobs_mod.MAX_LOG_LINES
        # The tail survives; the head is what gets dropped.
        assert f"line {overshoot - 1}" in lines[-1]
        assert not any("line 0" in line for line in lines)

    def test_history_is_trimmed_oldest_terminal_first(self, seeded, stub_handlers):
        _, settings = seeded
        stub_handlers("t-hist", [("only", "Quick")], lambda ctx: {})
        registry = JobRegistry(max_history=3)
        ids = []
        for _ in range(6):
            job = registry.submit("t-hist", {}, settings)
            registry.join(job.id)
            ids.append(job.id)

        listing = registry.listing(50)
        assert len(listing) <= 3
        kept = {row["id"] for row in listing}
        assert ids[-1] in kept
        assert ids[0] not in kept

    def test_listing_is_newest_first_and_omits_log_bodies(self, seeded, stub_handlers):
        _, settings = seeded

        def handler(ctx):
            ctx.log_line("something happened")
            return {}

        stub_handlers("t-list", [("only", "Quick")], handler)
        registry = JobRegistry()
        first = registry.submit("t-list", {}, settings)
        registry.join(first.id)
        second = registry.submit("t-list", {}, settings)
        registry.join(second.id)

        listing = registry.listing(10)
        assert [row["id"] for row in listing] == [second.id, first.id]
        assert "log" not in listing[0]
        # The detail view still has it.
        assert registry.snapshot(first.id)["log"]

    def test_strategy_list_parses_all_and_rejects_nonsense(self, seeded, stub_handlers):
        _, settings = seeded
        from nepse_trader.analysis.strategies import STRATEGIES

        captured: dict[str, object] = {}

        def handler(ctx):
            captured["all"] = ctx.strategy_list()
            captured["subset"] = ctx.strategy_list("subset")
            try:
                ctx.strategy_list("bogus")
            except ValueError as exc:
                captured["error"] = str(exc)
            return {}

        stub_handlers("t-strat", [("only", "Parse")], handler)
        registry = JobRegistry()
        job = registry.submit(
            "t-strat",
            {"strategies": "all", "subset": "rsi,macd", "bogus": "nope"},
            settings,
        )
        registry.join(job.id)

        assert registry.snapshot(job.id)["status"] == "done"
        assert captured["all"] == list(STRATEGIES)
        assert captured["subset"] == ["rsi", "macd"]
        assert "nope" in captured["error"]


# ---------------------------------------------------------------------------
# Real handlers, over local data only
# ---------------------------------------------------------------------------
class TestRealHandlers:
    def test_reconcile_runs_and_reports_rows(self, seeded):
        storage, settings = seeded
        registry = JobRegistry()
        job = registry.submit(
            "reconcile", {"business_date": "2026-01-05"}, settings
        )
        registry.join(job.id, timeout=60)

        snapshot = registry.snapshot(job.id)
        assert snapshot["status"] == "done", snapshot["error"]
        assert snapshot["stages"][0]["status"] == "ok"
        assert snapshot["result"]["business_date"] == "2026-01-05"
        row = snapshot["result"]["rows"][0]
        assert row["symbol"] == "NABIL"
        # Serialized from the enum lists, not from a field that does not exist.
        assert row["sources_agreeing"] == ["sharesansar"]

    def test_screen_backtests_every_strategy(self, seeded):
        _, settings = seeded
        registry = JobRegistry()
        job = registry.submit("screen", {"strategies": "rsi", "min_bars": 20}, settings)
        registry.join(job.id, timeout=120)

        snapshot = registry.snapshot(job.id)
        assert snapshot["status"] == "done", snapshot["error"]
        assert snapshot["result"]["rank_by"] == "sharpe"
        stage = snapshot["stages"][0]
        assert stage["total"] == 1  # one symbol seeded
        assert stage["status"] == "ok"

    def test_run_daily_skips_a_non_trading_day_without_running_anything(self, seeded):
        """A Saturday must not reach the network. Every stage is skipped."""
        _, settings = seeded
        registry = JobRegistry()
        # 2026-01-03 is a Saturday.
        job = registry.submit("run-daily", {"business_date": "2026-01-03"}, settings)
        registry.join(job.id, timeout=60)

        snapshot = registry.snapshot(job.id)
        assert snapshot["status"] == "done"
        assert snapshot["result"]["skipped"] is True
        assert "not a NEPSE trading day" in snapshot["result"]["reason"]
        assert [s["status"] for s in snapshot["stages"]] == ["skipped"] * 3

    def test_rag_index_fails_cleanly_on_an_empty_database(self, tmp_path):
        db = tmp_path / "empty.db"
        storage = Storage(db)
        settings = Settings(_env_file=None, db_path=db)
        registry = JobRegistry()
        job = registry.submit("rag-index", {}, settings)
        registry.join(job.id, timeout=60)

        snapshot = registry.snapshot(job.id)
        assert snapshot["status"] == "failed"
        assert "ingest and reconcile first" in snapshot["error"]
        storage.close()


# ---------------------------------------------------------------------------
# POST/GET /api/jobs
# ---------------------------------------------------------------------------
class TestJobRoutes:
    def test_submit_returns_the_job_before_work_happens(self, client):
        res = client.post(
            "/api/jobs", json={"kind": "reconcile", "params": {"business_date": "2026-01-05"}}
        )
        assert res.status_code == 200
        body = res.json()
        assert body["kind"] == "reconcile"
        assert body["status"] in ("queued", "running", "done")
        assert [s["name"] for s in body["stages"]] == ["reconcile"]
        assert body["cancel_requested"] is False
        jobs_mod.registry.join(body["id"], timeout=60)

    def test_polling_a_job_reaches_a_terminal_state(self, client):
        job_id = client.post(
            "/api/jobs", json={"kind": "reconcile", "params": {"business_date": "2026-01-05"}}
        ).json()["id"]
        jobs_mod.registry.join(job_id, timeout=60)

        body = client.get(f"/api/jobs/{job_id}").json()
        assert body["status"] == "done", body["error"]
        assert body["finished_at"] is not None
        assert isinstance(body["log"], list)

    def test_listing_reports_the_running_job_and_the_known_kinds(self, client):
        job_id = client.post(
            "/api/jobs", json={"kind": "reconcile", "params": {"business_date": "2026-01-05"}}
        ).json()["id"]
        jobs_mod.registry.join(job_id, timeout=60)

        body = client.get("/api/jobs?limit=5").json()
        assert body["running"] is None
        assert body["kinds"] == [
            "backfill",
            "floorsheet",
            "fundamentals",
            "ingest",
            "rag-index",
            "reconcile",
            "refresh-today",
            "run-daily",
            "screen",
        ]
        assert body["jobs"][0]["id"] == job_id
        assert "log" not in body["jobs"][0]

    def test_a_second_submit_while_busy_is_a_409_pointing_at_the_first(self, client, seeded):
        _, settings = seeded
        release = threading.Event()

        def handler(ctx):
            with ctx.stage("only"):
                release.wait(5)
            return {}

        JOB_STAGES["t-http-busy"] = [("only", "Wait")]
        HANDLERS["t-http-busy"] = handler
        first = None
        try:
            first = jobs_mod.registry.submit("t-http-busy", {}, settings)
            res = client.post("/api/jobs", json={"kind": "reconcile", "params": {}})
            assert res.status_code == 409
            detail = res.json()["detail"]
            assert detail["running_job_id"] == first.id
            assert "already running" in detail["message"]
        finally:
            release.set()
            if first is not None:
                jobs_mod.registry.join(first.id)
            JOB_STAGES.pop("t-http-busy", None)
            HANDLERS.pop("t-http-busy", None)

    def test_an_unknown_kind_is_rejected_by_the_schema(self, client):
        """The route only accepts the five real kinds, so a typo never reaches the registry."""
        res = client.post("/api/jobs", json={"kind": "rm -rf", "params": {}})
        assert res.status_code == 422

    def test_unknown_job_id_is_404_on_read_and_on_cancel(self, client):
        assert client.get("/api/jobs/deadbeef").status_code == 404
        assert client.post("/api/jobs/deadbeef/cancel").status_code == 404

    def test_cancel_stops_the_job_and_the_next_poll_says_so(self, client, seeded):
        """Cancel is driven over HTTP; the work is a stub so the test stays fast.

        The kind is submitted through the registry rather than the route because
        the route's schema only accepts the five real kinds.
        """
        _, settings = seeded
        started = threading.Event()

        def handler(ctx):
            with ctx.stage("only"):
                started.set()
                for i in range(2000):
                    ctx.progress(i, 2000)
                    time.sleep(0.002)
            return {}

        JOB_STAGES["t-http-cancel"] = [("only", "Wait")]
        HANDLERS["t-http-cancel"] = handler
        try:
            job_id = jobs_mod.registry.submit("t-http-cancel", {}, settings).id
            assert started.wait(5)
            assert client.get("/api/jobs").json()["running"] == job_id

            body = client.post(f"/api/jobs/{job_id}/cancel").json()
            assert body["cancel_requested"] is True

            jobs_mod.registry.join(job_id)
            assert client.get(f"/api/jobs/{job_id}").json()["status"] == "cancelled"
        finally:
            JOB_STAGES.pop("t-http-cancel", None)
            HANDLERS.pop("t-http-cancel", None)


# ---------------------------------------------------------------------------
# GET /api/sources, /api/strategies
# ---------------------------------------------------------------------------
class TestInventoryRoutes:
    def test_sources_lists_every_configured_source(self, client):
        body = client.get("/api/sources").json()
        assert isinstance(body["enabled_in_settings"], list)
        assert body["sources"], "sources.yaml should configure at least one source"
        first = body["sources"][0]
        assert {"name", "enabled", "base_url", "access_method", "endpoints"} <= set(first)

    def test_strategies_matches_the_registry(self, client):
        from nepse_trader.analysis.strategies import STRATEGIES

        assert client.get("/api/strategies").json() == {"strategies": sorted(STRATEGIES)}


# ---------------------------------------------------------------------------
# GET /api/tables — the in-page answer to `export csv`
# ---------------------------------------------------------------------------
class TestTableBrowser:
    def test_listing_reports_row_counts(self, client):
        tables = client.get("/api/tables").json()["tables"]
        by_name = {t["name"]: t["rows"] for t in tables}
        assert by_name["price_bars"] == _BAR_COUNT
        assert by_name["reconciled_prices"] == _BAR_COUNT

    def test_a_page_carries_its_columns_total_and_offset(self, client):
        body = client.get("/api/tables/price_bars?limit=10&offset=5").json()
        assert body["name"] == "price_bars"
        assert body["total"] == _BAR_COUNT
        assert body["limit"] == 10
        assert body["offset"] == 5
        assert len(body["rows"]) == 10
        assert "business_date" in body["columns"]
        assert set(body["rows"][0]) == set(body["columns"])

    def test_paging_is_newest_first_and_does_not_repeat_rows(self, client):
        first = client.get("/api/tables/price_bars?limit=5&offset=0").json()["rows"]
        second = client.get("/api/tables/price_bars?limit=5&offset=5").json()["rows"]
        dates = [r["business_date"] for r in first]
        assert dates == sorted(dates, reverse=True)
        assert not set(r["business_date"] for r in first) & set(
            r["business_date"] for r in second
        )

    def test_an_unknown_table_is_404_and_never_reaches_sql(self, client):
        res = client.get("/api/tables/sqlite_master")
        assert res.status_code == 404
        assert "Unknown table" in res.json()["detail"]

    def test_an_injection_attempt_in_the_name_is_just_an_unknown_table(self, client):
        res = client.get("/api/tables/price_bars;DROP TABLE price_bars")
        assert res.status_code == 404
        # The real table is untouched.
        assert client.get("/api/tables/price_bars").json()["total"] == _BAR_COUNT

    def test_limit_is_capped(self, client):
        assert client.get("/api/tables/price_bars?limit=5000").status_code == 422


# ---------------------------------------------------------------------------
# Corporate actions
# ---------------------------------------------------------------------------
class TestCorporateActions:
    def test_recording_one_returns_a_readable_description(self, client):
        res = client.post(
            "/api/corporate-actions",
            json={
                "symbol": "nabil",
                "ex_date": "2026-02-01",
                "action_type": "bonus",
                "ratio_numerator": 1,
                "ratio_denominator": 10,
                "notes": "AGM decision",
            },
        )
        assert res.status_code == 200
        body = res.json()
        assert body["symbol"] == "NABIL"  # normalized
        assert body["action_type"] == "bonus"
        assert body["source"] == "manual"
        assert body["description"]
        assert body["notes"] == "AGM decision"

    def test_it_comes_back_from_the_list_and_filters_by_symbol(self, client):
        client.post(
            "/api/corporate-actions",
            json={
                "symbol": "NABIL",
                "ex_date": "2026-02-01",
                "action_type": "split",
                "ratio_numerator": 1,
                "ratio_denominator": 2,
            },
        )
        assert len(client.get("/api/corporate-actions").json()) == 1
        assert client.get("/api/corporate-actions?symbol=NABIL").json()[0]["symbol"] == "NABIL"
        assert client.get("/api/corporate-actions?symbol=ADBL").json() == []

    def test_a_bad_date_is_a_400_not_a_500(self, client):
        res = client.post(
            "/api/corporate-actions",
            json={
                "symbol": "NABIL",
                "ex_date": "01/02/2026",
                "action_type": "bonus",
                "ratio_numerator": 1,
                "ratio_denominator": 10,
            },
        )
        assert res.status_code == 400
        assert "YYYY-MM-DD" in res.json()["detail"]

    def test_an_unknown_action_type_is_rejected_by_the_schema(self, client):
        res = client.post(
            "/api/corporate-actions",
            json={
                "symbol": "NABIL",
                "ex_date": "2026-02-01",
                "action_type": "merger",
                "ratio_numerator": 1,
                "ratio_denominator": 2,
            },
        )
        assert res.status_code == 422

    def test_a_zero_ratio_is_rejected_before_a_division(self, client):
        res = client.post(
            "/api/corporate-actions",
            json={
                "symbol": "NABIL",
                "ex_date": "2026-02-01",
                "action_type": "bonus",
                "ratio_numerator": 0,
                "ratio_denominator": 10,
            },
        )
        assert res.status_code == 422


# ---------------------------------------------------------------------------
# Paper trades
# ---------------------------------------------------------------------------
class TestPaperTrades:
    def test_a_buy_applies_every_nepal_cost(self, client):
        res = client.post(
            "/api/paper/trades",
            json={
                "symbol": "nabil",
                "side": "buy",
                "price": 100.0,
                "quantity": 50,
                "business_date": "2026-02-02",
            },
        )
        assert res.status_code == 200
        trade = res.json()["trade"]
        assert trade["symbol"] == "NABIL"
        # The side comes back upper-cased, which the UI must not compare literally.
        assert trade["side"] == "BUY"
        assert trade["gross_amount"] == 5000.0
        assert trade["broker_commission"] > 0
        assert trade["sebon_fee"] > 0
        assert trade["dp_charge"] > 0
        # A buy costs more than the gross; there is no CGT on a purchase.
        assert trade["net_amount"] > trade["gross_amount"]
        assert trade["cgt"] == 0

    def test_the_portfolio_comes_back_with_the_fill(self, client):
        body = client.post(
            "/api/paper/trades",
            json={"symbol": "NABIL", "side": "buy", "price": 100.0, "quantity": 10},
        ).json()
        position = body["portfolio"]["positions"][0]
        assert position["symbol"] == "NABIL"
        assert position["quantity"] == 10
        assert body["portfolio"]["cash"] < body["portfolio"]["initial_cash"]

    def test_selling_more_than_is_held_is_a_400_with_the_reason(self, client):
        client.post(
            "/api/paper/trades",
            json={"symbol": "NABIL", "side": "buy", "price": 100.0, "quantity": 10},
        )
        res = client.post(
            "/api/paper/trades",
            json={"symbol": "NABIL", "side": "sell", "price": 110.0, "quantity": 999},
        )
        assert res.status_code == 400
        assert "only 10 held" in res.json()["detail"]

    def test_trades_are_persisted_and_listed_newest_first(self, client):
        for day, qty in (("2026-02-02", 10), ("2026-02-03", 5)):
            client.post(
                "/api/paper/trades",
                json={
                    "symbol": "NABIL",
                    "side": "buy",
                    "price": 100.0,
                    "quantity": qty,
                    "business_date": day,
                },
            )
        rows = client.get("/api/paper/trades").json()
        assert len(rows) == 2
        assert rows[0]["business_date"] == "2026-02-03"
        assert {"trade_id", "net_amount", "broker_commission"} <= set(rows[0])

    def test_a_bad_business_date_is_a_400(self, client):
        res = client.post(
            "/api/paper/trades",
            json={
                "symbol": "NABIL",
                "side": "buy",
                "price": 100.0,
                "quantity": 1,
                "business_date": "tomorrow",
            },
        )
        assert res.status_code == 400
        assert "YYYY-MM-DD" in res.json()["detail"]

    def test_a_nonpositive_quantity_or_price_is_rejected(self, client):
        for payload in (
            {"symbol": "NABIL", "side": "buy", "price": 0, "quantity": 1},
            {"symbol": "NABIL", "side": "buy", "price": 10, "quantity": 0},
            {"symbol": "NABIL", "side": "hodl", "price": 10, "quantity": 1},
        ):
            assert client.post("/api/paper/trades", json=payload).status_code == 422


# ---------------------------------------------------------------------------
# Bulk analytics
# ---------------------------------------------------------------------------
class TestBulkAnalytics:
    def test_stats_covers_the_stored_symbols(self, client):
        body = client.get("/api/stats?top=5").json()
        assert body["symbols"] == ["NABIL"]
        assert body["periods_per_year"] == 252
        assert body["rows"]

    def test_stats_accepts_an_explicit_symbol_list(self, client):
        body = client.get("/api/stats?symbols=nabil").json()
        assert body["symbols"] == ["NABIL"]

    def test_stats_on_an_empty_database_is_an_empty_answer_not_an_error(self, tmp_path):
        db = tmp_path / "empty.db"
        storage = Storage(db)
        from nepse_trader.web.api import _state

        _state["storage"] = storage
        _state["settings"] = Settings(_env_file=None, db_path=db)
        with TestClient(app) as c:
            assert c.get("/api/stats").json() == {"symbols": [], "rows": []}
        storage.close()
        _state.clear()

    def test_signals_returns_the_latest_row_per_symbol(self, client):
        body = client.get("/api/signals?strategy=rsi").json()
        assert body["strategy"] == "rsi"
        assert body["count"] == len(body["rows"])
        row = body["rows"][0]
        assert row["symbol"] == "NABIL"
        assert row["action"] in ("BUY", "SELL", "HOLD")

    def test_actionable_only_drops_hold_rows(self, client):
        body = client.get("/api/signals?strategy=rsi&actionable_only=true").json()
        assert all(r["action"] in ("BUY", "SELL") for r in body["rows"])

    def test_an_unknown_strategy_is_a_400_that_names_the_options(self, client):
        res = client.get("/api/signals?strategy=astrology")
        assert res.status_code == 400
        assert "sma_cross" in res.json()["detail"]


# ---------------------------------------------------------------------------
# AI status
# ---------------------------------------------------------------------------
class TestAiRoutes:
    def test_models_is_offline_and_reports_usable_legs(self, client):
        body = client.get("/api/ai/models").json()
        assert isinstance(body["tiers"], dict)
        assert isinstance(body["usable_legs"], int)
        assert "budget" in body and "cache" in body
        # With no keys configured nothing is usable, and the UI is told why.
        if body["usable_legs"] == 0:
            assert "degrade to normal mode" in body["banner"]
        else:
            assert body["banner"] is None

    def test_a_chain_that_nobody_answers_is_a_200_with_ok_false(self, client, monkeypatch):
        """A missing third-party key is not a server fault."""
        from nepse_trader.ai.providers import LLMResponse
        from nepse_trader.ai.router import LLMRouter

        monkeypatch.setattr(
            LLMRouter,
            "complete",
            lambda self, *a, **k: LLMResponse(error="no provider configured"),
        )
        res = client.post("/api/ai/test", json={"tier": "synthesis"})
        assert res.status_code == 200
        body = res.json()
        assert body["ok"] is False
        assert body["error"] == "no provider configured"
        assert body["text"] == ""

    def test_a_successful_test_reports_what_answered(self, client, monkeypatch):
        from nepse_trader.ai.providers import LLMResponse
        from nepse_trader.ai.router import LLMRouter

        monkeypatch.setattr(
            LLMRouter,
            "complete",
            lambda self, *a, **k: LLMResponse(
                text="  pong  ",
                provider="stub",
                model="stub-1",
                prompt_tokens=4,
                completion_tokens=3,
            ),
        )
        body = client.post("/api/ai/test", json={"tier": "bulk"}).json()
        assert body["ok"] is True
        assert body["tier"] == "bulk"
        assert body["provider"] == "stub"
        assert body["text"] == "pong"
        assert body["total_tokens"] == 7

    def test_an_unknown_tier_is_rejected_by_the_schema(self, client):
        assert client.post("/api/ai/test", json={"tier": "deep"}).status_code == 422
