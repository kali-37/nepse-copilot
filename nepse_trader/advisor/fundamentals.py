"""Use dated public earnings/valuation data without inventing financial strength."""

from __future__ import annotations

import math
from datetime import date, datetime

LIMITATIONS = [
    "The verified items and missing metrics depend on each issuer's available documents.",
    "Provider snapshot dates record retrieval. Official evidence lists its reporting period separately.",
    "Dividend yield depends on the cash payout and market price.",
]


def is_mutual_fund(snapshot) -> bool:
    if snapshot is None:
        return False
    description = f"{snapshot.sector} {snapshot.company_name}".casefold().replace("-", " ")
    return "mutual fund" in description


def assess_fundamentals(
    snapshot,
    *,
    quote: float | None,
    snapshot_date: date | None,
    today: date,
    evidence=(),
    symbol: str | None = None,
    as_of: datetime | None = None,
) -> dict:
    from nepse_trader.advisor.financial_quality import financial_quality

    quality = financial_quality(snapshot, evidence, today=today, symbol=symbol, as_of=as_of)
    verified = quality.pop("effective_metrics")
    annual_eps = quality.pop("annual_eps")
    core_verified = all(name in verified for name in ("eps", "book_value"))
    provider_source = getattr(snapshot, "source_name", "") or "MeroLagani public snapshot"
    base = dict(
        asset_kind="mutual_fund" if is_mutual_fund(snapshot) else "stock",
        source="Official issuer document excerpts" if core_verified else provider_source,
        source_url=getattr(snapshot, "source_url", None),
        snapshot_date=snapshot_date.isoformat() if snapshot_date else None,
        reporting_period_end=(
            quality["verification"]["period_end"]
            if core_verified
            else getattr(snapshot, "reporting_period_end", None).isoformat()
            if getattr(snapshot, "reporting_period_end", None)
            else None
        ),
        eps=None,
        book_value=None,
        current_pe=None,
        current_pbv=None,
        indicative_price_eps=None,
        valuation_basis="unverified_provider_basis",
        basis_unverified=True,
        reasons=[],
        limitations=LIMITATIONS,
        **quality,
    )

    def finish(report):
        status = quality["verification"]["status"]
        failures = [check for check in quality["financial_checks"] if check["verdict"] == "fail"]
        cautions = [check for check in quality["financial_checks"] if check["verdict"] == "caution"]
        if status == "conflict":
            report.update(rating="incomplete", multiplier=0, needs_refresh=True)
            report["reasons"].append(
                "Conflicting same-period official evidence for "
                + ", ".join(quality["verification"]["conflicts"])
                + "; resolve the source conflict before new risk."
            )
        elif quality["quality_multiplier"] == 0 and failures:
            report.update(rating="unsupported", multiplier=0, needs_refresh=False)
        elif quality["quality_multiplier"] < 1 and report["multiplier"] > 0:
            report["multiplier"] = min(report["multiplier"], quality["quality_multiplier"])
            if report["rating"] == "supported":
                report["rating"] = "caution"
        for check in failures + cautions:
            report["reasons"].append(
                f"Verified {check['label']}: {check['value']:.2f} {check['unit'] or ''}. {check['reason']}"
            )
        if status != "matched_official_excerpt":
            report["reasons"].append(
                "Broader financial support remains "
                + status.replace("_", " ")
                + "; provider snapshots and human attestations are not independently matched official statements."
            )
        report["verified_eligibility"] = bool(
            report["verified_eligibility"] and report["multiplier"] > 0
        )
        return report

    if base["asset_kind"] == "mutual_fund":
        base.update(
            rating="fund_review",
            multiplier=0,
            needs_refresh=False,
            reasons=[
                "This is a mutual fund; company EPS, P/E and book-value rules do not establish its investment quality.",
                "Dated NAV, market discount/premium (where traded), fund terms, portfolio and distributions need fund-specific review.",
            ],
            limitations=[
                "Fund NAV, expense ratios, maturity/redemption terms and distribution history are not fully verified here.",
                "A missing exchange quote is not proof that a fund has lost value; valuation may require published NAV.",
                "Mutual funds are excluded from company-based buy and lower-risk screens.",
            ],
        )
        if "nav_per_unit" in verified:
            nav = verified["nav_per_unit"]["value"]
            base["verified_nav_per_unit"] = nav
            base["reasons"].append(
                f"Matched official NAV per unit: NPR {nav:.2f}, period {quality['verification']['period_end']}."
            )
            if quote and math.isfinite(quote) and quote > 0 and nav > 0:
                base["market_premium_discount_pct"] = (quote / nav - 1) * 100
        return finish(base)
    if not core_verified and (snapshot is None or snapshot_date is None or snapshot_date > today):
        return finish(
            {
                **base,
                "rating": "missing",
                "multiplier": 0,
                "needs_refresh": True,
                "reasons": ["No dated earnings/valuation snapshot is available."],
            }
        )
    if not core_verified and (today - snapshot_date).days > 90:
        return finish(
            {
                **base,
                "rating": "stale",
                "multiplier": 0,
                "needs_refresh": True,
                "reasons": [f"Financial snapshot {snapshot_date} is more than 90 days old."],
            }
        )
    eps = verified["eps"]["value"] if core_verified else snapshot.eps
    book = verified["book_value"]["value"] if core_verified else snapshot.book_value
    if any(value is None or not math.isfinite(value) for value in (eps, book)):
        return finish(
            {
                **base,
                "rating": "incomplete",
                "multiplier": 0,
                "needs_refresh": True,
                "reasons": ["EPS or book value is missing; financial support is unconfirmed."],
            }
        )
    base.update(eps=eps, book_value=book)
    if eps <= 0 or book <= 0:
        return finish(
            {
                **base,
                "rating": "unsupported",
                "multiplier": 0,
                "needs_refresh": False,
                "reasons": [
                    f"Reported EPS {eps:.2f} and book value {book:.2f} do not pass positive-earnings/equity checks."
                ],
            }
        )
    if quote is None or not math.isfinite(quote) or quote <= 0:
        return finish(
            {
                **base,
                "rating": "incomplete",
                "multiplier": 0,
                "needs_refresh": True,
                "reasons": ["A usable current quote is needed to assess valuation."],
            }
        )
    basis = (
        "verified_ttm_eps"
        if core_verified
        and (
            verified["eps"].get("basis") == "ttm"
            or quality["verification"]["period_basis"] == "ttm"
        )
        else "verified_annualized_eps"
        if core_verified and verified["eps"].get("basis") == "annualized"
        else "verified_annual_eps"
        if core_verified and annual_eps
        else "verified_quarterly_eps"
        if core_verified
        else "reported_annualized_eps"
        if getattr(snapshot, "eps_basis", "unknown") in ("annual", "annualized", "ttm")
        else "reported_quarterly_eps"
        if getattr(snapshot, "eps_basis", "unknown") == "quarterly"
        else "unverified_provider_basis"
    )
    ratio, pbv = quote / eps, quote / book
    comparable_pe = basis not in ("verified_quarterly_eps", "reported_quarterly_eps")
    pe = ratio if comparable_pe else None
    rating = (
        "supported"
        if (pe is None or pe <= 30) and pbv <= 3
        else "caution"
        if (pe is None or pe <= 45) and pbv <= 5
        else "expensive"
    )
    multiplier = {"supported": 1.0, "caution": 0.85, "expensive": 0.65}[rating]
    if not comparable_pe:
        rating = "caution" if rating == "supported" else rating
        multiplier = min(multiplier, 0.85)
    base.update(
        current_pe=round(pe, 2) if pe is not None else None,
        current_pbv=round(pbv, 2),
        indicative_price_eps=round(ratio, 2),
        valuation_basis=basis,
        basis_unverified=not (core_verified and annual_eps),
    )
    origin = (
        f"matched period ended {quality['verification']['period_end']}"
        if core_verified
        else f"provider snapshot {snapshot_date}"
    )
    reasons = [f"Positive EPS of NPR {eps:.2f} from {origin}."]
    if basis == "verified_annualized_eps":
        reasons.append("The issuer annualized interim EPS for its reported valuation ratio.")
    if comparable_pe:
        prefix = "Current P/E" if basis != "unverified_provider_basis" else "Indicative price/EPS"
        reasons.append(
            f"{prefix} {pe:.1f} and price/book {pbv:.2f}: "
            + (
                "within valuation screen limits."
                if rating == "supported"
                else "valuation raises caution; technical strength alone is insufficient."
            )
        )
    else:
        reasons.append(
            f"Current price/book {pbv:.2f}; quarterly EPS is not treated as annual EPS or multiplied into a guessed P/E."
        )
    if base["basis_unverified"]:
        reasons.append(
            "Annual/TTM EPS basis is unverified or unavailable; the price/EPS figure is indicative, not verified annual P/E."
        )
    return finish(
        {
            **base,
            "rating": rating,
            "multiplier": multiplier,
            "needs_refresh": False,
            "reasons": reasons,
        }
    )
