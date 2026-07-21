"""Polite HTTP base client shared by all ingestion sources.

Design goals:
  * Respect sites: per-host minimum request interval, capped retries with
    exponential backoff, a descriptive User-Agent, and NO attempt to bypass
    auth, rate limits, CAPTCHAs, or WAFs. If a source returns 401/403/429 we
    back off and surface the condition rather than evading it.
  * Auditability: every raw response can be cached to disk so reconciliation
    discrepancies can be traced back to exactly what each source returned.
  * Testability: a thin httpx.Client wrapper that respx can intercept.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from nepse_trader.config import Settings, get_settings
from nepse_trader.ingest.engines import (
    FetchEngine,
    HttpxEngine,
    TransportFailure,
    build_engine,
)
from nepse_trader.models import (
    FloorsheetEntry,
    IndexValue,
    MarketStatus,
    PriceBar,
    SourceName,
)


class RateLimitedError(Exception):
    """Raised when a source signals 429/403 — we back off, never bypass."""


class FetchError(Exception):
    """Non-retryable fetch failure (bad status, parse impossible)."""


@dataclass
class FetchResult:
    url: str
    status_code: int
    text: str
    headers: dict[str, str] = field(default_factory=dict)
    fetched_at: datetime = field(default_factory=lambda: datetime.now())

    def json(self) -> Any:
        return json.loads(self.text)


class _HostThrottle:
    """Enforces a minimum wall-clock gap between requests to each host."""

    def __init__(self, min_interval: float):
        self.min_interval = min_interval
        self._last: dict[str, float] = {}

    def wait(self, host: str, sleep=time.sleep, clock=time.monotonic) -> None:
        last = self._last.get(host)
        now = clock()
        if last is not None:
            elapsed = now - last
            if elapsed < self.min_interval:
                sleep(self.min_interval - elapsed)
        self._last[host] = clock()


class BaseClient:
    """Wraps httpx with throttling, retries, and optional raw-response caching."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.Client | None = None,
        throttle: _HostThrottle | None = None,
        cache_raw: bool = True,
        engine: FetchEngine | None = None,
    ):
        self.settings = settings or get_settings()
        # The fetch engine is the transport. By default it honours
        # settings.fetch_engine ("httpx" or "scrapling"); an explicit httpx
        # `client` (used by tests via respx) forces the httpx engine so mocking
        # keeps working unchanged.
        if engine is not None:
            self.engine = engine
        elif client is not None:
            self.engine = HttpxEngine(self.settings, client=client)
        else:
            self.engine = build_engine(self.settings)
        self.throttle = throttle or _HostThrottle(self.settings.min_request_interval)
        self.cache_raw = cache_raw

    def close(self) -> None:
        self.engine.close()

    def __enter__(self) -> BaseClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def fetch(
        self,
        url: str,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        json_body: Any | None = None,
    ) -> FetchResult:
        host = httpx.URL(url).host or "unknown"
        self.throttle.wait(host)
        result = self._do_request(url, method, params, headers, json_body)
        if self.cache_raw:
            self._cache(url, result)
        return result

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, TransportFailure, RateLimitedError)),
        wait=wait_exponential(multiplier=1.5, min=2, max=30),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def _do_request(
        self,
        url: str,
        method: str,
        params: dict[str, Any] | None,
        headers: dict[str, str] | None,
        json_body: Any | None,
    ) -> FetchResult:
        resp = self.engine.raw_request(url, method, params, headers, json_body)
        # Honour rate-limit / forbidden signals by backing off — never bypass.
        if resp.status_code in (429, 403):
            raise RateLimitedError(
                f"{resp.status_code} from {url}: backing off (we do not bypass limits)"
            )
        if resp.status_code >= 500:
            raise httpx.TransportError(f"server error {resp.status_code} from {url}")
        if resp.status_code >= 400:
            raise FetchError(f"{resp.status_code} from {url}: {resp.text[:200]}")
        return FetchResult(
            url=resp.url,
            status_code=resp.status_code,
            text=resp.text,
            headers=resp.headers,
        )

    def _cache(self, url: str, result: FetchResult) -> None:
        try:
            cache_dir: Path = self.settings.raw_cache_dir
            cache_dir.mkdir(parents=True, exist_ok=True)
            key = hashlib.sha256(url.encode()).hexdigest()[:16]
            stamp = result.fetched_at.strftime("%Y%m%d")
            path = cache_dir / f"{stamp}_{key}.txt"
            path.write_text(result.text, encoding="utf-8")
        except OSError:
            # Caching is best-effort; never let it break ingestion.
            pass


class SourceClient:
    """Interface every source adapter implements.

    Concrete clients (ShareSansar, Chukul, NEPSE official, HAR-replay) subclass
    this. Methods return [] when a source does not provide that data type, so
    the orchestrator can call uniformly and reconcile whatever is available.
    """

    name: SourceName = SourceName.MANUAL

    def fetch_prices(self, business_date: date | None = None) -> list[PriceBar]:
        raise NotImplementedError

    def fetch_indices(self, business_date: date | None = None) -> list[IndexValue]:
        return []

    def fetch_floorsheet(self, business_date: date | None = None) -> list[FloorsheetEntry]:
        return []

    def market_status(self) -> MarketStatus | None:
        return None
