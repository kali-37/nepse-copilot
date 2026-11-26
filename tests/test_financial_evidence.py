"""Official value matching has explicit issuer, timing, period and unit boundaries."""

import hashlib
from dataclasses import replace
from datetime import UTC, date, datetime

import httpx
import pytest
from freezegun import freeze_time
from pydantic import ValidationError
from selectolax.parser import HTMLParser

from nepse_trader.advisor.financial_quality import financial_quality
from nepse_trader.advisor.fundamentals import assess_fundamentals
from nepse_trader.analysis.financial_evidence import (
    FinancialEvidence,
    StatementSubmission,
    attest_statement,
    verify_official_statement,
)
from nepse_trader.config import Settings
from nepse_trader.ingest import nrb_fundamentals
from nepse_trader.models import FundamentalData

NOW = datetime(2026, 11, 25, 10, tzinfo=UTC)
PERIOD = "2025-07-16 to 2026-07-15"
TABLE = f"""<table><caption>{PERIOD}</caption>
<tr><td>Units</td><td>NPR per share; amounts in NPR millions; ratios in percent</td></tr>
<tr><td>EPS</td><td>30.0</td></tr><tr><td>Book value</td><td>200.0</td></tr>
<tr><td>ROE</td><td>15.0</td></tr><tr><td>NPL</td><td>1.0</td></tr>
<tr><td>Capital adequacy ratio</td><td>13.0</td></tr>
<tr><td>Operating cash flow</td><td>(100.0)</td></tr>
</table>"""
HTML = f"<html><body><h1>Nabil Bank</h1><p>Published on 2026-08-15</p>{TABLE}</body></html>"
CONTEXT = HTMLParser(TABLE).css_first("table").text(separator=" ")


@pytest.fixture(autouse=True)
def evidence_clock():
    with freeze_time(NOW):
        yield


def request(**updates):
    raw = dict(
        symbol="NABIL",
        source_url="https://www.nabilbank.com/report.html",
        period_start="2025-07-16",
        period_end="2026-07-15",
        period_basis="annual",
        period_quote=PERIOD,
        published_on="2026-08-15",
        publication_quote="Published on 2026-08-15",
        metrics={
            "eps": dict(
                value=30,
                unit="NPR_per_share",
                quote="EPS 30.0",
                unit_quote="NPR per share",
                context_quote=CONTEXT,
            )
        },
    )
    raw.update(updates)
    return StatementSubmission.model_validate(raw)


@pytest.fixture
def transport(monkeypatch):
    monkeypatch.setattr(
        "socket.getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443))]
    )
    return httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=HTML.encode()))
    )


def settings(**updates):
    return Settings(
        _env_file=None, online=True, respect_robots=False, min_request_interval=0, **updates
    )


def test_server_fetched_document_binds_value_period_units_and_archive(transport, tmp_path):
    with freeze_time(NOW):
        evidence = verify_official_statement(
            request(), settings=settings(), client=transport, archive_dir=tmp_path
        )
    assert evidence.verification_kind == "matched_official_excerpt"
    assert evidence.document_sha256 == hashlib.sha256(HTML.encode()).hexdigest()
    assert evidence.available_at == NOW and evidence.published_on == date(2026, 8, 15)
    assert evidence.metrics["eps"]["value"] == 30
    assert (tmp_path / (evidence.document_sha256 + ".source")).read_bytes() == HTML.encode()


def test_manual_attestation_cannot_claim_official_verification():
    evidence = attest_statement(request(), now=NOW)
    assert evidence.verification_kind == "manual_attestation" and evidence.verified_at is None
    assert evidence.document_sha256 is None
    with pytest.raises(ValidationError):
        request(verified=True)


@pytest.mark.parametrize(
    "url",
    [
        "http://www.nabilbank.com/report",
        "https://www.nabilbank.com.evil.test/report",
        "https://user:password@www.nabilbank.com/report",
        "https://www.nabilbank.com:8000/report",
        "https://127.0.0.1/report",
    ],
)
def test_unregistered_or_unsafe_references_cannot_be_verified(url, transport):
    with pytest.raises(ValueError):
        verify_official_statement(request(source_url=url), settings=settings(), client=transport)


def test_private_dns_is_refused_before_request(monkeypatch, transport):
    monkeypatch.setattr("socket.getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("127.0.0.1", 443))])
    with pytest.raises(ValueError, match="public addresses"):
        verify_official_statement(request(), settings=settings(), client=transport)


def test_redirects_are_refused_without_following_destination(transport):
    calls = []

    def redirect(r):
        calls.append(str(r.url))
        return httpx.Response(302, headers={"Location": "http://127.0.0.1/internal"})

    client = httpx.Client(transport=httpx.MockTransport(redirect), follow_redirects=True)
    with pytest.raises(ValueError, match="redirects"):
        verify_official_statement(request(), settings=settings(), client=client)
    assert calls == ["https://www.nabilbank.com/report.html"]


def test_large_response_is_bounded_before_reading(transport):
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, headers={"content-length": "4000001"}, content=b"")
        )
    )
    with pytest.raises(ValueError, match="download limit"):
        verify_official_statement(request(), settings=settings(), client=client)


def test_false_metric_or_unit_citations_do_not_become_verified(transport):
    for value, unit_quote in [(31, "NPR per share"), (30, "USD per share")]:
        with pytest.raises(ValueError):
            verify_official_statement(
                request(
                    metrics={
                        "eps": dict(
                            value=value,
                            unit="NPR_per_share",
                            quote="EPS 30.0",
                            unit_quote=unit_quote,
                            context_quote=CONTEXT,
                        )
                    }
                ),
                settings=settings(),
                client=transport,
            )


def test_old_metric_and_current_period_in_different_blocks_are_not_associated(transport):
    old = "<table><caption>2024-07-16 to 2025-07-15</caption><tr><td>Units</td><td>NPR per share</td></tr><tr><td>EPS</td><td>30.0</td></tr></table>"
    current = f"<table><caption>{PERIOD}</caption><tr><td>Units</td><td>NPR per share</td></tr><tr><td>EPS</td><td>40.0</td></tr></table>"
    html = (
        f"<body><h1>Nabil Bank</h1><p>Published on 2026-08-15</p><div>{old}{current}</div></body>"
    )
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=html.encode()))
    )
    combined = HTMLParser(html).css_first("div").text(separator=" ")
    with pytest.raises(ValueError, match="later period|another reporting period"):
        verify_official_statement(
            request(
                metrics={
                    "eps": dict(
                        value=30,
                        unit="NPR_per_share",
                        quote="EPS 30.0",
                        unit_quote="NPR per share",
                        context_quote=combined,
                    )
                }
            ),
            settings=settings(),
            client=client,
        )


def test_cropped_comparative_row_cannot_verify_a_selected_value(transport):
    html = HTML.replace("<td>30.0</td>", "<td>30.0 20.0</td>")
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=html.encode()))
    )
    with pytest.raises(ValueError, match="complete source row"):
        verify_official_statement(request(), settings=settings(), client=client)


def test_accounting_negative_and_explicit_amount_scale_are_preserved(transport):
    with freeze_time(NOW):
        evidence = verify_official_statement(
            request(
                metrics={
                    "operating_cash_flow": dict(
                        value=-100,
                        unit="NPR_millions",
                        quote="Operating cash flow (100.0)",
                        unit_quote="amounts in NPR millions",
                        context_quote=CONTEXT,
                    )
                }
            ),
            settings=settings(),
            client=transport,
        )
    assert evidence.metrics["operating_cash_flow"]["value"] == -100000000


def test_npr_amount_cannot_ignore_reported_scale(transport):
    with pytest.raises(ValueError, match="amount scale"):
        verify_official_statement(
            request(
                metrics={
                    "operating_cash_flow": dict(
                        value=-100,
                        unit="NPR",
                        quote="Operating cash flow (100.0)",
                        unit_quote="amounts in NPR millions",
                        context_quote=CONTEXT,
                    )
                }
            ),
            settings=settings(),
            client=transport,
        )


def evidence(
    values,
    *,
    available=NOW,
    period_end=date(2026, 7, 15),
    basis="annual",
    kind="matched_official_excerpt",
):
    metrics = {
        name: dict(
            value=value,
            unit="percent"
            if name.endswith("_pct")
            else "NPR_per_share"
            if name in ("eps", "book_value")
            else "NPR",
            basis="reported",
        )
        for name, value in values.items()
    }
    return FinancialEvidence(
        evidence_id=str(values),
        symbol="NABIL",
        source_url="https://www.nabilbank.com/report",
        document_sha256="a" * 64 if kind == "matched_official_excerpt" else None,
        period_start=date(period_end.year - 1, period_end.month, period_end.day),
        period_end=period_end,
        period_basis=basis,
        published_on=None,
        available_at=available,
        retrieved_at=available,
        verified_at=available if kind == "matched_official_excerpt" else None,
        verification_kind=kind,
        metrics=metrics,
        notes=[],
    )


def snapshot(**updates):
    return FundamentalData(
        symbol="NABIL", sector="Commercial Banks", eps=30, book_value=200, **updates
    )


def test_bank_coverage_and_same_period_roe_npl_capital_checks_are_verified():
    record = evidence(dict(eps=30, book_value=200, roe_pct=15, npl_pct=1, capital_adequacy_pct=13))
    report = assess_fundamentals(
        snapshot(), quote=500, snapshot_date=NOW.date(), today=NOW.date(), evidence=[record]
    )
    assert report["verified_eligibility"] and report["valuation_basis"] == "verified_annual_eps"
    assert report["verification"]["missing_metrics"] == []
    assert report["current_pe"] == round(500 / 30, 2)


def test_missing_required_bank_metrics_are_unknown_not_good():
    report = financial_quality(
        snapshot(), [evidence(dict(eps=30, book_value=200))], today=NOW.date()
    )
    assert not report["verified_eligibility"]
    assert {"roe_pct", "npl_pct", "capital_adequacy_pct"} <= set(
        report["verification"]["missing_metrics"]
    )
    assert all(
        check["value"] is None
        for check in report["financial_checks"]
        if check["verdict"] == "unknown"
    )


def test_future_availability_and_manual_attestation_do_not_leak_into_verified_history():
    future = NOW.replace(day=26)
    for record in (
        evidence(dict(eps=30, book_value=200), available=future),
        evidence(dict(eps=30, book_value=200), kind="manual_attestation"),
    ):
        report = financial_quality(snapshot(), [record], today=NOW.date())
        assert not report["verified_eligibility"] and report["effective_metrics"] == {}


def test_refreshing_an_old_report_does_not_make_its_period_fresh():
    report = financial_quality(
        snapshot(),
        [evidence(dict(eps=30, book_value=200), period_end=date(2023, 7, 15))],
        today=NOW.date(),
    )
    assert report["verification"]["status"] == "stale" and not report["verified_eligibility"]


def test_conflicting_same_period_official_values_block_without_averaging():
    report = assess_fundamentals(
        snapshot(),
        quote=500,
        snapshot_date=NOW.date(),
        today=NOW.date(),
        evidence=[evidence(dict(eps=30, book_value=200)), evidence(dict(eps=31, book_value=200))],
    )
    assert report["verification"]["status"] == "conflict" and report["multiplier"] == 0
    assert report["verification"]["conflicts"] == ["eps"]


def test_verified_loss_blocks_new_risk_even_when_provider_eps_looks_positive():
    report = assess_fundamentals(
        snapshot(),
        quote=500,
        snapshot_date=NOW.date(),
        today=NOW.date(),
        evidence=[evidence(dict(net_income=-100, total_equity=200))],
    )
    assert report["rating"] == "unsupported" and report["multiplier"] == 0
    assert any("Net income" in line for line in report["reasons"])


def test_verified_bank_risk_weakens_evidence_and_strict_eligibility():
    report = assess_fundamentals(
        snapshot(),
        quote=500,
        snapshot_date=NOW.date(),
        today=NOW.date(),
        evidence=[
            evidence(dict(eps=30, book_value=200, roe_pct=15, npl_pct=8, capital_adequacy_pct=8))
        ],
    )
    assert (
        report["rating"] == "caution"
        and report["multiplier"] <= 0.7
        and not report["verified_eligibility"]
    )


def test_known_quarterly_eps_is_not_guessed_into_annual_pe():
    report = assess_fundamentals(
        snapshot(eps_basis="quarterly"), quote=500, snapshot_date=NOW.date(), today=NOW.date()
    )
    assert report["current_pe"] is None and report["valuation_basis"] == "reported_quarterly_eps"
    assert report["indicative_price_eps"] == round(500 / 30, 2)


def test_legacy_provider_ratio_remains_explicitly_indicative():
    report = assess_fundamentals(snapshot(), quote=500, snapshot_date=NOW.date(), today=NOW.date())
    assert report["current_pe"] == round(500 / 30, 2) and report["basis_unverified"]
    assert (
        report["valuation_basis"] == "unverified_provider_basis"
        and not report["verified_eligibility"]
    )


def test_same_day_intraday_assessment_requires_evidence_to_be_available():
    record = evidence(dict(eps=30, book_value=200, roe_pct=15, npl_pct=1, capital_adequacy_pct=13))
    before = financial_quality(snapshot(), [record], today=NOW.date(), as_of=NOW.replace(hour=9))
    after = financial_quality(snapshot(), [record], today=NOW.date(), as_of=NOW)
    assert before["verification"]["status"] == "unverified"
    assert after["verified_eligibility"]


def test_nrb_indicators_bind_exact_issuer_row_and_retained_document(
    transport, monkeypatch, tmp_path
):
    pdf = b"%PDF-1.4 synthetic regulator report"
    digest = hashlib.sha256(pdf).hexdigest()
    report = replace(
        nrb_fundamentals._REPORTS[2],
        issuer_symbols={"Janaki Finance Company Limited": "JFL"},
        sha256=digest,
    )
    layout = (
        "Nepal Rastra Bank\n"
        f"Key Financial Indicators of {report.title} (Provisional)\n"
        f"{report.period_label}\n"
        "7 Janaki Finance Company Limited 690,473 (252,716) (252,716) 4,116,117 -6.14% -6.14% "
        "2,315,337 2,162,341 98.57% 37.94% 30.60% 9.80% 4.60% 61.55% 3.78% 27.83%\n"
    )
    monkeypatch.setattr(nrb_fundamentals, "_REPORTS", (report,))
    monkeypatch.setattr(nrb_fundamentals, "_document_text", lambda body: layout)
    with httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=pdf))
    ) as client:
        with freeze_time(NOW):
            records = nrb_fundamentals.fetch_nrb_indicators(
                settings(), archive_dir=tmp_path, client=client
            )
    [record] = records
    assert record.symbol == "JFL" and record.source_kind == "regulator"
    assert record.period_basis == "as_of" and record.period_end == date(2026, 7, 16)
    assert record.metrics["npl_pct"]["value"] == 61.55
    assert record.metrics["capital_adequacy_pct"]["value"] == -6.14
    assert record.document_sha256 == digest and record.available_at == NOW
    assert (tmp_path / f"{digest}.source").read_bytes() == pdf
    assessment = financial_quality(None, records, today=NOW.date(), symbol="JFL", as_of=NOW)
    assert assessment["quality_multiplier"] == 0
    assert assessment["verification"]["period_start"] is None
    assert assessment["verification"]["source_documents"][0]["source_kind"] == "regulator"


def test_changed_nrb_bytes_fail_before_document_parsing(transport, monkeypatch):
    monkeypatch.setattr(
        nrb_fundamentals, "_document_text", lambda *args: pytest.fail("Unexpected PDF parsing")
    )
    with pytest.raises(ValueError, match="document changed"):
        nrb_fundamentals.fetch_nrb_indicators(settings(), client=transport)


def test_same_period_regulator_ratios_preserve_issuer_valuation_and_both_sources():
    period_end = date(2026, 7, 16)
    issuer = evidence(
        dict(eps=30, book_value=200, roe_pct=15, npl_pct=1.1, capital_adequacy_pct=13),
        period_end=period_end,
    )
    regulator = FinancialEvidence.model_validate(
        {
            **evidence(
                dict(npl_pct=1.2, capital_adequacy_pct=13.1), period_end=period_end
            ).model_dump(),
            "source_kind": "regulator",
            "source_url": "https://www.nrb.org.np/investor-report.pdf",
            "period_basis": "as_of",
            "period_start": period_end,
        }
    )
    assessment = assess_fundamentals(
        snapshot(),
        quote=500,
        snapshot_date=NOW.date(),
        today=NOW.date(),
        evidence=[issuer, regulator],
        as_of=NOW,
    )
    assert (
        assessment["verified_eligibility"]
        and assessment["valuation_basis"] == "verified_annual_eps"
    )
    assert {
        document["source_kind"] for document in assessment["verification"]["source_documents"]
    } == {"issuer", "regulator"}
    npl = next(check for check in assessment["financial_checks"] if check["metric"] == "npl_pct")
    assert npl["value"] == 1.2 and npl["source_kind"] == "regulator"
