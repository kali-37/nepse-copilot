"""Configuration loading: app settings + source endpoint map + cost model.

Settings come from environment (prefixed NEPSE_) and optional .env. The source
endpoint map and the Nepal cost/tax model are loaded from YAML in config/ so
they can be tuned as HAR captures reveal real endpoints, without code changes.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"


class Settings(BaseSettings):
    """Runtime settings. Override via env vars (NEPSE_*) or .env."""

    # The .env path is absolute on purpose: a relative "*.env*" resolves against
    # the *current working directory*, so launching the API from a subdirectory
    # silently dropped every NEPSE_* value — MeroShare credentials included —
    # and the integration reported itself disabled instead of misconfigured.
    model_config = SettingsConfigDict(
        env_prefix="NEPSE_", env_file=PROJECT_ROOT / ".env", extra="ignore",
        hide_input_in_errors=True
    )

    db_path: Path = DATA_DIR / "nepse.db"
    raw_cache_dir: Path = DATA_DIR / "raw"
    # Root of the run-log tree. Every run writes a timestamped file under
    # log_dir/<component>/. Override with NEPSE_LOG_DIR (tests redirect it so
    # unit runs don't pollute the real logs/ tree).
    log_dir: Path = PROJECT_ROOT / "logs"
    log_format: Literal["text", "json"] = "text"
    request_timeout: float = 20.0
    max_retries: int = 3
    # Politeness: minimum seconds between requests to the SAME host.
    min_request_interval: float = 1.5
    respect_robots: bool = True
    raw_cache_retention_days: int = Field(30, ge=0)
    circuit_failure_threshold: int = Field(3, ge=1)
    circuit_cooldown_seconds: int = Field(900, ge=0)
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

    # ------------------------------------------------------------- run modes
    # "normal" = deterministic only (indicators, backtested edge, cost model).
    # "ai"     = the same deterministic numbers PLUS LLM narrative/ranking.
    # AI mode never alters an entry, stop, target or size — see analysis_mode
    # handling in nepse_trader/advisor/.
    analysis_mode: str = "normal"
    # Offline forbids every network call: no ingestion, no web retrieval, no
    # LLM provider that needs the network (cached LLM output is still used).
    online: bool = True
    # Symbols the advisor looks at when none are given explicitly. Empty list
    # means "whatever is in the DB", capped by advisor_max_symbols.
    watchlist: list[str] = Field(default_factory=list)
    advisor_max_symbols: int = 25

    # ------------------------------------------------------------------- LLM
    # Provider chain, tried in order per task tier. Known names:
    # "claude_cli" (local `claude -p` subprocess — no API billing),
    # "anthropic"  (ANTHROPIC_API_KEY via the Messages API),
    # "openrouter" (OPENROUTER_API_KEY, free models for bulk work).
    llm_bulk_providers: list[str] = Field(default_factory=lambda: ["openrouter", "claude_cli"])
    llm_synthesis_providers: list[str] = Field(
        default_factory=lambda: ["claude_cli", "anthropic", "openrouter"]
    )
    # Free OpenRouter models used for per-symbol bulk passes, tried in order.
    openrouter_models: list[str] = Field(
        default_factory=lambda: [
            "meta-llama/llama-3.3-70b-instruct:free",
            "qwen/qwen-2.5-72b-instruct:free",
            "google/gemma-2-9b-it:free",
        ]
    )
    openrouter_api_key: str = Field(default="", repr=False, exclude=True)
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # Path to the Claude Code CLI used by the claude_cli provider.
    claude_cli_path: str = "claude"
    claude_cli_model: str = ""  # empty = whatever the CLI defaults to
    anthropic_api_key: str = Field(default="", repr=False, exclude=True)
    anthropic_model: str = "claude-opus-5"
    llm_timeout: float = 180.0

    # -------------------------------------------------------- token budgeting
    # Hard ceilings. When a ceiling is hit the advisor degrades to normal mode
    # with a visible banner rather than erroring or silently truncating.
    llm_max_calls_per_day: int = 40
    llm_max_tokens_per_day: int = 400_000
    # The weekly deep pass (full evidence, synthesis model) runs at most this
    # many times per ISO week; daily runs reuse its cached thesis.
    llm_max_deep_passes_per_week: int = 2
    # Reuse a cached LLM response when the evidence hash matches and the entry
    # is younger than this. 0 disables the cache.
    llm_cache_ttl_hours: int = 168  # one week

    # ------------------------------------------------------------------- RAG
    rag_max_documents: int = 8  # documents per retrieval
    rag_max_evidence_chars: int = 12_000  # token-proxy ceiling on an evidence pack
    # Live web retrieval (online mode only). Empty list disables it.
    rag_web_search_urls: list[str] = Field(
        default_factory=lambda: ["https://duckduckgo.com/html/?q={query}"]
    )
    rag_enable_web: bool = True

    # ------------------------------------------------------------- MeroShare
    # Reading YOUR OWN account with YOUR OWN credentials. Read-only: holdings,
    # WACC and transaction history. No IPO/ASBA application, no order placement.
    # Credentials come from env / .env / optional OS keyring and are never
    # logged, never written to the DB. See nepse_trader/meroshare/credentials.py.
    meroshare_enabled: bool = False
    meroshare_base_url: str = "https://webbackend.cdsc.com.np/api"
    meroshare_dp_id: str = Field(default="", repr=False, exclude=True)
    meroshare_username: str = Field(default="", repr=False, exclude=True)
    meroshare_password: str = Field(default="", repr=False, exclude=True)
    # Read the password from the OS keyring instead of env (service/user below).
    meroshare_use_keyring: bool = False
    meroshare_keyring_service: str = "nepse-trader-meroshare"

    @field_validator("analysis_mode")
    @classmethod
    def _check_mode(cls, v: str) -> str:
        mode = v.strip().lower()
        if mode not in ("normal", "ai"):
            raise ValueError("analysis_mode must be 'normal' or 'ai'")
        return mode

    @field_validator("watchlist", "openrouter_models", mode="before")
    @classmethod
    def _split_csv(cls, v: Any) -> Any:
        """Accept a comma-separated string from env for list-valued settings."""
        if isinstance(v, str) and not v.strip().startswith("["):
            return [part.strip() for part in v.split(",") if part.strip()]
        return v


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
