"""
agents/github_agent.py — GitHub repository monitoring via GitHub MCP.

Primary path  : GitHub MCP (stdio, npx)
Fallback path : GitHub REST API v3 (direct HTTPS, no auth required for public repos)
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import asdict, dataclass, field
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from config import (
    GITHUB_TOKEN,
    MAX_GITHUB_REPOS,
    MCP_CALL_TIMEOUT,
    MCP_INIT_TIMEOUT,
    MCP_SERVERS,
)

logger = logging.getLogger(__name__)


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class RepoSnapshot:
    full_name: str
    description: str
    stars: int
    forks: int
    open_issues: int
    language: str
    latest_release: str
    latest_release_date: str
    recent_commits: int          # commits in last 30 days (approximation)
    topics: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ── GitHub REST helpers ───────────────────────────────────────────────────────

def _gh_headers() -> dict:
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return h


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
async def _gh_get(client: httpx.AsyncClient, path: str) -> Any:
    url = f"https://api.github.com{path}"
    resp = await client.get(url, headers=_gh_headers())
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


# ── MCP path ──────────────────────────────────────────────────────────────────

async def _search_repos_via_mcp(query: str, limit: int) -> list[dict]:
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError:
        raise RuntimeError("mcp package not installed")

    cfg = MCP_SERVERS["github"]
    env = {**os.environ, **cfg["env"]}
    params = StdioServerParameters(command=cfg["command"], args=cfg["args"], env=env)

    async with asyncio.timeout(MCP_INIT_TIMEOUT + MCP_CALL_TIMEOUT):
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), timeout=MCP_INIT_TIMEOUT)
                result = await asyncio.wait_for(
                    session.call_tool(
                        "search_repositories",
                        {"query": query, "perPage": limit},
                    ),
                    timeout=MCP_CALL_TIMEOUT,
                )
                return _parse_mcp_repos(result)


def _parse_mcp_repos(result: Any) -> list[dict]:
    repos: list[dict] = []
    if hasattr(result, "content"):
        for block in result.content:
            if hasattr(block, "text"):
                import json as _json
                try:
                    data = _json.loads(block.text)
                    items = data.get("items", data) if isinstance(data, dict) else data
                    if isinstance(items, list):
                        for r in items:
                            repos.append(
                                {
                                    "full_name": r.get("full_name", ""),
                                    "description": r.get("description", "") or "",
                                    "stars": r.get("stargazers_count", 0),
                                    "forks": r.get("forks_count", 0),
                                    "open_issues": r.get("open_issues_count", 0),
                                    "language": r.get("language", "") or "",
                                    "topics": r.get("topics", []),
                                }
                            )
                except Exception:
                    pass
    return repos


# ── REST path ─────────────────────────────────────────────────────────────────

async def _search_repos_via_rest(query: str, limit: int) -> list[dict]:
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            "https://api.github.com/search/repositories",
            headers=_gh_headers(),
            params={"q": query, "sort": "stars", "order": "desc", "per_page": limit},
        )
        resp.raise_for_status()
        data = resp.json()
    repos = []
    for r in data.get("items", []):
        repos.append(
            {
                "full_name": r.get("full_name", ""),
                "description": r.get("description", "") or "",
                "stars": r.get("stargazers_count", 0),
                "forks": r.get("forks_count", 0),
                "open_issues": r.get("open_issues_count", 0),
                "language": r.get("language", "") or "",
                "topics": r.get("topics", []),
            }
        )
    return repos


async def _enrich_repo(client: httpx.AsyncClient, repo_dict: dict) -> RepoSnapshot:
    """Fetch release & commit data and build a full RepoSnapshot."""
    fn = repo_dict["full_name"]

    # Latest release
    latest_release = "N/A"
    latest_release_date = ""
    try:
        rel = await _gh_get(client, f"/repos/{fn}/releases/latest")
        if rel:
            latest_release = rel.get("tag_name", "N/A")
            latest_release_date = rel.get("published_at", "")[:10]
    except Exception:
        pass

    # Approximate recent commit count via commits?since=30days
    recent_commits = 0
    try:
        from datetime import datetime, timedelta, timezone
        since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        commits = await _gh_get(client, f"/repos/{fn}/commits?since={since}&per_page=100")
        if isinstance(commits, list):
            recent_commits = len(commits)
    except Exception:
        pass

    return RepoSnapshot(
        full_name=fn,
        description=repo_dict["description"],
        stars=repo_dict["stars"],
        forks=repo_dict["forks"],
        open_issues=repo_dict["open_issues"],
        language=repo_dict["language"],
        latest_release=latest_release,
        latest_release_date=latest_release_date,
        recent_commits=recent_commits,
        topics=repo_dict.get("topics", []),
    )


# ── Public interface ──────────────────────────────────────────────────────────

class GitHubAgent:
    """Monitors GitHub for trending repos related to a topic."""

    def __init__(self, max_repos: int = MAX_GITHUB_REPOS) -> None:
        self.max_repos = max_repos

    async def monitor(self, topic: str) -> list[RepoSnapshot]:
        """
        Search GitHub for repos matching *topic*, enrich with release/commit data,
        return sorted by star count descending.
        """
        logger.info("[GitHubAgent] Monitoring GitHub for: %s", topic)
        query = self._build_query(topic)

        # Search
        repos: list[dict] = []
        try:
            repos = await _search_repos_via_mcp(query, self.max_repos)
            logger.debug("[GitHubAgent] MCP returned %d repos", len(repos))
        except Exception as mcp_err:
            logger.warning("[GitHubAgent] MCP failed (%s) — falling back to REST", mcp_err)
            try:
                repos = await _search_repos_via_rest(query, self.max_repos)
            except Exception as rest_err:
                logger.error("[GitHubAgent] REST also failed: %s", rest_err)
                return []

        if not repos:
            return []

        # Enrich in parallel
        async with httpx.AsyncClient(timeout=20) as client:
            snapshots = await asyncio.gather(
                *[_enrich_repo(client, r) for r in repos[: self.max_repos]],
                return_exceptions=True,
            )

        result = []
        for snap in snapshots:
            if isinstance(snap, RepoSnapshot):
                result.append(snap)
            else:
                logger.warning("[GitHubAgent] Enrichment error: %s", snap)

        result.sort(key=lambda s: s.stars, reverse=True)
        logger.info("[GitHubAgent] Returning %d repo snapshots", len(result))
        return result

    @staticmethod
    def _build_query(topic: str) -> str:
        # Lower star threshold for broader results; GitHub search ranks by relevance
        return f"{topic} stars:>5"
