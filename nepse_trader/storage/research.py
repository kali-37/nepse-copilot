"""Persistent issuer evidence and model validation records."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from collections.abc import Iterable

    from nepse_trader.analysis.financial_evidence import FinancialEvidence
    from nepse_trader.storage.db import Storage


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def save_financial_evidence(storage: Storage, records: Iterable[FinancialEvidence]) -> dict:
    inserted = 0
    stored_ids = []
    with storage._tx() as conn:
        conn.execute("BEGIN IMMEDIATE")
        for evidence in records:
            payload = evidence.model_dump(mode="json")
            available = evidence.available_at.astimezone(UTC).isoformat()
            payload["available_at"] = available
            stored_ids.append(evidence.evidence_id)
            existing = conn.execute(
                "SELECT payload FROM financial_evidence WHERE evidence_id=?",
                (evidence.evidence_id,),
            ).fetchone()
            if existing:
                stored = json.loads(existing[0])
                # Preserve first availability on repeated verification of identical facts.
                metadata = {"available_at", "retrieved_at", "verified_at", "notes"}
                if any(
                    stored.get(key) != value
                    for key, value in payload.items()
                    if key not in metadata
                ):
                    raise ValueError(
                        "A financial evidence ID cannot be rewritten with different content."
                    )
                continue
            conn.execute(
                """INSERT INTO financial_evidence
                (evidence_id,symbol,period_end,published_on,available_at,verification_kind,payload)
                VALUES(?,?,?,?,?,?,?)""",
                (
                    evidence.evidence_id,
                    evidence.symbol,
                    evidence.period_end.isoformat(),
                    evidence.published_on.isoformat() if evidence.published_on else None,
                    available,
                    evidence.verification_kind,
                    _json(payload),
                ),
            )
            inserted += 1
        if inserted:
            storage._bump_market_revision(conn)
    return {"inserted": inserted, "evidence_ids": stored_ids}


def evidence_by_symbol(
    storage: Storage, *, as_of: datetime, symbol: str | None = None
) -> dict[str, list[dict]]:
    cutoff = as_of.astimezone(UTC).isoformat()
    if symbol is None:
        rows = storage._conn.execute(
            """SELECT symbol,payload FROM financial_evidence WHERE available_at<=?
            ORDER BY symbol,period_end DESC,available_at DESC,evidence_id""",
            (cutoff,),
        )
    else:
        rows = storage._conn.execute(
            """SELECT symbol,payload FROM financial_evidence WHERE available_at<=? AND symbol=?
            ORDER BY period_end DESC,available_at DESC,evidence_id""",
            (cutoff, symbol),
        )
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["symbol"], []).append(json.loads(row["payload"]))
    return grouped


def save_model(storage: Storage, artifact: dict, summary: dict) -> dict:
    from nepse_trader.analysis.model_validation import verify_model_artifact

    verify_model_artifact(artifact)
    model_id, horizon, as_of = (
        artifact["model_id"],
        artifact["horizon_days"],
        artifact["completed_through"],
    )
    summary = {**summary, "id": model_id, "horizon_days": horizon, "data_as_of": as_of}
    with storage._tx() as conn:
        conn.execute(
            """INSERT INTO trained_models(model_id,horizon_days,created_at,data_as_of,artifact,summary)
            VALUES(?,?,?,?,?,?) ON CONFLICT(model_id) DO NOTHING""",
            (
                model_id,
                horizon,
                datetime.now(UTC).isoformat(),
                as_of,
                _json(artifact),
                _json(summary),
            ),
        )
    return model_record(storage, model_id)


_MODEL_SUMMARIES = """SELECT m.model_id,m.created_at,m.summary,d.activated_at FROM trained_models m
    LEFT JOIN model_deployments d ON d.model_id=m.model_id"""


def _activation_block(
    horizon: int, data_as_of: str, last_test_label: str, policy: str, *, today: date
) -> str | None:
    from nepse_trader.analysis.model_validation import label_policy_fingerprint

    age = (today - date.fromisoformat(last_test_label)).days
    if today < date.fromisoformat(data_as_of) or not 0 <= age <= 90:
        return "Model evaluation is outside the deployment window. Run a new evaluation."
    if policy != label_policy_fingerprint(horizon):
        return "The trade simulation policy has changed. Run a new evaluation."
    return None


def _model_summary(row) -> dict:
    summary = json.loads(row["summary"])
    passed = summary["gate"]["passed"]
    status = "candidate" if passed else "rejected"
    block = (
        _activation_block(
            summary["horizon_days"],
            summary["data_as_of"],
            summary["boundaries"]["test_end"],
            summary["diagnostics"]["policy_fingerprint"],
            today=datetime.now(ZoneInfo("Asia/Kathmandu")).date(),
        )
        if passed
        else "Held-out validation blocked activation."
    )
    return {
        **summary,
        "created_at": row["created_at"],
        "status": "active" if row["activated_at"] else status,
        "advisory_eligible": block is None,
        "advisory_block_reason": block,
    }


def model_record(storage: Storage, model_id: str) -> dict:
    row = storage._conn.execute(_MODEL_SUMMARIES + " WHERE m.model_id=?", (model_id,)).fetchone()
    if row is None:
        raise ValueError("Model version not found.")
    return _model_summary(row)


def list_models(storage: Storage, *, limit: int = 20) -> dict:
    rows = storage._conn.execute(
        _MODEL_SUMMARIES + " ORDER BY d.activated_at IS NULL,m.created_at DESC,m.model_id LIMIT ?",
        (max(2, limit),),
    ).fetchall()
    models = [_model_summary(row) for row in rows]
    active = {
        str(model["horizon_days"]): model["id"] for model in models if model["status"] == "active"
    }
    return {"models": models, "active": active}


def active_models(storage: Storage, *, eligible_on: date | None = None) -> dict[int, dict]:
    active = {}
    rows = storage._conn.execute(
        """SELECT m.horizon_days,m.artifact FROM trained_models m
        JOIN model_deployments d ON d.model_id=m.model_id AND d.horizon_days=m.horizon_days"""
    )
    for row in rows:
        horizon, artifact = row["horizon_days"], json.loads(row["artifact"])
        if eligible_on is None or (
            artifact["promotion_gate"]["passed"]
            and not _activation_block(
                horizon,
                artifact["completed_through"],
                artifact["boundaries"]["test"]["label_end"],
                artifact["policy_fingerprint"],
                today=eligible_on,
            )
        ):
            active[horizon] = artifact
    return active


def deploy_model(storage: Storage, model_id: str, *, today: date) -> dict:
    from nepse_trader.analysis.model_validation import verify_model_artifact

    with storage._tx() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT horizon_days,artifact FROM trained_models WHERE model_id=?", (model_id,)
        ).fetchone()
        if row is None:
            raise ValueError("Model version not found.")
        artifact = json.loads(row["artifact"])
        verify_model_artifact(artifact)
        gate = artifact["promotion_gate"]
        if not gate["passed"]:
            raise ValueError("Held-out validation blocked activation. " + " ".join(gate["reasons"]))
        horizon = row["horizon_days"]
        block = _activation_block(
            horizon,
            artifact["completed_through"],
            artifact["boundaries"]["test"]["label_end"],
            artifact["policy_fingerprint"],
            today=today,
        )
        if block:
            raise ValueError(block)
        updated = conn.execute(
            """INSERT INTO model_deployments(horizon_days,model_id,activated_at) VALUES(?,?,?)
            ON CONFLICT(horizon_days) DO UPDATE SET
              model_id=excluded.model_id,activated_at=excluded.activated_at
            WHERE model_deployments.model_id<>excluded.model_id""",
            (horizon, model_id, datetime.now(UTC).isoformat()),
        ).rowcount
        if updated:
            _record_deployment(storage, conn, horizon, model_id, "activated")
    return model_record(storage, model_id)


def disable_model(storage: Storage, horizon_days: int) -> None:
    with storage._tx() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT model_id FROM model_deployments WHERE horizon_days=?",
            (horizon_days,),
        ).fetchone()
        if row:
            conn.execute("DELETE FROM model_deployments WHERE horizon_days=?", (horizon_days,))
            _record_deployment(storage, conn, horizon_days, row[0], "disabled")


def _record_deployment(storage, conn, horizon_days, model_id, action) -> None:
    conn.execute(
        "INSERT INTO model_deployment_events(horizon_days,model_id,action,created_at) VALUES(?,?,?,?)",
        (horizon_days, model_id, action, datetime.now(UTC).isoformat()),
    )
    storage._bump_market_revision(conn)
