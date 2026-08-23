"""Content-hash response cache, so a re-run costs nothing.

The key is a hash of *what was asked* — task label, prompt, system prompt — and
deliberately **not** the provider or model. Yesterday's answer stays usable when
today's chain falls through to a different provider, which is exactly what makes
the daily run cheap. Which provider produced a cached row is recorded as metadata
and shown by ``ai budget``, so a cached answer is still auditable.

TTL comes from ``llm_cache_ttl_hours`` (default one week, matching the weekly deep
pass). Setting it to 0 disables the cache entirely — reads miss and writes are
dropped, rather than the cache silently answering forever.
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
from datetime import UTC, datetime, timedelta

from nepse_trader.ai.providers import LLMResponse
from nepse_trader.config import Settings, get_settings

log = logging.getLogger("nepse_trader.ai.cache")


def cache_key(*, task: str, prompt: str, system: str = "") -> str:
    """Stable key for a request's content.

    The parts are joined with a separator that cannot appear in the field values,
    so ``task="a", prompt="b"`` and ``task="a\\x00b", prompt=""`` cannot collide.
    """
    digest = hashlib.sha256()
    for part in (task, system, prompt):
        digest.update(part.encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


class ResponseCache:
    """SQLite-backed cache over the ``ai_cache`` table."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        settings: Settings | None = None,
        *,
        ttl_hours: int | None = None,
    ) -> None:
        self._conn = conn
        self._conn.row_factory = sqlite3.Row
        self.settings = settings or get_settings()
        self.ttl_hours = self.settings.llm_cache_ttl_hours if ttl_hours is None else ttl_hours

    @property
    def enabled(self) -> bool:
        return self.ttl_hours > 0

    def key(self, *, task: str, prompt: str, system: str = "") -> str:
        return cache_key(task=task, prompt=prompt, system=system)

    def get(self, key: str) -> LLMResponse | None:
        """A fresh cached response, or None on a miss or an expired entry."""
        if not self.enabled:
            return None
        row = self._conn.execute(
            "SELECT * FROM ai_cache WHERE cache_key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        if self._expired(row["created_at"]):
            log.debug("cache entry %s expired", key[:12])
            return None
        return LLMResponse(
            text=row["response"],
            provider=row["provider"],
            model=row["model"],
            prompt_tokens=int(row["prompt_tokens"]),
            completion_tokens=int(row["completion_tokens"]),
            cached=True,
        )

    def put(self, key: str, response: LLMResponse, *, task: str) -> bool:
        """Store a successful response. Returns whether it was written.

        Failures are never cached: a cached error would keep a transient provider
        outage alive for a week.
        """
        if not self.enabled or not response.ok:
            return False
        self._conn.execute(
            """INSERT OR REPLACE INTO ai_cache
               (cache_key, task, provider, model, response,
                prompt_tokens, completion_tokens, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                key,
                task,
                response.provider,
                response.model,
                response.text,
                response.prompt_tokens,
                response.completion_tokens,
                datetime.now(UTC).isoformat(),
            ),
        )
        self._conn.commit()
        return True

    def purge_expired(self) -> int:
        """Delete entries past the TTL. Returns how many went."""
        if not self.enabled:
            cur = self._conn.execute("DELETE FROM ai_cache")
        else:
            cutoff = (datetime.now(UTC) - timedelta(hours=self.ttl_hours)).isoformat()
            cur = self._conn.execute("DELETE FROM ai_cache WHERE created_at < ?", (cutoff,))
        self._conn.commit()
        return cur.rowcount

    def stats(self) -> dict:
        """Size and age of the cache, for ``ai budget``."""
        row = self._conn.execute(
            "SELECT COUNT(*) AS n, MIN(created_at) AS oldest, MAX(created_at) AS newest "
            "FROM ai_cache"
        ).fetchone()
        return {
            "entries": int(row["n"]),
            "oldest": row["oldest"],
            "newest": row["newest"],
            "ttl_hours": self.ttl_hours,
            "enabled": self.enabled,
        }

    def _expired(self, created_at: str) -> bool:
        try:
            created = datetime.fromisoformat(created_at)
        except (TypeError, ValueError):
            return True  # unreadable timestamp: treat as stale rather than trust it
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        return datetime.now(UTC) - created > timedelta(hours=self.ttl_hours)
