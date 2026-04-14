"""
memory/research_memory.py — SQLite-backed memory layer.

Responsibilities:
  • Deduplicate articles (by URL hash)
  • Deduplicate GitHub repos
  • Store past queries with timestamps
  • Track repo star growth over time
  • Persist full report JSON
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from config import DB_PATH

logger = logging.getLogger(__name__)

# ── Schema ────────────────────────────────────────────────────────────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS queries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    topic       TEXT NOT NULL,
    queried_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS articles (
    url_hash    TEXT PRIMARY KEY,
    url         TEXT NOT NULL,
    title       TEXT,
    summary     TEXT,
    topic       TEXT,
    scraped_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS github_repos (
    repo_full_name  TEXT NOT NULL,
    stars           INTEGER,
    forks           INTEGER,
    open_issues     INTEGER,
    latest_release  TEXT,
    topic           TEXT,
    recorded_at     TEXT NOT NULL,
    PRIMARY KEY (repo_full_name, recorded_at)
);

CREATE TABLE IF NOT EXISTS reports (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    topic       TEXT NOT NULL,
    report_json TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
"""


class ResearchMemory:
    """Async context manager wrapping an aiosqlite connection."""

    def __init__(self, db_path: str | Path = DB_PATH) -> None:
        self._db_path = str(db_path)
        self._conn: aiosqlite.Connection | None = None

    # ── Lifecycle ──────────────────────────────────────────────────────────────
    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(_SCHEMA)
        await self._conn.commit()
        logger.debug("ResearchMemory connected: %s", self._db_path)

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def __aenter__(self) -> "ResearchMemory":
        await self.connect()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    # ── Helpers ───────────────────────────────────────────────────────────────
    @staticmethod
    def _url_hash(url: str) -> str:
        return hashlib.sha256(url.encode()).hexdigest()[:16]

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _ensure_connected(self) -> None:
        if self._conn is None:
            raise RuntimeError("ResearchMemory not connected — call connect() first.")

    # ── Queries ───────────────────────────────────────────────────────────────
    async def log_query(self, topic: str) -> None:
        self._ensure_connected()
        await self._conn.execute(  # type: ignore[union-attr]
            "INSERT INTO queries (topic, queried_at) VALUES (?, ?)",
            (topic, self._now()),
        )
        await self._conn.commit()  # type: ignore[union-attr]

    async def get_query_history(self, limit: int = 20) -> list[dict]:
        self._ensure_connected()
        async with self._conn.execute(  # type: ignore[union-attr]
            "SELECT topic, queried_at FROM queries ORDER BY id DESC LIMIT ?", (limit,)
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    # ── Articles ──────────────────────────────────────────────────────────────
    async def is_article_seen(self, url: str) -> bool:
        self._ensure_connected()
        h = self._url_hash(url)
        async with self._conn.execute(  # type: ignore[union-attr]
            "SELECT 1 FROM articles WHERE url_hash = ?", (h,)
        ) as cur:
            return await cur.fetchone() is not None

    async def save_article(
        self,
        url: str,
        title: str = "",
        summary: str = "",
        topic: str = "",
    ) -> None:
        self._ensure_connected()
        h = self._url_hash(url)
        await self._conn.execute(  # type: ignore[union-attr]
            """INSERT OR IGNORE INTO articles
               (url_hash, url, title, summary, topic, scraped_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (h, url, title, summary, topic, self._now()),
        )
        await self._conn.commit()  # type: ignore[union-attr]

    async def get_articles_for_topic(self, topic: str, limit: int = 30) -> list[dict]:
        self._ensure_connected()
        async with self._conn.execute(  # type: ignore[union-attr]
            """SELECT url, title, summary, scraped_at
               FROM articles WHERE topic = ?
               ORDER BY scraped_at DESC LIMIT ?""",
            (topic, limit),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    # ── GitHub repos ──────────────────────────────────────────────────────────
    async def save_repo_snapshot(
        self,
        repo_full_name: str,
        stars: int,
        forks: int,
        open_issues: int,
        latest_release: str,
        topic: str = "",
    ) -> None:
        self._ensure_connected()
        await self._conn.execute(  # type: ignore[union-attr]
            """INSERT OR IGNORE INTO github_repos
               (repo_full_name, stars, forks, open_issues, latest_release, topic, recorded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (repo_full_name, stars, forks, open_issues, latest_release, topic, self._now()),
        )
        await self._conn.commit()  # type: ignore[union-attr]

    async def get_repo_history(self, repo_full_name: str) -> list[dict]:
        """Return chronological star-count snapshots for a repo."""
        self._ensure_connected()
        async with self._conn.execute(  # type: ignore[union-attr]
            """SELECT stars, forks, open_issues, recorded_at
               FROM github_repos WHERE repo_full_name = ?
               ORDER BY recorded_at ASC""",
            (repo_full_name,),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def get_latest_repos_for_topic(self, topic: str, limit: int = 20) -> list[dict]:
        self._ensure_connected()
        async with self._conn.execute(  # type: ignore[union-attr]
            """SELECT repo_full_name, stars, forks, open_issues, latest_release, recorded_at
               FROM github_repos WHERE topic = ?
               GROUP BY repo_full_name
               HAVING recorded_at = MAX(recorded_at)
               ORDER BY stars DESC LIMIT ?""",
            (topic, limit),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    # ── Reports ───────────────────────────────────────────────────────────────
    async def save_report(self, topic: str, report: dict) -> int:
        self._ensure_connected()
        async with self._conn.execute(  # type: ignore[union-attr]
            "INSERT INTO reports (topic, report_json, created_at) VALUES (?, ?, ?)",
            (topic, json.dumps(report), self._now()),
        ) as cur:
            row_id = cur.lastrowid
        await self._conn.commit()  # type: ignore[union-attr]
        return row_id  # type: ignore[return-value]

    async def get_reports_for_topic(self, topic: str, limit: int = 5) -> list[dict]:
        self._ensure_connected()
        async with self._conn.execute(  # type: ignore[union-attr]
            """SELECT id, created_at, report_json FROM reports
               WHERE topic = ? ORDER BY id DESC LIMIT ?""",
            (topic, limit),
        ) as cur:
            rows = await cur.fetchall()
        return [
            {"id": r["id"], "created_at": r["created_at"], **json.loads(r["report_json"])}
            for r in rows
        ]

    async def get_all_topics(self) -> list[str]:
        self._ensure_connected()
        async with self._conn.execute(  # type: ignore[union-attr]
            "SELECT DISTINCT topic FROM queries ORDER BY topic"
        ) as cur:
            rows = await cur.fetchall()
        return [r["topic"] for r in rows]
