"""Same-period financial checks over dated, independently stored evidence."""

from __future__ import annotations

from datetime import datetime, time

from nepse_trader.analysis.financial_evidence import NPT, TRUSTED_ISSUERS, FinancialEvidence

_REGULATORY_METRICS = frozenset({"npl_pct", "capital_adequacy_pct", "core_capital_pct"})
LABELS = {
    "eps": "Earnings per share",
    "book_value": "Book value per share",
    "roe_pct": "Return on equity",
    "npl_pct": "Non-performing loans",
    "capital_adequacy_pct": "Capital adequacy",
    "core_capital_pct": "Core capital",
    "operating_cash_flow": "Operating cash flow",
    "net_income": "Net income",
    "total_debt": "Total debt",
    "total_equity": "Total equity",
    "debt_equity": "Debt/equity",
    "cash_conversion": "Operating cash/profit",
    "nav_per_unit": "NAV per unit",
    "expense_ratio_pct": "Expense ratio",
}


def financial_quality(snapshot, evidence, *, today, symbol=None, as_of=None) -> dict:
    if as_of is not None and (as_of.tzinfo is None or as_of.utcoffset() is None):
        raise ValueError("Financial assessment time requires a UTC offset.")
    cutoff = datetime.combine(today, time.max, tzinfo=NPT)
    if as_of is not None:
        cutoff = min(cutoff, as_of)
    symbol = snapshot.symbol if snapshot else symbol
    records = [
        item if isinstance(item, FinancialEvidence) else FinancialEvidence.model_validate(item)
        for item in evidence or ()
    ]
    if symbol is None and len({record.symbol for record in records}) > 1:
        raise ValueError("Financial evidence must be scoped to one issuer.")
    symbol = symbol or (records[0].symbol if records else None)
    visible = []
    for record in records:
        if symbol and record.symbol != symbol:
            continue
        if (
            record.available_at > cutoff
            or (record.verified_at and record.verified_at > cutoff)
            or record.period_end > today
        ):
            continue
        visible.append(record)
    matched = [r for r in visible if r.verification_kind == "matched_official_excerpt"]
    latest_end = max((record.period_end for record in matched), default=None)
    issuer = [r for r in matched if r.source_kind == "issuer" and r.period_end == latest_end]
    anchor = min(issuer, key=lambda r: (r.period_start, r.period_basis), default=None)
    if anchor:
        issuer = [
            r
            for r in issuer
            if (r.period_start, r.period_basis) == (anchor.period_start, anchor.period_basis)
        ]
    regulator = [r for r in matched if r.source_kind == "regulator" and r.period_end == latest_end]
    selected = issuer + regulator
    anchor = anchor or (regulator[0] if regulator else None)
    sector = (snapshot.sector if snapshot else "").casefold()
    if not sector and (
        regulator or (symbol in TRUSTED_ISSUERS and "bank" in TRUSTED_ISSUERS[symbol][0].casefold())
    ):
        sector = "bank"
    profile = (
        "fund"
        if "mutual fund" in sector
        else "bank"
        if any(v in sector for v in ("bank", "finance"))
        else "unsupported_financial"
        if "insurance" in sector
        else "company"
    )
    required = (
        ["eps", "book_value", "roe_pct", "npl_pct", "capital_adequacy_pct"]
        if profile == "bank"
        else ["nav_per_unit", "expense_ratio_pct"]
        if profile == "fund"
        else [
            "eps",
            "book_value",
            "net_income",
            "operating_cash_flow",
            "total_debt",
            "total_equity",
        ]
    )
    if profile == "unsupported_financial":
        required += ["sector_specific_solvency_evidence"]
    by_scope, conflicts = {}, []
    for record in selected:
        scoped = by_scope.setdefault(record.source_kind, {})
        for name, metric in record.metrics.items():
            if record.source_kind == "regulator" and name not in _REGULATORY_METRICS:
                continue
            if name in scoped and any(
                scoped[name].get(k) != metric.get(k) for k in ("value", "unit", "basis")
            ):
                conflicts.append(name)
            else:
                scoped[name] = {**metric, "source_kind": record.source_kind}
    values = {**by_scope.get("issuer", {}), **by_scope.get("regulator", {})}
    age_limit = 550 if anchor and anchor.period_basis in {"annual", "ttm"} else 180
    stale = bool(anchor and (today - anchor.period_end).days > age_limit)
    if regulator and not stale and (today - latest_end).days > 180:
        # A recent annual filing can still be useful after its spot bank ratios age out.
        values = by_scope.get("issuer", {})
    notes = [
        "Matched excerpts retain their reporting source and period. Provider snapshots and attestations have separate status."
    ]
    if regulator:
        notes.append(
            "Nepal Rastra Bank figures are provisional. Recent regulatory ratios take precedence over issuer ratios for the same date."
        )
    status = (
        "conflict"
        if conflicts
        else "stale"
        if stale
        else "matched_official_excerpt"
        if selected
        else "attested_only"
        if visible
        else "unverified"
    )
    usable = values if status == "matched_official_excerpt" else {}
    checks = []
    multiplier = 0.0 if status == "conflict" else 1.0

    def check(name, verdict, note, value=None, unit=None):
        metric = usable.get(name)
        checks.append(
            dict(
                metric=name,
                label=LABELS.get(name, name),
                value=value if value is not None else metric.get("value") if metric else None,
                unit=unit or (metric.get("unit") if metric else None),
                source_status="matched_official_excerpt"
                if metric or value is not None
                else "missing",
                verdict=verdict,
                source_kind=metric.get("source_kind") if metric else None,
                reason=note,
            )
        )

    for name in required:
        if name not in usable:
            check(
                name,
                "unknown",
                "Comparable verified financial evidence is unavailable; missing is not zero or a pass.",
            )
    for name in ("eps", "book_value", "net_income", "total_equity"):
        if name in usable:
            bad = usable[name]["value"] <= 0
            check(
                name,
                "fail" if bad else "pass",
                "Reported earnings/equity must be positive for new risk.",
            )
            if bad:
                multiplier = 0.0
    if "roe_pct" in usable:
        roe = usable["roe_pct"]["value"]
        bad = roe <= 0
        check(
            "roe_pct",
            "fail" if bad else "pass",
            "Reported ROE is negative/non-positive."
            if bad
            else "Reported ROE is positive; it is not a return forecast.",
        )
        if bad:
            multiplier = min(multiplier, 0.65)
    if profile == "bank":
        for name, threshold, note in (
            (
                "npl_pct",
                5,
                "Research screen raises caution above 5% NPL; this is not a regulatory compliance verdict.",
            ),
            (
                "capital_adequacy_pct",
                11,
                "Research screen raises caution below 11% capital adequacy; requirements vary and are not verified here.",
            ),
            (
                "core_capital_pct",
                0,
                "Non-positive reported core capital fails the financial screen.",
            ),
        ):
            if name in usable:
                amount = usable[name]["value"]
                failed = name != "npl_pct" and amount <= 0
                caution = amount > threshold if name == "npl_pct" else amount < threshold
                check(name, "fail" if failed else "caution" if caution else "pass", note)
                if failed:
                    multiplier = 0.0
                elif caution:
                    multiplier = min(multiplier, 0.7)
    elif profile == "company":
        if "operating_cash_flow" in usable:
            caution = usable["operating_cash_flow"]["value"] <= 0
            check(
                "operating_cash_flow",
                "caution" if caution else "pass",
                "Negative/non-positive operating cash flow weakens earnings support; one period does not prove insolvency.",
            )
            if caution:
                multiplier = min(multiplier, 0.65)
        if (
            all(name in usable for name in ("total_debt", "total_equity"))
            and usable["total_equity"]["value"] > 0
        ):
            ratio = usable["total_debt"]["value"] / usable["total_equity"]["value"]
            check(
                "debt_equity",
                "caution" if ratio > 2 else "pass",
                "Explicit borrowing/equity research screen; bank deposits and total liabilities are not substituted for debt.",
                value=ratio,
                unit="ratio",
            )
            if ratio > 2:
                multiplier = min(multiplier, 0.7)
        if (
            all(name in usable for name in ("operating_cash_flow", "net_income"))
            and usable["net_income"]["value"] > 0
        ):
            ratio = usable["operating_cash_flow"]["value"] / usable["net_income"]["value"]
            check(
                "cash_conversion",
                "caution" if ratio < 0.5 else "pass",
                "Same-period operating cash/profit below 0.5 raises earnings-quality caution.",
                value=ratio,
                unit="ratio",
            )
            if ratio < 0.5:
                multiplier = min(multiplier, 0.75)
    annual_eps = usable.get("eps")
    annual_eps = bool(
        annual_eps
        and (
            anchor.period_basis in {"annual", "ttm"}
            or annual_eps.get("basis") in {"annualized", "ttm"}
        )
    )
    missing = [name for name in required if name not in usable]
    if usable.get("eps") and not annual_eps:
        missing.append("annual_or_ttm_eps_basis")
    return dict(
        verification=dict(
            status=status,
            period_start=anchor.period_start.isoformat()
            if anchor and anchor.period_basis != "as_of"
            else None,
            period_end=anchor.period_end.isoformat() if anchor else None,
            period_basis=anchor.period_basis if anchor else None,
            period_label=anchor.period_label if anchor else None,
            available_at=max(r.available_at for r in selected).isoformat() if selected else None,
            matched_metrics=sorted(usable),
            missing_metrics=missing,
            conflicts=sorted(set(conflicts)),
            source_documents=[
                dict(
                    evidence_id=r.evidence_id,
                    source_url=r.source_url,
                    source_kind=r.source_kind,
                    period_label=r.period_label,
                    document_sha256=r.document_sha256,
                    available_at=r.available_at.isoformat(),
                    published_on=r.published_on.isoformat() if r.published_on else None,
                    verified_at=r.verified_at.isoformat() if r.verified_at else None,
                )
                for r in selected
            ],
            note=" ".join(notes),
        ),
        sector_profile=profile,
        financial_checks=checks,
        quality_multiplier=multiplier,
        verified_eligibility=status == "matched_official_excerpt"
        and profile != "fund"
        and not missing
        and multiplier >= 1,
        effective_metrics=usable,
        annual_eps=annual_eps,
    )
