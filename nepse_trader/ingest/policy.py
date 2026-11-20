"""Persistent source cooldowns and incremental ingestion decisions."""

from __future__ import annotations

import time
from collections import Counter
from datetime import date

from nepse_trader.config import Settings
from nepse_trader.models import PriceBar
from nepse_trader.storage import Storage


class IngestPolicy:
    def __init__(self, storage: Storage, settings: Settings):
        self.storage = storage
        self.settings = settings

    def skip_reason(self, source: str, business_date: date | None, *, force: bool = False) -> str | None:
        if not self.settings.online:
            return "Offline mode: downloads are disabled."
        if force:
            return None
        until = self.storage.source_cooldown(source)
        if until > time.time():
            return f"Source cooling down for {int(until - time.time()) + 1}s after repeated failures."
        if business_date is not None and self.storage.source_date_ingested(source, business_date):
            return "This source and date are already ingested; use force to refresh."
        return None

    def record(self, source: str, bars: list[PriceBar], requested_date: date | None) -> list[str]:
        counts = Counter(bar.business_date for bar in bars)
        recent = self.storage.recent_source_counts(source)
        warnings = []
        for business_date, count in counts.items():
            if recent and count < sum(recent) / len(recent) * 0.5:
                warnings.append(f"{source}: only {count} rows for {business_date}, below half the recent average.")
            self.storage.log_ingest(source, "prices", business_date, count, "ok", "; ".join(warnings))
        if not counts:
            self.storage.log_ingest(source, "prices", requested_date, 0, "empty", "No prices returned.")
        self.storage.record_source_result(source, bool(bars), self.settings.circuit_failure_threshold,
                                          self.settings.circuit_cooldown_seconds)
        return warnings
