"""HAR analysis: discover data endpoints in a capture, emit config, redact.

A HAR file is a JSON document with log.entries[], each having a request (url,
method, headers, queryString, postData) and a response (status, content.text).
We rank entries by how likely they are to be a useful market-data endpoint:
JSON payloads that look like arrays / DataTables and mention market keywords
score highest; server-rendered HTML tables score next; everything else is noise.
"""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_MARKET_KEYWORDS = (
    "symbol", "ltp", "close", "open", "high", "low", "turnover", "volume",
    "index", "floorsheet", "gainer", "loser", "price", "scrip", "security",
    "nepse", "today-price", "today-share-price", "market", "quantity", "rate",
)

_SENSITIVE_HEADERS = {"cookie", "set-cookie", "authorization", "x-csrf-token", "x-xsrf-token"}

# Query/form parameter names that commonly carry credentials or session state.
_SENSITIVE_PARAM_PATTERNS = (
    "token", "auth", "salter", "csrf", "xsrf", "access", "refresh",
    "session", "sid", "jwt", "bearer", "key", "secret", "password",
)

# URL substrings whose RESPONSE bodies carry credentials (e.g. NEPSE's
# /api/authenticate/prove returns access/refresh tokens in JSON).
_AUTH_URL_MARKERS = ("authenticate", "token", "login", "auth/")


@dataclass
class EndpointCandidate:
    method: str
    url: str
    kind: str  # json_api | html_table | other
    score: float
    status: int
    content_type: str
    sample_keys: list[str] = field(default_factory=list)
    query_params: list[str] = field(default_factory=list)

    def as_row(self) -> tuple[str, str, str, str]:
        return (
            f"{self.method} {self._short_url()}",
            self.kind,
            f"{self.score:.0f}",
            ", ".join(self.sample_keys[:8]),
        )

    def _short_url(self) -> str:
        return self.url if len(self.url) <= 80 else self.url[:77] + "..."


def load_har(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _entries(har: dict[str, Any]) -> list[dict[str, Any]]:
    return (har.get("log") or {}).get("entries") or []


def decode_content(entry: dict[str, Any]) -> str:
    """Return the response body text, decoding base64 when so flagged."""
    content = (entry.get("response") or {}).get("content") or {}
    text = content.get("text") or ""
    if content.get("encoding") == "base64" and text:
        try:
            return base64.b64decode(text).decode("utf-8", errors="replace")
        except (binascii.Error, ValueError):
            return text
    return text


def find_entries(har: dict[str, Any], url_substring: str) -> list[dict[str, Any]]:
    out = []
    for e in _entries(har):
        url = ((e.get("request") or {}).get("url")) or ""
        if url_substring in url:
            out.append(e)
    return out


def _content_type(entry: dict[str, Any]) -> str:
    content = (entry.get("response") or {}).get("content") or {}
    ct = content.get("mimeType") or ""
    if ct:
        return ct.split(";")[0].strip().lower()
    for h in (entry.get("response") or {}).get("headers") or []:
        if (h.get("name") or "").lower() == "content-type":
            return (h.get("value") or "").split(";")[0].strip().lower()
    return ""


def _keyword_score(text: str) -> float:
    low = text.lower()
    return sum(2.0 for kw in _MARKET_KEYWORDS if kw in low)


def _json_sample_keys(obj: Any) -> list[str]:
    # Drill into common DataTables / paginated shapes to find the row keys.
    if isinstance(obj, dict):
        for container in ("data", "content", "results", "floorsheets", "rows"):
            if container in obj:
                inner = obj[container]
                if isinstance(inner, dict) and "content" in inner:
                    inner = inner["content"]
                if isinstance(inner, list) and inner and isinstance(inner[0], dict):
                    return list(inner[0].keys())
        # Fall back to top-level keys.
        return list(obj.keys())
    if isinstance(obj, list) and obj and isinstance(obj[0], dict):
        return list(obj[0].keys())
    return []


def analyze(har: dict[str, Any]) -> list[EndpointCandidate]:
    candidates: list[EndpointCandidate] = []
    for e in _entries(har):
        req = e.get("request") or {}
        resp = e.get("response") or {}
        url = req.get("url") or ""
        method = (req.get("method") or "GET").upper()
        status = int(resp.get("status") or 0)
        ct = _content_type(e)
        body = decode_content(e)
        query_params = [q.get("name", "") for q in (req.get("queryString") or [])]

        kind = "other"
        score = 0.0
        sample_keys: list[str] = []

        is_json = "json" in ct or _looks_like_json(body)
        if is_json:
            try:
                parsed = json.loads(body) if body else None
            except (json.JSONDecodeError, ValueError):
                parsed = None
            if parsed is not None:
                kind = "json_api"
                sample_keys = _json_sample_keys(parsed)
                score = 10.0 + _keyword_score(" ".join(sample_keys)) + _keyword_score(url)
                if isinstance(parsed, list) or _json_sample_keys(parsed):
                    score += 5.0
        elif "html" in ct or "<table" in body.lower():
            kind = "html_table"
            n_tables = body.lower().count("<table")
            score = 3.0 * n_tables + _keyword_score(url) + min(_keyword_score(body), 10.0)
            sample_keys = _table_ids(body)

        # Penalise obvious non-data assets.
        if any(url.lower().endswith(ext) for ext in (".js", ".css", ".png", ".jpg", ".svg", ".woff", ".woff2", ".ico")):
            score = 0.0
            kind = "other"

        if score > 0:
            candidates.append(
                EndpointCandidate(
                    method=method, url=url, kind=kind, score=score, status=status,
                    content_type=ct, sample_keys=sample_keys, query_params=query_params,
                )
            )

    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates


def _looks_like_json(body: str) -> bool:
    s = body.lstrip()[:1]
    return s in ("{", "[")


def _table_ids(html: str) -> list[str]:
    import re

    ids = re.findall(r"<table[^>]*\bid=[\"']([^\"']+)[\"']", html, flags=re.IGNORECASE)
    return [f"table#{i}" for i in ids]


def to_config_snippet(har: dict[str, Any], source: str, top: int = 8) -> str:
    """Emit a sources.yaml snippet for the highest-scoring endpoints."""
    cands = [c for c in analyze(har) if c.kind in ("json_api", "html_table")][:top]
    lines = [f"  {source}:", f'    name: {source}', "    endpoints:"]
    seen: set[str] = set()
    for c in cands:
        key = _endpoint_key(c.url, seen)
        seen.add(key)
        lines.append(f"      {key}:")
        lines.append(f"        method: {c.method}")
        lines.append(f'        url: "{c.url.split("?")[0]}"')
        if c.query_params:
            params = ", ".join(f'{p}: ""' for p in c.query_params if p)
            lines.append(f"        params: {{ {params} }}")
        lines.append("        confidence: medium")
        note = f"kind={c.kind}; keys={','.join(c.sample_keys[:6])}".replace('"', "'")
        lines.append(f'        notes: "{note}"')
    if not cands:
        lines.append("      # (no JSON/HTML data endpoints found in this HAR)")
    return "\n".join(lines)


def _endpoint_key(url: str, seen: set[str]) -> str:
    path = url.split("?")[0].rstrip("/").rsplit("/", 1)[-1] or "root"
    key = "".join(ch if ch.isalnum() else "_" for ch in path).strip("_").lower() or "endpoint"
    base = key
    n = 2
    while key in seen:
        key = f"{base}_{n}"
        n += 1
    return key


def _is_sensitive_param(name: str) -> bool:
    low = (name or "").lower()
    return any(p in low for p in _SENSITIVE_PARAM_PATTERNS)


def _redact_url_query(url: str) -> str:
    """Blank the values of sensitive query params inside the URL string itself."""
    if "?" not in url:
        return url
    base, _, query = url.partition("?")
    parts = []
    for piece in query.split("&"):
        name, sep, _value = piece.partition("=")
        if sep and _is_sensitive_param(name):
            parts.append(f"{name}=REDACTED")
        else:
            parts.append(piece)
    return base + "?" + "&".join(parts)


def redact(har: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of the HAR safe to share: strips cookies, auth headers,
    request bodies, sensitive query params (in both queryString and the URL),
    and the response bodies of auth/token endpoints.

    Market-data response bodies are kept — they are the point of the capture.
    """
    out = json.loads(json.dumps(har))  # deep copy
    for e in _entries(out):
        req = e.get("request") or {}
        resp = e.get("response") or {}

        for obj in (req, resp):
            obj["cookies"] = []
            headers = obj.get("headers") or []
            obj["headers"] = [
                h for h in headers if (h.get("name") or "").lower() not in _SENSITIVE_HEADERS
            ]

        # Request bodies routinely carry tokens/credentials (e.g. POST payload
        # ids, login forms). The analyzer never needs them, so drop them all.
        if "postData" in req:
            req["postData"] = {
                "mimeType": (req.get("postData") or {}).get("mimeType", ""),
                "text": "REDACTED",
            }

        # Sensitive query params: blank in the structured list AND in the URL.
        for q in req.get("queryString") or []:
            if _is_sensitive_param(q.get("name", "")):
                q["value"] = "REDACTED"
        if req.get("url"):
            req["url"] = _redact_url_query(req["url"])

        # Auth/token endpoints return credentials in their response bodies
        # (e.g. NEPSE /api/authenticate/prove). Blank those bodies entirely.
        # Match on the URL *path* only — query strings legitimately contain
        # words like "accessToken" on market-data endpoints we want to keep.
        path_low = (req.get("url") or "").partition("?")[0].lower()
        if any(m in path_low for m in _AUTH_URL_MARKERS):
            content = resp.get("content") or {}
            content["text"] = "REDACTED"
            content.pop("encoding", None)
            resp["content"] = content
    return out
