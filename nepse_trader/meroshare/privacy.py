"""Privacy-safe identifiers for persisted MeroShare mirror rows.

The CDSC demat/BOID is useful while a client request is in memory, but it is an
account identifier and must not be retained in the local SQLite database.  A
domain-separated SHA-256 fingerprint keeps multiple demats distinct for
idempotent upserts without making the raw identifier recoverable from a normal
database dump.  The final four digits are retained separately for a human
friendly, non-unique display hint.
"""

from __future__ import annotations

import hashlib

_NAMESPACE = b"nepse-trader/meroshare/demat/v1:"


def _normalise(value: object) -> str:
    return str(value or "").strip()


def demat_fingerprint(value: object) -> str:
    """Return a deterministic, non-reversible storage key for a demat value."""
    normalised = _normalise(value)
    if not normalised:
        return ""
    return hashlib.sha256(_NAMESPACE + normalised.encode("utf-8")).hexdigest()


def demat_last4(value: object) -> str:
    """Return only the final four characters for masked display."""
    normalised = _normalise(value)
    return normalised[-4:] if normalised else ""


__all__ = ["demat_fingerprint", "demat_last4"]
