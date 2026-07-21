"""Pluggable HTTP fetch engines for BaseClient.

Two backends, one interface (`raw_request` -> RawResponse):
  * **httpx** (default) — the original lightweight client.
  * **scrapling** — Scrapling's curl_cffi-based Fetcher, used in PLAIN mode for
    public sources. It can optionally use a TLS-impersonation profile for
    compatibility with picky-but-public CDNs, but ships with stealth headers OFF
    and NO Cloudflare/WAF/anti-bot solving. We do not evade access controls.

Both engines are transport only: status-code policy (back off on 403/429, treat
5xx as transient) stays in BaseClient so behaviour is identical regardless of
backend.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field
from typing import Any

import httpx

from nepse_trader.config import Settings


@dataclass
class RawResponse:
    status_code: int
    text: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)


class TransportFailure(Exception):
    """A network-level failure that BaseClient should treat as retryable."""


class FetchEngine:
    """Interface every engine implements."""

    name = "base"

    def raw_request(
        self,
        url: str,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        json_body: Any | None = None,
    ) -> RawResponse:
        raise NotImplementedError

    async def async_raw_request(
        self,
        url: str,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        json_body: Any | None = None,
    ) -> RawResponse:
        raise NotImplementedError

    def close(self) -> None:  # pragma: no cover - trivial
        pass


class HttpxEngine(FetchEngine):
    name = "httpx"

    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.settings = settings
        self._owns_client = client is None
        self.client = client or httpx.Client(
            timeout=settings.request_timeout,
            headers={"User-Agent": settings.user_agent},
            follow_redirects=True,
        )
        self._async_client: httpx.AsyncClient | None = None

    def raw_request(self, url, method="GET", params=None, headers=None, json_body=None):
        try:
            resp = self.client.request(
                method.upper(), url, params=params, headers=headers, json=json_body
            )
        except httpx.TransportError as exc:
            raise TransportFailure(str(exc)) from exc
        return RawResponse(
            status_code=resp.status_code,
            text=resp.text,
            url=str(resp.url),
            headers=dict(resp.headers),
        )

    async def async_raw_request(self, url, method="GET", params=None, headers=None, json_body=None):
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(
                timeout=self.settings.request_timeout,
                headers={"User-Agent": self.settings.user_agent},
                follow_redirects=True,
            )
        try:
            resp = await self._async_client.request(
                method.upper(), url, params=params, headers=headers, json=json_body
            )
        except httpx.TransportError as exc:
            raise TransportFailure(str(exc)) from exc
        return RawResponse(
            status_code=resp.status_code,
            text=resp.text,
            url=str(resp.url),
            headers=dict(resp.headers),
        )

    def close(self):
        if self._owns_client:
            self.client.close()


class ScraplingEngine(FetchEngine):
    """Scrapling (curl_cffi) engine in PLAIN mode — no stealth, no CF bypass."""

    name = "scrapling"

    def __init__(self, settings: Settings):
        self.settings = settings
        from scrapling.fetchers import Fetcher  # raises if not installed

        self._fetcher = Fetcher

    def raw_request(self, url, method="GET", params=None, headers=None, json_body=None):
        base_headers = {"User-Agent": self.settings.user_agent}
        if headers:
            base_headers.update(headers)
        kwargs: dict[str, Any] = {
            "timeout": self.settings.request_timeout,
            "headers": base_headers,
            "stealthy_headers": False,  # honest headers; no fingerprint spoofing
            "follow_redirects": True,
        }
        if self.settings.scrapling_impersonate:
            kwargs["impersonate"] = self.settings.scrapling_impersonate
        if params:
            kwargs["params"] = params
        try:
            if method.upper() == "POST":
                page = self._fetcher.post(url, json=json_body, **kwargs)
            else:
                page = self._fetcher.get(url, **kwargs)
        except Exception as exc:  # curl_cffi transport errors
            raise TransportFailure(str(exc)) from exc
        return RawResponse(
            status_code=int(getattr(page, "status", 0)),
            text=_response_text(page),
            url=str(getattr(page, "url", url)),
            headers=dict(getattr(page, "headers", {}) or {}),
        )


def _response_text(page: Any) -> str:
    """Extract the decoded body from a Scrapling Response.

    Scrapling's ``.text`` can be empty for some content types while the raw
    bytes live on ``.body``; fall back to decoding those (with the response's
    declared encoding when available).
    """
    text = getattr(page, "text", None)
    text = str(text) if text else ""
    if text:
        return text
    body = getattr(page, "body", b"")
    if isinstance(body, (bytes, bytearray)):
        enc = getattr(page, "encoding", None) or "utf-8"
        try:
            return bytes(body).decode(enc, "replace")
        except (LookupError, TypeError):
            return bytes(body).decode("utf-8", "replace")
    return str(body) if body else ""


@functools.lru_cache(maxsize=1)
def scrapling_fetcher_available() -> bool:
    try:
        from scrapling.fetchers import Fetcher  # noqa: F401

        return True
    except Exception:
        return False


def build_engine(settings: Settings, client: httpx.Client | None = None) -> FetchEngine:
    """Construct the configured fetch engine, falling back to httpx if Scrapling
    is requested but unavailable."""
    choice = (settings.fetch_engine or "httpx").lower()
    if choice == "scrapling" and scrapling_fetcher_available():
        return ScraplingEngine(settings)
    return HttpxEngine(settings, client=client)
