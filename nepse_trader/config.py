"""Configuration loading: app settings + source endpoint map + cost model.

Settings come from environment (prefixed NEPSE_) and optional .env. The source
endpoint map and the Nepal cost/tax model are loaded from YAML in config/ so
they can be tuned as HAR captures reveal real endpoints, without code changes.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"


class Settings(BaseSettings):
    """Runtime settings. Override via env vars (NEPSE_*) or .env."""

    model_config = SettingsConfigDict(env_prefix="NEPSE_", env_file=".env", extra="ignore")

    db_path: Path = DATA_DIR / "nepse.db"
    raw_cache_dir: Path = DATA_DIR / "raw"
    # Root of the run-log tree. Every run writes a timestamped file under
    # log_dir/<component>/. Override with NEPSE_LOG_DIR (tests redirect it so
    # unit runs don't pollute the real logs/ tree).
    log_dir: Path = PROJECT_ROOT / "logs"
    request_timeout: float = 20.0
    max_retries: int = 3
    # Politeness: minimum seconds between requests to the SAME host.
    min_request_interval: float = 1.5
    user_agent: str = "nepse-trader/0.1 (+public-data-aggregator; respects robots & ToS)"
    # Enabled ingestion sources (by SourceName value).
    enabled_sources: list[str] = Field(
        default_factory=lambda: ["sharesansar", "chukul", "nepse_official"]
    )
    sources_file: Path = CONFIG_DIR / "sources.yaml"
    cost_model_file: Path = CONFIG_DIR / "cost_model.yaml"
    # Reconciliation: relative tolerance for two sources to "agree" on a price.
    price_agreement_tolerance: float = 0.005  # 0.5%
    # HTML parse backend: "auto" (Scrapling if installed, else selectolax),
    # "scrapling", or "selectolax". Scrapling adds adaptive, layout-drift-resilient
    # element matching; selectolax is the always-available fallback.
    parse_engine: str = "auto"
    # HTTP fetch backend: "httpx" (default) or "scrapling" (curl_cffi). The
    # Scrapling engine is used in PLAIN mode only — no stealth/anti-bot/Cloudflare
    # bypass — for public sources that don't gate access.
    fetch_engine: str = "httpx"
    # Optional curl_cffi TLS impersonation profile for the scrapling engine
    # (e.g. "chrome"). Empty = no impersonation (honest, plain client).
    scrapling_impersonate: str = ""


class EndpointSpec(BaseModel):
    name: str
    method: str = "GET"
    url: str
    params: dict[str, Any] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    confidence: str = "medium"
    notes: str = ""


class SourceSpec(BaseModel):
    name: str
    base_url: str = ""
    access_method: str = "html_scrape"
    requires_auth: bool = False
    enabled: bool = True
    rate_limit_seconds: float | None = None
    endpoints: dict[str, EndpointSpec] = Field(default_factory=dict)
    notes: str = ""


class SourcesConfig(BaseModel):
    sources: dict[str, SourceSpec] = Field(default_factory=dict)

    def get(self, name: str) -> SourceSpec | None:
        return self.sources.get(name)


class CommissionSlab(BaseModel):
    min_amount: float
    max_amount: float | None = None
    rate_percent: float


class CostModel(BaseModel):
    """Nepal equity transaction cost + tax model. Values are tunable via YAML."""

    broker_commission_slabs: list[CommissionSlab]
    broker_min_commission: float = 10.0
    sebon_fee_percent: float = 0.015
    dp_charge_per_scrip: float = 25.0
    cgt_short_percent: float = 7.5  # individual, held < 365 days
    cgt_long_percent: float = 5.0  # individual, held >= 365 days
    cgt_institutional_percent: float = 10.0
    settlement_cycle: str = "T+2"
    currency: str = "NPR"


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def load_sources(path: Path | None = None) -> SourcesConfig:
    settings = get_settings()
    raw = _read_yaml(path or settings.sources_file)
    sources: dict[str, SourceSpec] = {}
    for key, spec in (raw.get("sources") or {}).items():
        endpoints = {
            ep_key: EndpointSpec(name=ep_key, **ep_val)
            for ep_key, ep_val in (spec.get("endpoints") or {}).items()
        }
        spec = {**spec, "endpoints": endpoints, "name": spec.get("name", key)}
        sources[key] = SourceSpec(**spec)
    return SourcesConfig(sources=sources)


def load_cost_model(path: Path | None = None) -> CostModel:
    settings = get_settings()
    raw = _read_yaml(path or settings.cost_model_file)
    if not raw:
        # Sensible defaults if YAML absent; real values populated by research.
        return CostModel(
            broker_commission_slabs=[
                CommissionSlab(min_amount=0, max_amount=50_000, rate_percent=0.40),
                CommissionSlab(min_amount=50_000, max_amount=500_000, rate_percent=0.37),
                CommissionSlab(min_amount=500_000, max_amount=2_000_000, rate_percent=0.34),
                CommissionSlab(min_amount=2_000_000, max_amount=10_000_000, rate_percent=0.30),
                CommissionSlab(min_amount=10_000_000, max_amount=None, rate_percent=0.27),
            ]
        )
    slabs = [CommissionSlab(**s) for s in raw.get("broker_commission_slabs", [])]
    return CostModel(**{**raw, "broker_commission_slabs": slabs})
