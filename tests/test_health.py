"""Health-report tests: every verdict, the guard, and the snapshot history.

Fully offline. Each test builds a temp database through the real ``Storage``
constructor (so all migrations run) and passes a ``Settings`` built with
``_env_file=None`` — otherwise the developer's own ``.env`` would decide whether
MeroShare is enabled and the AI checks would depend on whose machine ran them.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from nepse_trader import health as health_mod
from nepse_trader.config import Settings
from nepse_trader.health import (
    FAIL,
    OFF,
    OK,
    WARN,
    check_ai,
    check_config,
    check_database,
    check_freshness,
    check_ingest,
    check_journal,
    check_meroshare,
    check_paper,
    check_rag,
    check_schema,
    problems,
    record_snapshot,
    snapshot,
    snapshot_history,
    system_health,
)
from nepse_trader.models import PriceBar, ReconciledPrice, SourceName
from nepse_trader.rag.corpus import KIND_NEWS, Document
from nepse_trader.rag.index import DocumentIndex
from nepse_trader.storage import Storage
from nepse_trader.storage.migrations import MIGRATIONS


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


@pytest.fixture
def storage(tmp_path):
    s = Storage(tmp_path / "health.db")
    yield s
    s.close()


def _seed_prices(storage: Storage, *, days: int = 3, end: date | None = None) -> None:
    end = end or date(2026, 6, 10)
    bars, reconciled = [], []
    for offset in range(days):
        business_date = end - timedelta(days=offset)
        bars.append(
            PriceBar(
                symbol="NABIL",
                business_date=business_date,
                open=500.0,
                high=510.0,
                low=495.0,
                close=505.0,
                volume=1_000,
                source=SourceName.SHARESANSAR,
            )
        )
        reconciled.append(
            ReconciledPrice(
                symbol="NABIL",
                business_date=business_date,
                open=500.0,
                high=510.0,
                low=495.0,
                close=505.0,
                volume=1_000,
                turnover=505_000.0,
                sources_agreeing=[SourceName.SHARESANSAR],
                sources_present=[SourceName.SHARESANSAR],
                disputed_fields=[],
                confidence=1.0,
            )
        )
    storage.upsert_price_bars(bars)
    storage.upsert_reconciled(reconciled)


class TestSchema:
    def test_a_fully_migrated_database_passes_and_names_the_latest(self, storage):
        check = check_schema(storage._conn)
        assert check.status == OK
        assert check.metrics["applied"] == len(MIGRATIONS)
        assert check.metrics["latest_expected"] == MIGRATIONS[-1][0]
        assert check.metrics["missing"] == []

    def test_a_missing_migration_fails_and_names_it(self, storage):
        victim = MIGRATIONS[-1][0]
        storage._conn.execute("DELETE FROM schema_version WHERE version=?", (victim,))
        check = check_schema(storage._conn)
        assert check.status == FAIL
        assert victim in check.detail
        assert check.metrics["missing"] == [victim]

    def test_an_unknown_migration_warns_rather_than_fails(self, storage):
        # A newer build wrote this row. Read paths still work, so the report must
        # say "ahead of this build" and not refuse to run.
        storage._conn.execute(
            "INSERT INTO schema_version (version, applied_at) VALUES ('9999_from_the_future', ?)",
            (datetime.now().isoformat(),),
        )
        check = check_schema(storage._conn)
        assert check.status == WARN
        assert check.metrics["unknown"] == ["9999_from_the_future"]

    def test_an_unmigrated_database_fails_instead_of_raising(self, tmp_path):
        import sqlite3

        conn = sqlite3.connect(tmp_path / "bare.db")
        conn.row_factory = sqlite3.Row
        check = check_schema(conn)
        assert check.status == FAIL
        assert "never migrated" in check.detail
        conn.close()


class TestDatabaseAndFreshness:
    def test_empty_database_warns_and_says_what_to_run(self, storage):
        check = check_database(storage)
        assert check.status == WARN
        assert "ingest" in check.detail

    def test_raw_rows_without_reconciliation_point_at_reconcile(self, storage):
        storage.upsert_price_bars(
            [
                PriceBar(
                    symbol="NABIL",
                    business_date=date(2026, 6, 10),
                    close=505.0,
                    source=SourceName.SHARESANSAR,
                )
            ]
        )
        check = check_database(storage)
        assert check.status == WARN
        assert "reconcile" in check.detail

    def test_populated_database_passes_with_counts(self, storage):
        _seed_prices(storage)
        check = check_database(storage)
        assert check.status == OK
        assert check.metrics["symbols"] == 1
        assert check.metrics["reconciled_rows"] == 3

    def test_data_from_the_last_trading_day_is_current(self, storage):
        # 2026-06-11 is a Thursday, itself a trading day, so ``previous_trading_day``
        # returns that same date and data through it is "current".
        _seed_prices(storage, end=date(2026, 6, 11))
        check = check_freshness(storage, today=date(2026, 6, 11))
        assert check.status == OK
        assert check.metrics["trading_days_behind"] == 0

    def test_a_publishing_lag_of_a_few_days_is_still_ok(self, storage):
        _seed_prices(storage, end=date(2026, 6, 9))
        check = check_freshness(storage, today=date(2026, 6, 11))
        assert check.status == OK
        assert 0 < check.metrics["trading_days_behind"] <= health_mod.STALE_AFTER_TRADING_DAYS

    def test_a_long_gap_warns_that_the_daily_job_may_be_dead(self, storage):
        _seed_prices(storage, end=date(2026, 5, 1))
        check = check_freshness(storage, today=date(2026, 6, 11))
        assert check.status == WARN
        assert check.metrics["trading_days_behind"] > health_mod.STALE_AFTER_TRADING_DAYS

    def test_no_prices_at_all_warns(self, storage):
        check = check_freshness(storage, today=date(2026, 6, 11))
        assert check.status == WARN
        assert check.metrics["latest_reconciled_date"] is None


class TestIngest:
    def test_never_run_warns(self, storage):
        assert check_ingest(storage._conn).status == WARN

    def test_a_clean_run_passes(self, storage):
        storage.log_ingest("sharesansar", "prices", date(2026, 6, 10), 250, "ok")
        check = check_ingest(storage._conn)
        assert check.status == OK
        assert check.metrics["errors"] == 0

    def test_a_high_error_rate_warns_and_names_the_source(self, storage):
        storage.log_ingest("sharesansar", "prices", date(2026, 6, 10), 250, "ok")
        for _ in range(3):
            storage.log_ingest("merolagani", "prices", date(2026, 6, 10), 0, "error", "boom")
        check = check_ingest(storage._conn)
        assert check.status == WARN
        assert check.metrics["failing_sources"] == ["merolagani"]

    def test_one_stray_failure_among_many_successes_is_not_a_warning(self, storage):
        for _ in range(9):
            storage.log_ingest("sharesansar", "prices", date(2026, 6, 10), 250, "ok")
        storage.log_ingest("sharesansar", "prices", date(2026, 6, 10), 0, "error", "one blip")
        assert check_ingest(storage._conn).status == OK


class TestConfig:
    def test_the_shipped_config_files_validate(self):
        # This is the regression guard for the schemas themselves: the repo's own
        # holidays.yaml has an all-comments ``ranges:`` key, which parses as null.
        check = check_config(_settings())
        assert check.metrics["schema_errors"] == []
        assert check.status == OK

    def test_no_effective_source_warns(self):
        check = check_config(_settings(enabled_sources=["merolagani"]))
        assert check.status == WARN
        assert check.metrics["effective_sources"] == []


class TestRag:
    def test_an_empty_corpus_warns(self, storage):
        check = check_rag(storage._conn)
        assert check.status == WARN
        assert "rag index" in check.detail

    def test_a_populated_corpus_passes_and_counts_kinds(self, storage):
        DocumentIndex(storage._conn).upsert(
            [
                Document(
                    doc_id="news-1",
                    kind=KIND_NEWS,
                    symbol="NABIL",
                    business_date=date(2026, 6, 10),
                    title="Dividend declared",
                    body="The board declared a cash dividend.",
                    source="test",
                )
            ]
        )
        check = check_rag(storage._conn)
        assert check.status == OK
        assert check.metrics["documents"] == 1
        assert check.metrics["per_kind"] == {KIND_NEWS: 1}


class TestAi:
    def test_normal_mode_reports_off_and_never_builds_a_provider(self, storage):
        check = check_ai(storage._conn, _settings(analysis_mode="normal"))
        assert check.status == OFF
        assert "normal" in check.detail

    def test_ai_mode_with_no_provider_warns_about_degrading(self, storage):
        check = check_ai(
            storage._conn,
            _settings(
                analysis_mode="ai",
                llm_synthesis_providers=["openrouter"],
                llm_bulk_providers=["openrouter"],
                openrouter_api_key="",
                claude_cli_path="",
            ),
        )
        assert check.status == WARN
        assert "degrade" in check.detail

    def test_ai_mode_offline_is_off_not_a_warning(self, storage):
        # Offline AI mode is a deliberate choice, so it must not read as breakage.
        check = check_ai(
            storage._conn,
            _settings(
                analysis_mode="ai",
                online=False,
                llm_synthesis_providers=["openrouter"],
                llm_bulk_providers=["openrouter"],
                openrouter_api_key="key",
                openrouter_models=["some/model"],
            ),
        )
        assert check.status == OFF

    def test_an_exhausted_budget_warns(self, storage):
        settings = _settings(
            analysis_mode="ai",
            online=True,
            llm_synthesis_providers=["openrouter"],
            llm_bulk_providers=["openrouter"],
            openrouter_api_key="key",
            openrouter_models=["some/model"],
            llm_max_calls_per_day=1,
        )
        from nepse_trader.ai import LLMResponse, TokenBudget

        TokenBudget(storage._conn, settings).record(
            LLMResponse(
                text="hello",
                provider="openrouter",
                model="some/model",
                prompt_tokens=10,
                completion_tokens=10,
            ),
            task="test",
        )
        check = check_ai(storage._conn, settings)
        assert check.status == WARN
        assert "budget" in check.detail


class TestMeroShare:
    def test_disabled_reports_off_and_still_counts_retained_holdings(self, storage):
        check = check_meroshare(storage._conn, _settings(meroshare_enabled=False))
        assert check.status == OFF
        assert check.metrics["toggle_source"] == "env"

    def test_the_database_toggle_overrides_the_environment(self, storage):
        storage._conn.execute(
            "INSERT INTO app_settings (key, value, updated_at) VALUES "
            "('meroshare_enabled', 'true', ?)",
            (datetime.now().isoformat(),),
        )
        storage._conn.commit()
        check = check_meroshare(storage._conn, _settings(meroshare_enabled=False))
        assert check.metrics["enabled"] is True
        assert check.metrics["toggle_source"] == "database"

    def test_enabled_without_credentials_names_only_the_missing_fields(self, storage):
        check = check_meroshare(
            storage._conn,
            _settings(
                meroshare_enabled=True,
                meroshare_dp_id="",
                meroshare_username="",
                meroshare_password="",
            ),
        )
        assert check.status == WARN
        assert set(check.metrics["missing_credentials"]) == {"dp_id", "username", "password"}

    def test_no_credential_value_reaches_the_report(self, storage):
        secret = "correct-horse-battery-staple"
        check = check_meroshare(
            storage._conn,
            _settings(
                meroshare_enabled=True,
                meroshare_dp_id="12300",
                meroshare_username="user",
                meroshare_password=secret,
            ),
        )
        rendered = repr(check.as_dict())
        assert secret not in rendered
        assert "user" not in check.detail

    def test_a_failed_last_sync_warns_but_reports_retained_holdings(self, storage):
        storage._conn.execute(
            "INSERT INTO ms_sync_log (ran_at, method, status, holdings, transactions, error) "
            "VALUES (?, 'api', 'error', 0, 0, 'login failed')",
            (datetime.now().isoformat(),),
        )
        storage._conn.commit()
        check = check_meroshare(
            storage._conn,
            _settings(
                meroshare_enabled=True,
                meroshare_dp_id="12300",
                meroshare_username="user",
                meroshare_password="pw",
            ),
        )
        assert check.status == WARN
        assert "last sync failed" in check.detail


class TestJournalAndPaper:
    def test_an_empty_journal_is_ok_not_a_warning(self, storage):
        check = check_journal(storage._conn)
        assert check.status == OK
        assert check.metrics["total"] == 0

    def test_an_overdue_open_prediction_warns_to_score_it(self, storage):
        storage._conn.execute(
            "INSERT INTO predictions (prediction_id, kind, symbol, made_on, horizon, "
            "horizon_days, deadline, action, reference_price, status, created_at) "
            "VALUES ('p1', 'plan', 'NABIL', '2026-01-01', 'day', 3, '2026-01-06', "
            "'BUY', 500.0, 'open', '2026-01-01T00:00:00Z')"
        )
        storage._conn.commit()
        check = check_journal(storage._conn)
        assert check.status == WARN
        assert check.metrics["overdue_open"] == 1
        assert "journal score" in check.detail

    def test_no_paper_trades_is_off(self, storage):
        assert check_paper(storage).status == OFF


class TestReport:
    def test_the_overall_status_is_the_worst_check(self, storage):
        report = system_health(storage, _settings())
        worst = max(
            health_mod._SEVERITY[c["status"]] for c in report["checks"]
        )
        assert health_mod._SEVERITY[report["status"]] == worst

    def test_a_switched_off_feature_cannot_drag_the_overall_status_down(self, storage):
        _seed_prices(storage, end=date.today())
        storage.log_ingest("sharesansar", "prices", date.today(), 250, "ok")
        DocumentIndex(storage._conn).upsert(
            [
                Document(
                    doc_id="d1",
                    kind=KIND_NEWS,
                    title="t",
                    body="b",
                    source="test",
                    business_date=date.today(),
                )
            ]
        )
        report = system_health(storage, _settings(analysis_mode="normal", meroshare_enabled=False))
        assert {c["name"] for c in report["checks"] if c["status"] == OFF} >= {"ai", "meroshare"}
        assert report["status"] == OK

    def test_every_check_runs_in_a_stable_order(self, storage):
        report = system_health(storage, _settings())
        assert [c["name"] for c in report["checks"]] == list(health_mod.CHECK_ORDER)

    def test_a_broken_check_fails_only_itself(self, storage, monkeypatch):
        def explode(*_args, **_kwargs):
            raise RuntimeError("check is broken")

        monkeypatch.setattr(health_mod, "check_rag", explode)
        report = system_health(storage, _settings())
        rag = next(c for c in report["checks"] if c["name"] == "rag")
        assert rag["status"] == FAIL
        assert "RuntimeError" in rag["detail"]
        # The rest of the report still arrived.
        assert len(report["checks"]) == len(health_mod.CHECK_ORDER)

    def test_problems_returns_only_warnings_and_failures(self, storage):
        report = system_health(storage, _settings())
        assert all(c["status"] in (WARN, FAIL) for c in problems(report))

    def test_the_report_never_contains_a_configured_password(self, storage):
        secret = "s3cret-do-not-leak"
        report = system_health(
            storage,
            _settings(
                meroshare_enabled=True,
                meroshare_dp_id="12300",
                meroshare_username="user",
                meroshare_password=secret,
                openrouter_api_key=secret,
                analysis_mode="ai",
            ),
        )
        assert secret not in repr(report)


class TestSnapshots:
    def test_reading_the_report_records_nothing(self, storage):
        system_health(storage, _settings())
        assert snapshot_history(storage._conn) == []

    def test_recording_stores_the_whole_report_and_its_counts(self, storage):
        report = system_health(storage, _settings())
        row_id = record_snapshot(storage._conn, report)
        history = snapshot_history(storage._conn)
        assert len(history) == 1
        assert history[0]["status"] == report["status"]
        assert history[0]["ok"] == report["counts"]["ok"]
        stored = snapshot(storage._conn, row_id)
        assert stored is not None
        assert [c["name"] for c in stored["checks"]] == list(health_mod.CHECK_ORDER)

    def test_history_is_newest_first_and_respects_the_limit(self, storage):
        report = system_health(storage, _settings())
        for hour in range(3):
            record_snapshot(
                storage._conn, {**report, "generated_at": f"2026-06-10T0{hour}:00:00+00:00"}
            )
        history = snapshot_history(storage._conn, limit=2)
        assert len(history) == 2
        assert history[0]["captured_at"] > history[1]["captured_at"]

    def test_an_unknown_snapshot_id_is_none_not_an_error(self, storage):
        assert snapshot(storage._conn, 4242) is None
