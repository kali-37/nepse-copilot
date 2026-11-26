"""Verified capital and loan-quality ratios from Nepal Rastra Bank reports."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import httpx

from nepse_trader.analysis.financial_evidence import (
    FinancialEvidence,
    _document_text,
    archive_official_document,
    fetch_official_document,
)
from nepse_trader.config import Settings

_NRB = {"NRB": ("Nepal Rastra Bank", frozenset({"www.nrb.org.np"}))}
_REPORT_BASE = "https://www.nrb.org.np/contents/uploads/2026/09/"
# The NMB filing for Asar End 2083 gives the exact Gregorian date of the
# report's Mid-July 2026 reference. NRB expresses these ratios as of that date.
_PERIOD_END = date(2026, 7, 16)
_FIELDS = (
    ("core_capital_pct", "CCAR"),
    ("capital_adequacy_pct", "CAR"),
    ("npl_pct", "NPL"),
)


@dataclass(frozen=True)
class _Report:
    title: str
    filename: str
    sha256: str
    period_label: str
    field_columns: tuple[int, int, int]
    cell_count: int
    issuer_symbols: dict[str, str]


_REPORTS = (
    _Report(
        title="Commercial Banks",
        filename="KFI-ASAR-END-2083-Provisional.pdf",
        sha256="0823f3d493f12342908a7bf4ee7d9ce4d51bef0319dc1262a639bd12377e4300",
        period_label="As on Asadh End, 2083 (Mid-July 2026)",
        field_columns=(2, 3, 13),
        cell_count=23,
        issuer_symbols={
            "Nepal Bank Limited": "NBL",
            "Agriculture Development Bank": "ADBL",
            "Nabil Bank Limited": "NABIL",
            "Nepal Investment Mega Bank Limited": "NIMB",
            "Standard Chartered Bank Nepal Limited": "SCB",
            "Himalayan Bank Limited": "HBL",
            "Nepal SBI Bank Limited": "SBI",
            "Everest Bank Limited": "EBL",
            "NIC ASIA Bank Limited": "NICA",
            "Machhapuchhre Bank Limited": "MBL",
            "Kumari Bank Limited": "KBL",
            "Laxmi Sunrise Bank Limited": "LSL",
            "Siddhartha Bank Limited": "SBL",
            "Global IME Bank Limited": "GBIME",
            "Citizens Bank International Limited": "CZBIL",
            "Prime Commercial Bank Limited": "PCBL",
            "NMB Bank Limited": "NMB",
            "Prabhu Bank Limited": "PRVU",
            "Sanima Bank Limited": "SANIMA",
        },
    ),
    _Report(
        title="Development Banks",
        filename="KFI_2083_Asar-B.pdf",
        sha256="ae385f1c711fa4f66b71362a56ebf0275850c24a83f1c2b5dad20107834a1bcb",
        period_label="As on Asar end, 2083 ( Mid July 2026)",
        field_columns=(4, 5, 13),
        cell_count=16,
        issuer_symbols={
            "Muktinath Bikas Bank Limited": "MNBBL",
            "Jyoti Bikas Bank Limited": "JBBL",
            "Garima Bikas Bank Limited": "GBBL",
            "Mahalaxmi Bikas Bank Limited": "MLBL",
            "Shine Resunga Development Bank Limited": "SHINE",
            "Lumbini Bikas Bank Limited": "LBBL",
            "Shangrila Development Bank Limited": "SADBL",
            "Kamana Sewa Bikas Bank Limited": "KSBBL",
            "Saptakoshi Development Bank Limited": "SAPDBL",
            "Excel Development Bank Limited": "EDBL",
            "Miteri Development Bank Limited": "MDB",
            "Sindhu Bikas Bank Limited": "SINDU",
            "Green Development Bank Limited": "GRDBL",
            "Corporate Development bank Limited": "CORBL",
            "Narayani Development Bank Limited": "NABBC",
        },
    ),
    _Report(
        title="Finance Companies",
        filename="KFI_2083_Asar_C.pdf",
        sha256="070474059bfd8ce0f0df0bb11295508ba270698fc883a983442a782a0c854e3c",
        period_label="As on Asar end, 2083 ( Mid July 2026)",
        field_columns=(4, 5, 13),
        cell_count=16,
        issuer_symbols={
            "Nepal Finance Limited": "NFS",
            "Gorkhas Finance Limited": "GUFL",
            "Goodwill Finance Limited": "GFCL",
            "Shree Investment & Finance Co. Limited": "SIFC",
            "Best Finance Company Limited": "BFC",
            "Progressive Finance Limited": "PROFL",
            "Janaki Finance Company Limited": "JFL",
            "Pokhara Finance Limited": "PFL",
            "Central Finance Limited": "CFCL",
            "Multipurpose Finance Limited": "MPFL",
            "Guheshwori Merchant Banking & Finance Limited": "GMFIL",
            "ICFC Finance Limited": "ICFC",
            "Manjushree Finance Limited": "MFIL",
            "Reliance Finance Limited": "RLFL",
        },
    ),
)
_ROW = re.compile(r"^\s*\d+\s+(?P<issuer>[^0-9]+?)\s+(?=[(+-]?\d)(?P<cells>.+)$")


def _read_ratios(report: _Report, text: str) -> dict[str, dict]:
    normalized = " ".join(text.split())
    title = f"Key Financial Indicators of {report.title} (Provisional)"
    if not all(
        marker in normalized for marker in ("Nepal Rastra Bank", title, report.period_label)
    ):
        raise ValueError(f"NRB {report.title}: report title or reporting period did not match.")
    results = {}
    for line in text.splitlines():
        row = _ROW.fullmatch(line)
        if row is None:
            continue
        issuer = " ".join(row["issuer"].split())
        symbol = report.issuer_symbols.get(issuer)
        if symbol is None:
            continue
        cells = row["cells"].split()
        if symbol in results or len(cells) != report.cell_count:
            raise ValueError(f"NRB {report.title}: unexpected or duplicated row for {symbol}.")
        metrics = {}
        for (name, label), column in zip(_FIELDS, report.field_columns, strict=True):
            raw = cells[column]
            if not re.fullmatch(r"[+-]?\d+\.\d{2}%?", raw):
                raise ValueError(f"NRB {report.title}: invalid {label} for {symbol}.")
            value = float(raw.rstrip("%"))
            if name == "npl_pct" and not 0 <= value <= 100:
                raise ValueError(f"NRB {report.title}: NPL out of range for {symbol}.")
            metrics[name] = dict(
                value=value,
                unit="percent",
                basis="reported",
                label=label,
                quote=" ".join(line.split()),
                reported_value=raw,
            )
        results[symbol] = metrics
    if missing := set(report.issuer_symbols.values()) - results.keys():
        raise ValueError(f"NRB {report.title}: missing rows for {', '.join(sorted(missing))}.")
    return results


def fetch_nrb_indicators(
    settings: Settings, *, archive_dir: Path | None = None, client: httpx.Client | None = None
) -> list[FinancialEvidence]:
    """Match and archive the reviewed provisional reports before returning a complete batch."""
    records = []
    for report in _REPORTS:
        url = _REPORT_BASE + report.filename
        body, retrieved_at = fetch_official_document(
            url, "NRB", settings=settings, issuers=_NRB, client=client
        )
        digest = hashlib.sha256(body).hexdigest()
        if digest != report.sha256 or not body.startswith(b"%PDF"):
            raise ValueError(
                f"NRB {report.title}: document changed. Review the revised publication before importing it."
            )
        ratios = _read_ratios(report, _document_text(body))
        archive_official_document(body, digest, archive_dir)
        verified_at = datetime.now(UTC)
        for symbol, metrics in ratios.items():
            identity = hashlib.sha256(f"nrb-indicators-v1:{symbol}:{digest}".encode()).hexdigest()
            records.append(
                FinancialEvidence(
                    evidence_id=identity,
                    symbol=symbol,
                    source_url=url,
                    document_sha256=digest,
                    period_start=_PERIOD_END,
                    period_end=_PERIOD_END,
                    period_basis="as_of",
                    period_label=report.period_label,
                    published_on=None,
                    available_at=verified_at,
                    retrieved_at=retrieved_at,
                    verified_at=verified_at,
                    verification_kind="matched_official_excerpt",
                    source_kind="regulator",
                    metrics=metrics,
                    notes=[
                        "Provisional Nepal Rastra Bank regulatory reporting. Issuer financial statements may use a different reporting basis."
                    ],
                )
            )
    return records
