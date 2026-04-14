"""
agents/scraper_agent.py — Full-page content extraction.

Primary path  : Direct httpx + BeautifulSoup (fast, reliable)
Fallback path : Fetch MCP (stdio, npx)
Last resort   : Use search snippet as summary
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from config import MAX_SCRAPE_ARTICLES, MCP_CALL_TIMEOUT, MCP_INIT_TIMEOUT, MCP_SERVERS

logger = logging.getLogger(__name__)

MAX_CONTENT_CHARS = 6_000

# ── Junk patterns to strip from scraped content ──────────────────────────────

_JUNK_PATTERNS = [
    # Navigation / boilerplate
    r"Skip to [\w\s]+",
    r"Sign in.*?(?=\n|$)",
    r"Log in.*?(?=\n|$)",
    r"Subscribe.*?(?=\n|$)",
    r"Create (?:an )?account.*?(?=\n|$)",
    r"Already have an account\??.*?(?=\n|$)",
    # Cookie banners
    r"(?:We use |This site uses )cookies.*?(?=\n\n|\Z)",
    r"Accept (?:all )?cookies.*?(?=\n|$)",
    # Robots.txt / fetch errors
    r"Failed to fetch robots\.txt.*?(?=\n|$)",
    r"Contents of https?://[^\s]+robots\.txt.*?(?=\n|$)",
    r"due to a connection issue.*?(?=\n|$)",
    r"Oops,? something went wrong.*?(?=\n|$)",
    # Social / share buttons
    r"Share (?:this|on) (?:Facebook|Twitter|LinkedIn|X).*?(?=\n|$)",
    r"Follow us on.*?(?=\n|$)",
    # Ads / promos
    r"Adve?r?t?i?s?e?m?e?n?t?\s*$",
    r"Sponsored\s*$",
    r"Promoted\s*$",
    r"Newsletter\s*$",
    # Footer junk
    r"All rights reserved.*?(?=\n|$)",
    r"Terms of (?:Service|Use).*?(?=\n|$)",
    r"Privacy Policy.*?(?=\n|$)",
    r"©\s*\d{4}.*?(?=\n|$)",
]

_JUNK_RE = re.compile("|".join(f"(?:{p})" for p in _JUNK_PATTERNS), re.IGNORECASE | re.MULTILINE)


def _sanitize_content(text: str) -> str:
    """Strip navigation, login walls, ad fragments, error messages from scraped text."""
    text = _JUNK_RE.sub("", text)
    # Collapse blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    # Remove very short lines (likely menu items)
    lines = []
    for line in text.split("\n"):
        stripped = line.strip()
        if len(stripped) > 15 or stripped == "":
            lines.append(line)
    text = "\n".join(lines)
    return text.strip()[:MAX_CONTENT_CHARS]


# ── Direct HTTP scraper (primary) ────────────────────────────────────────────

@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5))
async def _fetch_via_httpx(url: str) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return _parse_html(resp.text)


def _parse_html(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    # Remove non-content tags
    for tag in soup(["script", "style", "nav", "footer", "header", "aside",
                     "form", "iframe", "noscript", "svg", "button"]):
        tag.decompose()

    # Remove elements by common junk classes/ids
    for selector in [
        '[class*="cookie"]', '[class*="banner"]', '[class*="popup"]',
        '[class*="modal"]', '[class*="advert"]', '[class*="sidebar"]',
        '[class*="newsletter"]', '[class*="subscribe"]', '[class*="social"]',
        '[id*="cookie"]', '[id*="banner"]', '[id*="popup"]',
        '[id*="modal"]', '[id*="sidebar"]', '[id*="advert"]',
    ]:
        for el in soup.select(selector):
            el.decompose()

    # Prefer article / main body
    for selector in ["article", "main", '[role="main"]', ".post-content",
                     ".article-body", ".entry-content", ".story-body",
                     ".article-text", "#article-body"]:
        el = soup.select_one(selector)
        if el:
            return _sanitize_content(el.get_text(separator="\n"))

    return _sanitize_content(soup.get_text(separator="\n"))


# ── MCP fallback ─────────────────────────────────────────────────────────────

async def _fetch_via_mcp(url: str) -> str:
    """Retrieve page content via the Fetch MCP server."""
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError:
        raise RuntimeError("mcp package not installed")

    cfg = MCP_SERVERS["fetch"]
    if cfg["command"] is None:
        raise RuntimeError("Fetch MCP not configured")

    env = {**os.environ, **cfg["env"]}
    params = StdioServerParameters(command=cfg["command"], args=cfg["args"], env=env)

    async with asyncio.timeout(MCP_INIT_TIMEOUT + MCP_CALL_TIMEOUT):
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), timeout=MCP_INIT_TIMEOUT)
                result = await asyncio.wait_for(
                    session.call_tool("fetch", {"url": url, "max_length": MAX_CONTENT_CHARS}),
                    timeout=MCP_CALL_TIMEOUT,
                )
                text = ""
                if hasattr(result, "content"):
                    for block in result.content:
                        if hasattr(block, "text"):
                            text = block.text or ""
                            break
                return _sanitize_content(text)


# ── Article model ─────────────────────────────────────────────────────────────

class ScrapedArticle:
    __slots__ = ("url", "title", "content", "success")

    def __init__(self, url: str, title: str, content: str, success: bool) -> None:
        self.url = url
        self.title = title
        self.content = content
        self.success = success

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "title": self.title,
            "content": self.content,
            "success": self.success,
        }


# ── Public interface ──────────────────────────────────────────────────────────

class ScraperAgent:
    """Extracts full text content from a list of URLs."""

    def __init__(self, max_articles: int = MAX_SCRAPE_ARTICLES) -> None:
        self.max_articles = max_articles

    async def scrape(self, search_results: list[dict]) -> list[ScrapedArticle]:
        targets = search_results[: self.max_articles]
        logger.info("[ScraperAgent] Scraping %d URLs", len(targets))

        tasks = [self._scrape_one(r) for r in targets]
        articles = await asyncio.gather(*tasks, return_exceptions=False)
        successful = sum(1 for a in articles if a.success)
        logger.info("[ScraperAgent] Scraped %d/%d successfully", successful, len(articles))
        return articles

    async def _scrape_one(self, result: dict) -> ScrapedArticle:
        url = result.get("url", "")
        title = result.get("title", url)

        if not url:
            return ScrapedArticle(url, title, "", False)

        # Try direct HTTP first (faster, more reliable)
        try:
            content = await _fetch_via_httpx(url)
            if content.strip() and len(content.strip()) > 50:
                logger.debug("[ScraperAgent] HTTP success: %s", url[:60])
                return ScrapedArticle(url, title, content, True)
        except Exception as e:
            logger.debug("[ScraperAgent] HTTP failed for %s: %s", url[:60], e)

        # Try MCP
        try:
            content = await _fetch_via_mcp(url)
            if content.strip() and len(content.strip()) > 50:
                logger.debug("[ScraperAgent] MCP success: %s", url[:60])
                return ScrapedArticle(url, title, content, True)
        except Exception as e:
            logger.debug("[ScraperAgent] MCP failed for %s: %s", url[:60], e)

        # Last resort: use the search description
        fallback = result.get("description", "")
        return ScrapedArticle(url, title, fallback, bool(fallback))
