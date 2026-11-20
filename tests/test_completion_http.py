import gzip
import json
from datetime import UTC, date, datetime

import httpx
import pytest

from nepse_trader.config import Settings
from nepse_trader.ingest.base import BaseClient, FetchError, RateLimitedError, SourceClient
from nepse_trader.ingest.http_policy import retry_after_seconds
from nepse_trader.ingest.policy import IngestPolicy
from nepse_trader.logging_setup import JsonLogFormatter
from nepse_trader.models import PriceBar, SourceName
from nepse_trader.pipeline import DailyPipeline
from nepse_trader.storage import Storage


def test_robots_denial_is_cached_and_never_requests_disallowed_path():
    calls = []
    def handle(request):
        calls.append(request.url.path)
        return httpx.Response(200, text="User-agent: *\nDisallow: /private\nAllow: /public\n")
    settings = Settings(_env_file=None, respect_robots=True, min_request_interval=0)
    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        client = BaseClient(settings, client=http, cache_raw=False)
        for _ in range(2):
            with pytest.raises(FetchError, match="disallows"):
                client.fetch("https://example.test/private")
        assert calls == ["/robots.txt"]


def test_offline_does_not_even_request_robots():
    def handle(request):
        raise AssertionError("Network should never be called")
    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        client = BaseClient(Settings(_env_file=None, online=False), client=http)
        with pytest.raises(FetchError, match="offline"):
            client.fetch("https://example.test/public")


def test_retry_after_dates_and_long_backoff_do_not_retry_early():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert retry_after_seconds("30", now) == 30
    assert retry_after_seconds("Thu, 01 Jan 2026 00:01:00 GMT", now) == 60
    assert retry_after_seconds("junk", now) is None
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "120"})
    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        client = BaseClient(Settings(_env_file=None, respect_robots=False, min_request_interval=0), client=http, cache_raw=False)
        with pytest.raises(FetchError, match="long Retry-After"):
            client.fetch("https://example.test/public")
        with pytest.raises(FetchError, match="still active"):
            client.fetch("https://example.test/public")
        assert len(calls) == 1


def test_cache_is_compressed_and_old_plain_captures_are_preserved(tmp_path):
    legacy = tmp_path / "20200101_deadbeef.txt"
    legacy.write_text("older capture")
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, text="public prices"))) as http:
        client = BaseClient(Settings(_env_file=None, respect_robots=False, raw_cache_dir=tmp_path), client=http)
        client.fetch("https://example.test/public")
    caches = list(tmp_path.glob("*.gz"))
    assert len(caches) == 1
    assert gzip.open(caches[0], "rt").read() == "public prices"
    assert legacy.read_text() == "older capture"


def test_circuit_breaker_persists_and_force_never_overrides_offline(tmp_path):
    path = tmp_path / "db"
    settings = Settings(_env_file=None, circuit_failure_threshold=3)
    with Storage(path) as storage:
        policy = IngestPolicy(storage, settings)
        for _ in range(3):
            policy.record("sharesansar", [], date(2026, 1, 1))
    with Storage(path) as storage:
        policy = IngestPolicy(storage, settings)
        assert "cooling" in policy.skip_reason("sharesansar", None)
        assert policy.skip_reason("sharesansar", None, force=True) is None
        assert "Offline" in IngestPolicy(storage, settings.model_copy(update={"online": False})).skip_reason("sharesansar", None, force=True)


def test_ingestion_logs_observed_date_and_skips_completed_requested_date(tmp_path):
    class Source:
        name = SourceName.SHARESANSAR
        calls = 0
        def fetch_prices(self, business_date):
            self.calls += 1
            return [PriceBar(symbol="NABIL", business_date=date(2026, 1, 4), close=100, source=self.name)]
        def fetch_indices(self, business_date):
            return []
    source = Source()
    with Storage(tmp_path / "db") as storage:
        pipe = DailyPipeline(Settings(_env_file=None), storage=storage, clients=[source])
        pipe.ingest(date(2026, 1, 1))
        assert not storage.source_date_ingested("sharesansar", date(2026, 1, 1))
        assert storage.source_date_ingested("sharesansar", date(2026, 1, 4))
        assert pipe.ingest(date(2026, 1, 4)).skipped
        assert source.calls == 1
        pipe.ingest(date(2026, 1, 4), force=True)
        assert source.calls == 2


def test_json_logs_have_stable_run_id_and_parseable_exception():
    import logging
    formatter = JsonLogFormatter("run-123")
    record = logging.LogRecord("nepse", logging.INFO, "file", 1, "hello %s", ("world",), None)
    parsed = json.loads(formatter.format(record))
    assert parsed["run_id"] == "run-123"
    assert parsed["message"] == "hello world"


def test_robots_retry_after_suppresses_followup_requests():
    calls = []
    def handle(request):
        calls.append(request.url.path)
        return httpx.Response(429, headers={"Retry-After": "3600"})
    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        client = BaseClient(Settings(_env_file=None, respect_robots=True, min_request_interval=0), client=http, cache_raw=False)
        with pytest.raises(FetchError, match="long Retry-After"):
            client.fetch("https://example.test/a")
        with pytest.raises(FetchError, match="still active"):
            client.fetch("https://example.test/b")
        assert calls == ["/robots.txt"]


def test_short_robots_retry_after_defers_the_next_request():
    calls = []
    def handle(request):
        calls.append(request.url.path)
        return httpx.Response(429, headers={"Retry-After": "30"})
    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        client = BaseClient(Settings(_env_file=None, respect_robots=True, min_request_interval=0), client=http, cache_raw=False)
        with pytest.raises(RateLimitedError):
            client.fetch("https://example.test/a")
        with pytest.raises(FetchError, match="still active"):
            client.fetch("https://example.test/b")
        assert calls == ["/robots.txt"]


@pytest.mark.asyncio
async def test_async_source_fallback_fetches_two_sources_concurrently(tmp_path):
    import threading
    barrier = threading.Barrier(2)
    class Source(SourceClient):
        def __init__(self, name):
            self.name = name
        def fetch_prices(self, business_date=None):
            barrier.wait(timeout=3)
            return [PriceBar(symbol="A", business_date=date(2026, 1, 4), close=100, source=self.name)]
    with Storage(tmp_path / "db") as storage:
        pipe = DailyPipeline(Settings(_env_file=None), storage=storage,
            clients=[Source(SourceName.SHARESANSAR), Source(SourceName.MEROLAGANI)])
        result = await pipe.async_ingest()
        assert result.total_bars == 2
        assert not result.errors
