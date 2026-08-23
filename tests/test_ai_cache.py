"""Tests for the LLM response cache.

Two properties carry this module:

* **The key is content, not provider.** Yesterday's answer must still be served
  when today's chain falls through to a different provider — that is what makes
  the daily run cheap. A key that included the model would silently stop caching
  the moment a free model rotated out.
* **Failures are never cached.** Caching an error would keep a five-minute
  provider outage alive for the whole TTL.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from nepse_trader.ai.cache import ResponseCache, cache_key
from nepse_trader.ai.providers import LLMResponse
from nepse_trader.config import Settings
from nepse_trader.storage import Storage


@pytest.fixture
def conn(tmp_path: Path):
    storage = Storage(tmp_path / "ai.db")
    yield storage._conn
    storage.close()


def _settings(**kw) -> Settings:
    base = {"_env_file": None}
    base.update(kw)
    return Settings(**base)


def _response(text: str = "the answer", **kw) -> LLMResponse:
    base = {
        "text": text,
        "provider": "openrouter",
        "model": "a:free",
        "prompt_tokens": 100,
        "completion_tokens": 20,
    }
    base.update(kw)
    return LLMResponse(**base)


def _age(conn, key: str, *, hours: float) -> None:
    """Backdate an entry so TTL behaviour is testable without waiting."""
    when = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
    conn.execute("UPDATE ai_cache SET created_at = ? WHERE cache_key = ?", (when, key))
    conn.commit()


class TestCacheKey:
    def test_same_content_gives_the_same_key(self):
        a = cache_key(task="t", prompt="p", system="s")
        b = cache_key(task="t", prompt="p", system="s")
        assert a == b

    def test_different_prompts_differ(self):
        assert cache_key(task="t", prompt="a") != cache_key(task="t", prompt="b")

    def test_different_tasks_differ(self):
        """A bulk note and a critique over the same text are different questions."""
        assert cache_key(task="note", prompt="p") != cache_key(task="critique", prompt="p")

    def test_system_prompt_is_part_of_the_key(self):
        assert cache_key(task="t", prompt="p", system="x") != cache_key(task="t", prompt="p")

    def test_field_boundaries_cannot_be_confused(self):
        """Concatenating fields without a separator would collide these two."""
        assert cache_key(task="ab", prompt="c") != cache_key(task="a", prompt="bc")


class TestGetPut:
    def test_miss_returns_none(self, conn):
        assert ResponseCache(conn, _settings()).get("nope") is None

    def test_round_trip(self, conn):
        cache = ResponseCache(conn, _settings())
        key = cache.key(task="note", prompt="p")
        assert cache.put(key, _response(), task="note")
        hit = cache.get(key)
        assert hit is not None
        assert hit.text == "the answer"
        assert hit.total_tokens == 120

    def test_a_hit_is_flagged_as_cached(self, conn):
        """The router uses this flag to keep cache hits out of the budget."""
        cache = ResponseCache(conn, _settings())
        key = cache.key(task="note", prompt="p")
        cache.put(key, _response(), task="note")
        assert cache.get(key).cached is True

    def test_provider_is_not_part_of_the_key(self, conn):
        """A claude answer must still be served when the chain picks openrouter."""
        cache = ResponseCache(conn, _settings())
        key = cache.key(task="note", prompt="p")
        cache.put(key, _response(provider="claude_cli", model="claude-opus-5"), task="note")
        hit = cache.get(cache.key(task="note", prompt="p"))
        assert hit is not None
        assert hit.provider == "claude_cli"  # recorded, so it stays auditable

    def test_failures_are_not_cached(self, conn):
        """An outage must not be remembered for a week."""
        cache = ResponseCache(conn, _settings())
        key = cache.key(task="note", prompt="p")
        assert cache.put(key, LLMResponse(error="503"), task="note") is False
        assert cache.get(key) is None

    def test_whitespace_only_text_is_not_cached(self, conn):
        cache = ResponseCache(conn, _settings())
        key = cache.key(task="note", prompt="p")
        assert cache.put(key, _response("   "), task="note") is False

    def test_rewriting_a_key_replaces_rather_than_duplicates(self, conn):
        cache = ResponseCache(conn, _settings())
        key = cache.key(task="note", prompt="p")
        cache.put(key, _response("first"), task="note")
        cache.put(key, _response("second"), task="note")
        assert cache.get(key).text == "second"
        assert cache.stats()["entries"] == 1


class TestTtl:
    def test_fresh_entry_is_served(self, conn):
        cache = ResponseCache(conn, _settings(), ttl_hours=168)
        key = cache.key(task="t", prompt="p")
        cache.put(key, _response(), task="t")
        _age(conn, key, hours=100)
        assert cache.get(key) is not None

    def test_expired_entry_is_a_miss(self, conn):
        cache = ResponseCache(conn, _settings(), ttl_hours=168)
        key = cache.key(task="t", prompt="p")
        cache.put(key, _response(), task="t")
        _age(conn, key, hours=200)
        assert cache.get(key) is None

    def test_zero_ttl_disables_reads_and_writes(self, conn):
        cache = ResponseCache(conn, _settings(), ttl_hours=0)
        assert cache.enabled is False
        key = cache.key(task="t", prompt="p")
        assert cache.put(key, _response(), task="t") is False
        assert cache.get(key) is None

    def test_ttl_comes_from_settings_by_default(self, conn):
        assert ResponseCache(conn, _settings(llm_cache_ttl_hours=24)).ttl_hours == 24

    def test_unreadable_timestamp_is_treated_as_stale(self, conn):
        """Better a wasted call than trusting a row we can't date."""
        cache = ResponseCache(conn, _settings())
        key = cache.key(task="t", prompt="p")
        cache.put(key, _response(), task="t")
        conn.execute("UPDATE ai_cache SET created_at = 'garbage' WHERE cache_key = ?", (key,))
        conn.commit()
        assert cache.get(key) is None


class TestPurge:
    def test_removes_only_expired_entries(self, conn):
        cache = ResponseCache(conn, _settings(), ttl_hours=168)
        old = cache.key(task="t", prompt="old")
        new = cache.key(task="t", prompt="new")
        cache.put(old, _response(), task="t")
        cache.put(new, _response(), task="t")
        _age(conn, old, hours=300)
        assert cache.purge_expired() == 1
        assert cache.get(new) is not None

    def test_disabled_cache_purges_everything(self, conn):
        writable = ResponseCache(conn, _settings(), ttl_hours=168)
        key = writable.key(task="t", prompt="p")
        writable.put(key, _response(), task="t")
        assert ResponseCache(conn, _settings(), ttl_hours=0).purge_expired() == 1


class TestStats:
    def test_empty_cache_reports_zero(self, conn):
        stats = ResponseCache(conn, _settings()).stats()
        assert stats["entries"] == 0
        assert stats["oldest"] is None

    def test_reports_size_and_ttl(self, conn):
        cache = ResponseCache(conn, _settings(), ttl_hours=48)
        cache.put(cache.key(task="t", prompt="p"), _response(), task="t")
        stats = cache.stats()
        assert stats == {
            **stats,
            "entries": 1,
            "ttl_hours": 48,
            "enabled": True,
        }
        assert stats["newest"]
