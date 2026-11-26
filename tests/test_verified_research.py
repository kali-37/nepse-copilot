"""Issuer evidence flows from storage into offline advice and research coverage."""

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from freezegun import freeze_time

from nepse_trader.analysis.financial_evidence import FinancialEvidence
from nepse_trader.config import Settings
from nepse_trader.models import FundamentalData, ReconciledPrice
from nepse_trader.storage import Storage
from nepse_trader.storage.research import evidence_by_symbol, save_financial_evidence
from nepse_trader.web.api import _state, app

AVAILABLE = datetime(2026, 11, 24, 10, tzinfo=UTC)


def official_evidence(evidence_id="test-evidence", *, symbol="NABIL", eps=-2):
    return FinancialEvidence(
        evidence_id=evidence_id,
        symbol=symbol,
        source_url="https://www.nabilbank.com/report",
        document_sha256="a" * 64,
        period_start=date(2025, 7, 17),
        period_end=date(2026, 7, 16),
        period_basis="annual",
        published_on=None,
        available_at=AVAILABLE,
        retrieved_at=AVAILABLE,
        verified_at=AVAILABLE,
        verification_kind="matched_official_excerpt",
        metrics={
            "eps": {"value": eps, "unit": "NPR_per_share", "basis": "reported"},
            "book_value": {"value": 200, "unit": "NPR_per_share", "basis": "reported"},
        },
        notes=[],
    )


def test_repeat_verification_preserves_first_availability_and_conflicts_rollback(tmp_path):
    with Storage(tmp_path / "db.sqlite") as storage:
        original = official_evidence()
        assert save_financial_evidence(storage, [original])["inserted"] == 1
        assert evidence_by_symbol(storage, as_of=AVAILABLE - timedelta(seconds=1)) == {}
        later = AVAILABLE + timedelta(days=1)
        repeated = original.model_copy(
            update={
                "available_at": later,
                "verified_at": later,
                "retrieved_at": later,
            }
        )
        assert save_financial_evidence(storage, [repeated])["inserted"] == 0
        with pytest.raises(ValueError, match="cannot be rewritten"):
            save_financial_evidence(
                storage,
                [
                    official_evidence("another", symbol="EBL"),
                    official_evidence(eps=10),
                ],
            )
        visible = evidence_by_symbol(storage, as_of=AVAILABLE)
        assert set(visible) == {"NABIL"}
        assert visible["NABIL"][0]["available_at"] == AVAILABLE.isoformat()


@freeze_time("2026-11-24 11:00:00")
def test_matched_issuer_loss_overrides_profitable_provider_snapshot(tmp_path):
    settings = Settings(_env_file=None, db_path=tmp_path / "db.sqlite", online=False)
    with Storage(settings.db_path) as storage:
        storage.upsert_fundamental(
            FundamentalData(symbol="NABIL", sector="Commercial Banks", eps=30, book_value=200),
            AVAILABLE.date(),
        )
        storage.upsert_reconciled(
            [
                ReconciledPrice(
                    symbol="NABIL", business_date=AVAILABLE.date(), close=500, confidence=1
                ),
            ]
        )
        save_financial_evidence(storage, [official_evidence()])
        _state.update(storage=storage, settings=settings)
        with TestClient(app) as client:
            response = client.get("/api/decisions/fundamentals/nabil")
            assert response.status_code == 200
            assessment = response.json()
            assert assessment["quote"] == 500 and assessment["eps"] == -2
            assert assessment["multiplier"] == 0 and assessment["rating"] == "unsupported"
            verification = assessment["verification"]
            assert verification["source_documents"][0]["document_sha256"] == "a" * 64
            coverage = client.get("/api/research/financial-evidence").json()
            assert coverage["provider_symbols"] == coverage["matched_symbols"] == 1
            assert coverage["complete_symbols"] == 0
            assert coverage["symbols"][0]["metrics"] == ["book_value", "eps"]
