"""Tests for the pluggable fetch engines and BaseClient wiring."""

from __future__ import annotations

import httpx
import pytest
import respx

from nepse_trader.config import Settings
from nepse_trader.ingest.base import BaseClient, FetchError, RateLimitedError
from nepse_trader.ingest.engines import (
    HttpxEngine,
    RawResponse,
    TransportFailure,
    build_engine,
    scrapling_fetcher_available,
)


def _settings(**kw) -> Settings:
    return Settings(min_request_interval=0, **kw)


def test_build_engine_defaults_to_httpx():
    eng = build_engine(_settings())
    assert eng.name == "httpx"


def test_build_engine_scrapling_falls_back_when_unavailable(monkeypatch):
    monkeypatch.setattr("nepse_trader.ingest.engines.scrapling_fetcher_available", lambda: False)
    eng = build_engine(_settings(fetch_engine="scrapling"))
    assert eng.name == "httpx"  # graceful fallback


def test_build_engine_scrapling_when_available():
    if not scrapling_fetcher_available():
        pytest.skip("scrapling fetcher not installed")
    eng = build_engine(_settings(fetch_engine="scrapling"))
    assert eng.name == "scrapling"


@respx.mock
def test_httpx_engine_request_roundtrip():
    respx.get("https://example.test/data").mock(
        return_value=httpx.Response(200, text="ok", headers={"X-T": "1"})
    )
    eng = HttpxEngine(_settings())
    r = eng.raw_request("https://example.test/data")
    assert isinstance(r, RawResponse)
    assert r.status_code == 200 and r.text == "ok" and r.headers["x-t"] == "1"


@respx.mock
def test_baseclient_uses_injected_httpx_client_for_mocking():
    respx.get("https://example.test/x").mock(return_value=httpx.Response(200, json={"a": 1}))
    client = BaseClient(settings=_settings(), client=httpx.Client())
    res = client.fetch("https://example.test/x")
    assert res.json() == {"a": 1}


class _BoomEngine:
    name = "boom"

    def raw_request(self, *a, **k):
        raise TransportFailure("network down")

    def close(self):
        pass


def test_baseclient_retries_transport_failure_then_raises():
    client = BaseClient(settings=_settings(max_retries=3), engine=_BoomEngine())
    with pytest.raises(TransportFailure):
        client.fetch("https://example.test/y")


class _StatusEngine:
    name = "status"

    def __init__(self, code):
        self.code = code

    def raw_request(self, url, *a, **k):
        return RawResponse(status_code=self.code, text="body", url=url)

    def close(self):
        pass


def test_baseclient_backs_off_on_403_not_bypass():
    client = BaseClient(settings=_settings(), engine=_StatusEngine(403))
    with pytest.raises(RateLimitedError):
        client.fetch("https://example.test/z")


def test_baseclient_raises_fetcherror_on_404():
    client = BaseClient(settings=_settings(), engine=_StatusEngine(404))
    with pytest.raises(FetchError):
        client.fetch("https://example.test/z")


@respx.mock
@pytest.mark.asyncio
async def test_async_fetch_roundtrip():
    respx.get("https://example.test/async").mock(
        return_value=httpx.Response(200, text="async-ok")
    )
    client = BaseClient(settings=_settings(), client=httpx.Client())
    result = await client.async_fetch("https://example.test/async")
    assert result.text == "async-ok"


@respx.mock
@pytest.mark.asyncio
async def test_async_fetch_raises_on_retryable():
    respx.get("https://example.test/async-err").mock(
        return_value=httpx.Response(500)
    )
    client = BaseClient(settings=_settings(max_retries=1), client=httpx.Client())
    with pytest.raises(httpx.TransportError):
        await client.async_fetch("https://example.test/async-err")
