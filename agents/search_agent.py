"""
agents/search_agent.py — Web search with automatic fallback.

Primary   : Tavily Search API (AI-optimised, 1000 free/month)
Fallback  : DuckDuckGo (unlimited, no API key needed)

If TAVILY_API_KEY is set and has quota → uses Tavily.
Otherwise → falls back to DuckDuckGo automatically.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from config import TAVILY_API_KEY, MAX_SEARCH_RESULTS

logger = logging.getLogger(__name__)

TAVILY_SEARCH_URL = "https://api.tavily.com/search"


# ── Tavily (primary) ─────────────────────────────────────────────────────────

@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=8))
async def _search_tavily(query: str, max_results: int) -> list[dict]:
    """Call Tavily Search API. Raises on auth/quota errors so caller can fallback."""
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "max_results": max_results,
        "search_depth": "basic",
        "include_answer": False,
        "include_raw_content": False,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(TAVILY_SEARCH_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()

    results = []
    for r in data.get("results", []):
        results.append(
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "description": r.get("content", "")[:300],
            }
        )
    return results


# ── DuckDuckGo (fallback — no API key needed) ────────────────────────────────

async def _search_duckduckgo(query: str, max_results: int) -> list[dict]:
    """Search via duckduckgo-search library. Free, unlimited, no key required."""
    try:
        from ddgs import DDGS
    except ImportError:
        logger.error("ddgs not installed — run: pip install ddgs")
        return []

    results = []
    try:
        # DDGS is sync — run in executor to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        raw = await loop.run_in_executor(
            None,
            lambda: list(DDGS().text(query, max_results=max_results)),
        )
        for r in raw:
            results.append(
                {
                    "title": r.get("title", ""),
                    "url": r.get("href", r.get("link", "")),
                    "description": r.get("body", "")[:300],
                }
            )
    except Exception as e:
        logger.error("[SearchAgent] DuckDuckGo error: %s", e)

    return results


# ── Smart router ──────────────────────────────────────────────────────────────

async def _smart_search(query: str, max_results: int) -> tuple[list[dict], str]:
    """
    Try Tavily first. If key missing or request fails → DuckDuckGo.
    Returns (results, engine_used).
    """
    # Try Tavily if key is configured
    if TAVILY_API_KEY:
        try:
            results = await _search_tavily(query, max_results)
            if results:
                return results, "tavily"
        except Exception as e:
            logger.warning("[SearchAgent] Tavily failed (%s) — switching to DuckDuckGo", e)

    # Fallback to DuckDuckGo
    results = await _search_duckduckgo(query, max_results)
    return results, "duckduckgo"


# ── Public interface ──────────────────────────────────────────────────────────

class SearchAgent:
    """Searches the web for news and competitor data on a given topic."""

    def __init__(self, max_results: int = MAX_SEARCH_RESULTS) -> None:
        self.max_results = max_results

    async def search(self, topic: str) -> list[dict]:
        """
        Return a list of search results for *topic*.
        Each result: {"title": str, "url": str, "description": str}
        """
        logger.info("[SearchAgent] Searching: %s", topic)

        queries = self._build_queries(topic)
        all_results: list[dict] = []
        seen_urls: set[str] = set()
        engine_used = "none"

        for query in queries:
            results, engine_used = await _smart_search(query, self.max_results)

            for r in results:
                if r["url"] and r["url"] not in seen_urls:
                    seen_urls.add(r["url"])
                    all_results.append(r)

            if len(all_results) >= self.max_results * 2:
                break

        logger.info(
            "[SearchAgent] Total unique results: %d (engine: %s)",
            len(all_results),
            engine_used,
        )
        return all_results[: self.max_results * 3]

    @staticmethod
    def _build_queries(topic: str) -> list[str]:
        return [
            f"{topic} latest news 2025",
            f"{topic} product launch announcement",
            f"{topic} funding investment",
            f"{topic} competitors comparison",
        ]
