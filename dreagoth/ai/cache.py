"""SQLite cache for AI-generated content — same content never generated twice."""

from __future__ import annotations

import atexit
import sqlite3
import hashlib
from pathlib import Path

_DB_PATH = Path(__file__).parent.parent.parent / "saves" / "ai_cache.db"
_MAX_CACHE_ENTRIES = 5000


class AICache:
    """Cache AI responses keyed by content type + context hash."""

    def __init__(self) -> None:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(_DB_PATH))
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self._conn.commit()

    @staticmethod
    def _make_key(content_type: str, context: str) -> str:
        h = hashlib.sha256(f"{content_type}:{context}".encode()).hexdigest()[:16]
        return f"{content_type}:{h}"

    def get(self, content_type: str, context: str) -> str | None:
        key = self._make_key(content_type, context)
        row = self._conn.execute(
            "SELECT content FROM cache WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else None

    def put(self, content_type: str, context: str, content: str) -> None:
        key = self._make_key(content_type, context)
        self._conn.execute(
            "INSERT OR REPLACE INTO cache (key, content) VALUES (?, ?)",
            (key, content),
        )
        self._conn.commit()
        self._maybe_prune()

    def _maybe_prune(self) -> None:
        """Delete oldest entries if cache exceeds max size."""
        count = self._conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
        if count > _MAX_CACHE_ENTRIES:
            self._conn.execute(
                "DELETE FROM cache WHERE key IN ("
                "  SELECT key FROM cache ORDER BY created_at ASC LIMIT ?"
                ")",
                (count - _MAX_CACHE_ENTRIES,),
            )
            self._conn.commit()

    def close(self) -> None:
        self._conn.close()


ai_cache = AICache()
atexit.register(ai_cache.close)
