"""Issuer-bound statement evidence, kept separate from provider snapshots.

Matching a reported value to an official document is not an audit opinion.
Uploaded values can be attested, but only server-fetched issuer documents can
produce ``matched_official_excerpt`` evidence.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import re
import shutil
import socket
import subprocess
import tempfile
import threading
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import httpx
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator
from selectolax.parser import HTMLParser

from nepse_trader.config import Settings
from nepse_trader.ingest.base import BaseClient
from nepse_trader.ingest.engines import FetchEngine, RawResponse

METRIC_LABELS = {
    "eps": ("eps", "earnings per share"),
    "book_value": ("book value", "net worth per share"),
    "roe_pct": ("roe", "return on equity"),
    "operating_cash_flow": (
        "operating cash flow",
        "net cash from operating activities",
        "cash flow from operations",
    ),
    "net_income": ("net income", "net profit", "profit for the period"),
    "total_debt": ("total debt", "total borrowings"),
    "total_equity": ("total equity", "shareholders equity"),
    "total_assets": ("total assets",),
    "cash_and_equivalents": ("cash and cash equivalents", "cash and equivalents"),
    "interest_expense": ("interest expense", "finance costs"),
    "ebit": ("ebit", "earnings before interest and tax"),
    "npl_pct": ("npl", "non performing loan", "non-performing loan"),
    "capital_adequacy_pct": ("capital adequacy", "capital to risk weighted assets", "car"),
    "core_capital_pct": ("core capital ratio", "tier 1 capital"),
    "nav_per_unit": ("nav per unit", "net asset value per unit", "nav"),
    "expense_ratio_pct": ("expense ratio", "total expense ratio"),
}
AMOUNT_METRICS = frozenset(
    {
        "operating_cash_flow",
        "net_income",
        "total_debt",
        "total_equity",
        "total_assets",
        "cash_and_equivalents",
        "interest_expense",
        "ebit",
    }
)
PERCENT_METRICS = frozenset(
    {"roe_pct", "npl_pct", "capital_adequacy_pct", "core_capital_pct", "expense_ratio_pct"}
)
PER_SHARE_METRICS = frozenset({"eps", "book_value", "nav_per_unit"})
UNIT_SCALE = {
    "NPR": 1,
    "NPR_thousands": 1000,
    "NPR_millions": 1000000,
    "percent": 1,
    "NPR_per_share": 1,
}
NPT = ZoneInfo("Asia/Kathmandu")

# This is a deployment trust policy, not a claim that every page on a host is
# audited or that scraped provider values have become an official statement.
TRUSTED_ISSUERS = {
    "NABIL": ("Nabil Bank", frozenset({"nabilbank.com", "www.nabilbank.com"})),
    "NMB": ("NMB Bank", frozenset({"nmb.com.np", "www.nmb.com.np"})),
    "EBL": ("Everest Bank", frozenset({"everestbankltd.com", "www.everestbankltd.com"})),
    "SANIMA": ("Sanima Bank", frozenset({"sanimabank.com", "www.sanimabank.com"})),
    "SCB": ("Standard Chartered Bank Nepal", frozenset({"sc.com", "www.sc.com"})),
    "NTC": ("Nepal Telecom", frozenset({"ntc.net.np", "www.ntc.net.np"})),
}


class MetricSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    value: float = Field(allow_inf_nan=False, strict=True)
    unit: Literal["NPR", "NPR_thousands", "NPR_millions", "percent", "NPR_per_share"]
    quote: str = Field(min_length=3, max_length=2000)
    context_quote: str | None = Field(None, max_length=12000)
    unit_quote: str = Field(min_length=3, max_length=500)
    basis: Literal["reported", "annualized", "ttm"] = "reported"


class StatementSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    symbol: str = Field(min_length=1, max_length=25)
    source_url: str = Field(min_length=8, max_length=2048)
    period_start: date
    period_end: date
    period_basis: Literal["annual", "quarter", "year_to_date", "ttm"]
    period_quote: str = Field(min_length=8, max_length=2000)
    published_on: date | None = None
    publication_quote: str | None = Field(None, max_length=2000)
    metrics: dict[str, MetricSubmission] = Field(min_length=1, max_length=16)

    @field_validator("symbol")
    @classmethod
    def symbol_name(cls, value):
        value = value.strip().upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9.-]{0,24}", value):
            raise ValueError("Use a valid security symbol.")
        return value

    @field_validator("source_url")
    @classmethod
    def public_reference(cls, value):
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.fragment
            or parsed.port not in (None, 443)
        ):
            raise ValueError("Use an HTTPS document reference without credentials or fragments.")
        try:
            address = ipaddress.ip_address(parsed.hostname)
        except ValueError:
            return value
        if not address.is_global:
            raise ValueError("Private addresses cannot be financial document references.")
        return value

    @field_validator("metrics")
    @classmethod
    def known_metrics(cls, metrics):
        for name, item in metrics.items():
            if name not in METRIC_LABELS:
                raise ValueError(f"Unsupported financial metric: {name}")
            if name in AMOUNT_METRICS and item.unit not in {"NPR", "NPR_thousands", "NPR_millions"}:
                raise ValueError(f"{name} requires an explicit NPR amount unit.")
            if name in PERCENT_METRICS and item.unit != "percent":
                raise ValueError(f"{name} requires percentage units.")
            if name in PER_SHARE_METRICS and item.unit != "NPR_per_share":
                raise ValueError(f"{name} requires NPR per share/unit.")
        return metrics

    @model_validator(mode="after")
    def dated_period(self):
        if self.period_start >= self.period_end:
            raise ValueError("Statement period start must precede its end.")
        days = (self.period_end - self.period_start).days
        if (
            days > 370
            or (self.period_basis in {"annual", "ttm"} and days < 330)
            or (self.period_basis == "quarter" and not 75 <= days <= 110)
        ):
            raise ValueError("Reporting dates do not match the declared period basis.")
        if self.published_on and self.published_on < self.period_end:
            raise ValueError("A statement cannot be published before its period ends.")
        return self


class FinancialEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    evidence_id: str
    symbol: str
    source_url: str
    document_sha256: str | None
    period_start: date
    period_end: date
    period_basis: Literal["annual", "quarter", "year_to_date", "ttm", "as_of"]
    period_label: str | None = None
    source_kind: Literal["issuer", "regulator"] = "issuer"
    published_on: date | None
    publication_quote: str | None = None
    available_at: AwareDatetime
    retrieved_at: AwareDatetime | None
    verified_at: AwareDatetime | None
    verification_kind: Literal["matched_official_excerpt", "manual_attestation"]
    metrics: dict[str, dict]
    notes: list[str]

    @field_validator("metrics")
    @classmethod
    def finite_values(cls, values):
        if not values or any(
            name not in METRIC_LABELS
            or not isinstance(item.get("value"), (int, float))
            or isinstance(item.get("value"), bool)
            or not math.isfinite(item["value"])
            for name, item in values.items()
        ):
            raise ValueError("Evidence must contain finite, recognized normalized metric values.")
        return values

    @model_validator(mode="after")
    def evidence_dates_and_status(self):
        observed = self.available_at.astimezone(NPT).date()
        if (
            self.period_start > self.period_end
            or (self.period_start == self.period_end) != (self.period_basis == "as_of")
            or self.period_end > observed
            or (self.published_on and not self.period_end <= self.published_on <= observed)
        ):
            raise ValueError("Financial evidence dates are inconsistent.")
        if self.verification_kind == "matched_official_excerpt":
            if (
                not self.document_sha256
                or not re.fullmatch(r"[a-f0-9]{64}", self.document_sha256)
                or not self.retrieved_at
                or not self.verified_at
            ):
                raise ValueError(
                    "Matched official evidence requires a document hash and server retrieval/verification timestamps."
                )
            if not self.retrieved_at <= self.verified_at <= self.available_at:
                raise ValueError("Evidence availability must follow retrieval and verification.")
        elif self.verified_at is not None:
            raise ValueError("Manual attestation cannot carry an official verification timestamp.")
        return self


def _normalized(text: str) -> str:
    return " ".join(text.replace("\xa0", " ").split()).casefold()


def _public_url(url: str, symbol: str, issuers=TRUSTED_ISSUERS, *, resolve=True) -> str:
    parsed = urlsplit(url)
    issuer = issuers.get(symbol)
    if not issuer or parsed.scheme != "https" or parsed.hostname not in issuer[1]:
        raise ValueError(
            "Official verification requires a registered issuer HTTPS host for this symbol."
        )
    if parsed.username or parsed.password or parsed.fragment or parsed.port not in (None, 443):
        raise ValueError("Credentials, fragments and non-HTTPS ports are not accepted.")
    if resolve:
        addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
        if not addresses or any(
            not ipaddress.ip_address(item[4][0]).is_global for item in addresses
        ):
            raise ValueError("The issuer hostname must resolve only to public addresses.")
    return url


class _OfficialEngine(FetchEngine):
    """Bounded transport; BaseClient retains robots/throttle/status policy."""

    name = "official_evidence"

    def __init__(self, settings, symbol, issuers, client=None):
        self.symbol, self.issuers = symbol, issuers
        self.client = client or httpx.Client(
            timeout=min(settings.request_timeout, 20),
            follow_redirects=False,
            trust_env=False,
            headers={"User-Agent": settings.user_agent},
        )
        self.owns_client = client is None
        self.user_agent = settings.user_agent
        self.body = b""
        self.retrieved_at = None

    def raw_request(self, url, method="GET", params=None, headers=None, json_body=None):
        _public_url(url, self.symbol, self.issuers)
        limit = 128000 if urlsplit(url).path == "/robots.txt" else 4000000
        request_headers = {
            "User-Agent": self.user_agent,
            "Accept-Encoding": "identity",
            **(headers or {}),
        }
        with self.client.stream(
            "GET", url, follow_redirects=False, headers=request_headers
        ) as response:
            if 300 <= response.status_code < 400:
                raise ValueError(
                    "Official evidence redirects are refused; use the final registered issuer URL."
                )
            if int(response.headers.get("content-length", 0) or 0) > limit:
                raise ValueError("Official document exceeds the download limit.")
            if response.headers.get("content-encoding", "identity").lower() != "identity":
                raise ValueError(
                    "Compressed official responses are not accepted by the bounded verifier."
                )
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > limit:
                    raise ValueError("Official document exceeds the download limit.")
                chunks.append(chunk)
            body = b"".join(chunks)
            if urlsplit(url).path != "/robots.txt":
                self.body, self.retrieved_at = body, datetime.now(UTC)
            return RawResponse(
                response.status_code,
                body.decode("utf-8", "replace"),
                str(response.url),
                dict(response.headers),
            )

    def close(self):
        if self.owns_client:
            self.client.close()


def _document_text(body: bytes) -> str:
    if body.startswith(b"%PDF"):
        executable = shutil.which("pdftotext")
        if not executable:
            raise ValueError(
                "PDF text extraction is unavailable; retain this document as manually attested evidence."
            )
        with tempfile.NamedTemporaryFile(suffix=".pdf") as source:
            source.write(body)
            source.flush()
            process = subprocess.Popen(
                [executable, "-f", "1", "-l", "40", "-layout", source.name, "-"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            timer = threading.Timer(15, process.kill)
            timer.daemon = True
            timer.start()
            try:
                chunks, size = [], 0
                while chunk := process.stdout.read(65536):
                    size += len(chunk)
                    if size > 2000000:
                        raise ValueError("Extracted statement text exceeds the limit.")
                    chunks.append(chunk)
                if process.wait(timeout=1) != 0:
                    raise ValueError("PDF text extraction failed or exceeded its time limit.")
                return b"".join(chunks).decode("utf-8", "replace")
            finally:
                timer.cancel()
                if process.poll() is None:
                    process.kill()
                    process.wait()
                process.stdout.close()
    text = body.decode("utf-8", "strict")
    tree = HTMLParser(text)
    for node in tree.css("script,style,noscript"):
        node.decompose()
    return tree.body.text(separator=" ") if tree.body else tree.root.text(separator=" ")


def _date_in_text(day: date, text: str) -> bool:
    formats = (
        day.isoformat(),
        day.strftime("%d %B %Y"),
        day.strftime("%B %d, %Y"),
        day.strftime("%d %b %Y"),
    )
    normalized = _normalized(text)
    return any(_normalized(value) in normalized for value in formats)


def _metric_values(
    submission: StatementSubmission, text: str | None, rows=None, contexts=None
) -> dict:
    values = {}
    normalized_text = _normalized(text) if text is not None else None
    for name, item in submission.metrics.items():
        if normalized_text is not None:
            quote = _normalized(item.quote)
            unit_quote = _normalized(item.unit_quote)
            if quote not in normalized_text or unit_quote not in normalized_text:
                raise ValueError(
                    f"{name}: cited metric/unit excerpt is absent from the fetched document."
                )
            if rows is not None and quote not in rows:
                raise ValueError(
                    f"{name}: cite a complete source row or line, not a cropped value from multiple columns."
                )
            context = _normalized(item.context_quote or "")
            period = _normalized(submission.period_quote)
            if (
                not context
                or context not in normalized_text
                or period not in context
                or quote not in context
                or unit_quote not in context
            ):
                raise ValueError(
                    f"{name}: one retained metric context must bind the period, full metric row and units."
                )
            if context.index(period) > context.index(quote):
                raise ValueError(f"{name}: a later period header cannot verify an earlier metric.")
            if contexts is not None and context not in contexts:
                raise ValueError(
                    f"{name}: context must match a complete source table or statement block."
                )
            if re.search(r"\bprior\b|\bprevious\b|\bcomparative\b|\blast year\b", context):
                raise ValueError(
                    f"{name}: comparative period context is ambiguous; use attested evidence."
                )
            dates = {
                date.fromisoformat(value) for value in re.findall(r"\b\d{4}-\d{2}-\d{2}\b", context)
            }
            allowed_dates = {
                submission.period_start,
                submission.period_end,
                submission.published_on,
            }
            if dates - allowed_dates:
                raise ValueError(f"{name}: metric context contains another reporting period.")
            if not any(
                re.search(r"\b" + re.escape(label) + r"\b", quote) for label in METRIC_LABELS[name]
            ):
                raise ValueError(f"{name}: citation does not identify the declared metric.")
            numbers = re.findall(
                r"(?<!\w)(?:\([+-]?\d[\d,]*(?:\.\d+)?\)|[+-]?(?:\d[\d,]*(?:\.\d+)?|\.\d+))(?!\w)",
                quote,
            )
            raw_number = numbers[0].replace(",", "") if len(numbers) == 1 else ""
            number = (
                -float(raw_number[1:-1])
                if raw_number.startswith("(")
                else float(raw_number)
                if raw_number
                else None
            )
            if number != item.value:
                raise ValueError(
                    f"{name}: metric quote must contain one unambiguous matching value."
                )
            if name in AMOUNT_METRICS | PER_SHARE_METRICS and not re.search(
                r"\bnpr\b|nepal(?:ese|i) rupees?", item.unit_quote, re.I
            ):
                raise ValueError(f"{name}: source must explicitly identify NPR currency.")
            if item.unit == "percent" and not (
                "%" in item.unit_quote or "percent" in item.unit_quote.casefold()
            ):
                raise ValueError(f"{name}: the source must explicitly identify percentage units.")
            if name in AMOUNT_METRICS:
                scales = set(re.findall(r"\b(thousand|million)s?\b", unit_quote))
                expected = {
                    "NPR": set(),
                    "NPR_thousands": {"thousand"},
                    "NPR_millions": {"million"},
                }[item.unit]
                if scales != expected:
                    raise ValueError(
                        f"{name}: the cited source units do not match the amount scale."
                    )
            if item.unit == "NPR_per_share" and not re.search(
                r"per (?:share|unit)", item.unit_quote, re.I
            ):
                raise ValueError(f"{name}: source must identify per-share/unit figures.")
            basis_present = item.basis in quote or (
                item.basis == "annualized" and "annualised" in quote
            )
            if item.basis != "reported" and not basis_present:
                raise ValueError(
                    f"{name}: annualized/TTM treatment must be stated in the metric citation."
                )
            if item.basis == "reported" and (
                "annualized" in quote or "annualised" in quote or "ttm" in quote
            ):
                raise ValueError(
                    f"{name}: citation basis differs from the declared reported basis."
                )
        values[name] = dict(
            value=item.value * UNIT_SCALE[item.unit],
            unit="NPR" if name in AMOUNT_METRICS else item.unit,
            reported_value=item.value,
            reported_unit=item.unit,
            quote=item.quote,
            unit_quote=item.unit_quote,
            basis=item.basis,
            context_quote=item.context_quote,
        )
    return values


def _evidence(submission, metrics, *, kind, now, digest=None, retrieved_at=None):
    identity = json.dumps(
        dict(
            symbol=submission.symbol,
            source_url=submission.source_url,
            period_start=submission.period_start.isoformat(),
            period_end=submission.period_end.isoformat(),
            period_basis=submission.period_basis,
            period_quote=submission.period_quote,
            published_on=submission.published_on.isoformat() if submission.published_on else None,
            publication_quote=submission.publication_quote,
            document_sha256=digest,
            metrics=metrics,
            verification_kind=kind,
        ),
        sort_keys=True,
    ).encode()
    return FinancialEvidence(
        evidence_id=hashlib.sha256(identity).hexdigest(),
        symbol=submission.symbol,
        source_url=submission.source_url,
        document_sha256=digest,
        period_start=submission.period_start,
        period_end=submission.period_end,
        period_basis=submission.period_basis,
        period_label=submission.period_quote,
        published_on=submission.published_on,
        publication_quote=submission.publication_quote,
        available_at=now,
        retrieved_at=retrieved_at,
        verified_at=now if kind == "matched_official_excerpt" else None,
        verification_kind=kind,
        metrics=metrics,
        notes=["Matched reported excerpts are document checks, not an independent financial audit."]
        if digest
        else ["Human-attested values have not been matched to a server-fetched official document."],
    )


def attest_statement(submission: StatementSubmission, *, now=None) -> FinancialEvidence:
    now = now or datetime.now(UTC)
    today = now.astimezone(NPT).date()
    if submission.period_end > today or (
        submission.published_on and submission.published_on > today
    ):
        raise ValueError("Financial evidence dates cannot be in the future.")
    return _evidence(
        submission, _metric_values(submission, None), kind="manual_attestation", now=now
    )


def fetch_official_document(
    source_url: str,
    symbol: str,
    *,
    settings: Settings,
    client=None,
    issuers=None,
) -> tuple[bytes, datetime]:
    """Retrieve a bounded document from a registered issuer or regulator host."""
    if not settings.online:
        raise ValueError("Online mode is required to fetch and match an official document.")
    issuers = issuers or TRUSTED_ISSUERS
    _public_url(source_url, symbol, issuers)
    engine = _OfficialEngine(settings, symbol, issuers, client)
    with BaseClient(settings, engine=engine, cache_raw=False) as transport:
        response = transport.fetch(source_url)
        if response.status_code != 200:
            raise ValueError("The issuer document did not return a successful response.")
        return engine.body, engine.retrieved_at


def archive_official_document(body: bytes, digest: str, archive_dir: Path | None) -> None:
    if archive_dir is None:
        return
    archive_dir.mkdir(parents=True, exist_ok=True)
    target = archive_dir / f"{digest}.source"
    if target.exists():
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise ValueError("The retained official document does not match its evidence hash.")
        return
    with tempfile.NamedTemporaryFile(dir=archive_dir, delete=False) as temporary:
        temporary.write(body)
        temporary_path = Path(temporary.name)
    try:
        temporary_path.replace(target)
    finally:
        temporary_path.unlink(missing_ok=True)


def verify_official_statement(
    submission: StatementSubmission,
    *,
    settings: Settings,
    client=None,
    issuers=None,
    archive_dir: Path | None = None,
) -> FinancialEvidence:
    issuers = issuers or TRUSTED_ISSUERS
    body, retrieved_at = fetch_official_document(
        submission.source_url, submission.symbol, settings=settings, client=client, issuers=issuers
    )
    text = _document_text(body)
    if body.startswith(b"%PDF"):
        rows = {_normalized(line) for line in text.splitlines() if line.strip()}
        contexts = None
    else:
        tree = HTMLParser(body.decode("utf-8", "strict"))
        rows = {_normalized(row.text(separator=" ")) for row in tree.css("tr,p,li,div")}
        contexts = {
            _normalized(node.text(separator=" ")) for node in tree.css("table,section,article,div")
        }
    today = retrieved_at.astimezone(NPT).date()
    if submission.period_end > today or (
        submission.published_on and submission.published_on > today
    ):
        raise ValueError("Statement dates cannot be in the future.")
    normalized_text = _normalized(text)
    if _normalized(issuers[submission.symbol][0]) not in normalized_text:
        raise ValueError("The fetched document does not identify the registered issuer.")
    if _normalized(submission.period_quote) not in normalized_text or not all(
        _date_in_text(d, submission.period_quote)
        for d in (submission.period_start, submission.period_end)
    ):
        raise ValueError(
            "Period evidence must identify both declared Gregorian dates in the fetched document."
        )
    if submission.published_on:
        citation = submission.publication_quote or ""
        if (
            _normalized(citation) not in normalized_text
            or not _date_in_text(submission.published_on, citation)
            or not re.search(r"\bpublished\b|\bpublication\b|\bissued\b", citation, re.I)
        ):
            raise ValueError(
                "An explicit publication-date citation must match the official document."
            )
    metrics = _metric_values(submission, text, rows=rows, contexts=contexts)
    digest = hashlib.sha256(body).hexdigest()
    archive_official_document(body, digest, archive_dir)
    return _evidence(
        submission,
        metrics,
        kind="matched_official_excerpt",
        now=datetime.now(UTC),
        digest=digest,
        retrieved_at=retrieved_at,
    )
