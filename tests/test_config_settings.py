"""Tests for the runtime Settings model (modes, LLM, budget, RAG, MeroShare).

These settings gate every new subsystem, so the defaults matter: a fresh install
with an empty environment must land in deterministic, zero-token, no-credential
territory.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from nepse_trader.config import Settings


def _settings(**overrides) -> Settings:
    """Build Settings without reading the developer's real .env."""
    return Settings(_env_file=None, **overrides)


class TestSafeDefaults:
    def test_analysis_mode_defaults_to_normal(self):
        assert _settings().analysis_mode == "normal"

    def test_meroshare_disabled_with_no_credentials(self):
        s = _settings()
        assert s.meroshare_enabled is False
        assert s.meroshare_dp_id == ""
        assert s.meroshare_username == ""
        assert s.meroshare_password == ""

    def test_no_llm_keys_by_default(self):
        s = _settings()
        assert s.openrouter_api_key == ""
        assert s.anthropic_api_key == ""

    def test_watchlist_empty_by_default(self):
        assert _settings().watchlist == []

    def test_budget_ceilings_are_positive(self):
        s = _settings()
        assert s.llm_max_calls_per_day > 0
        assert s.llm_max_tokens_per_day > 0
        assert s.llm_max_deep_passes_per_week > 0


class TestProviderChains:
    def test_bulk_prefers_free_models(self):
        """Bulk per-symbol work must not default to a paid provider."""
        assert _settings().llm_bulk_providers[0] == "openrouter"

    def test_synthesis_prefers_local_cli(self):
        """claude_cli runs under the user's subscription — no API billing."""
        assert _settings().llm_synthesis_providers[0] == "claude_cli"

    def test_openrouter_models_are_free_tier(self):
        for model in _settings().openrouter_models:
            assert model.endswith(":free"), model


class TestValidation:
    def test_rejects_unknown_analysis_mode(self):
        with pytest.raises(ValidationError):
            _settings(analysis_mode="magic")

    @pytest.mark.parametrize("value", ["ai", "AI", " ai "])
    def test_accepts_and_normalises_ai_mode(self, value: str):
        assert _settings(analysis_mode=value).analysis_mode == "ai"

    def test_watchlist_accepts_comma_separated_env_value(self):
        """Env vars are strings; a CSV watchlist must still parse to a list."""
        assert _settings(watchlist="NABIL, ADBL ,HDL").watchlist == ["NABIL", "ADBL", "HDL"]

    def test_watchlist_accepts_real_list(self):
        assert _settings(watchlist=["NABIL"]).watchlist == ["NABIL"]

    def test_models_accept_comma_separated_env_value(self):
        s = _settings(openrouter_models="a:free,b:free")
        assert s.openrouter_models == ["a:free", "b:free"]


class TestEnvOverride:
    def test_env_prefix_applies(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("NEPSE_ANALYSIS_MODE", "ai")
        monkeypatch.setenv("NEPSE_LLM_MAX_CALLS_PER_DAY", "7")
        s = _settings()
        assert s.analysis_mode == "ai"
        assert s.llm_max_calls_per_day == 7

    def test_online_can_be_disabled_via_env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("NEPSE_ONLINE", "false")
        assert _settings().online is False
