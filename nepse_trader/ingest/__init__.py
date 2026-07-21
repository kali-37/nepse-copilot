"""Ingestion subpackage: per-source clients that fetch PUBLIC market data."""

from nepse_trader.ingest.base import BaseClient, FetchResult, SourceClient

__all__ = ["BaseClient", "FetchResult", "SourceClient"]
