"""
orchestrator.py — Coordinates all agents into a single research pipeline.

Pipeline:
  1. SearchAgent    → web search results (URLs + descriptions)
  2. ScraperAgent   → full article content for each URL
  3. GitHubAgent    → trending repos for topic
  4. Memory         → deduplicate already-seen articles & repos
  5. AnalystAgent   → LLM trend/threat/opportunity analysis
  6. ReportWriter   → structured JSON + Markdown report
  7. Memory         → persist report & article metadata
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from agents import AnalystAgent, GitHubAgent, ReportWriter, ScraperAgent, SearchAgent
from memory import ResearchMemory

logger = logging.getLogger(__name__)


class ResearchOrchestrator:
    """
    Single entry point: call ``run(topic)`` to get a complete intelligence report.
    """

    def __init__(self) -> None:
        self.search_agent  = SearchAgent()
        self.scraper_agent = ScraperAgent()
        self.github_agent  = GitHubAgent()
        self.analyst_agent = AnalystAgent()
        self.report_writer = ReportWriter()
        self.memory        = ResearchMemory()

    # ── Public ────────────────────────────────────────────────────────────────

    async def run(self, topic: str) -> dict[str, Any]:
        """
        Execute the full multi-agent pipeline for *topic*.
        Returns the final report dict.
        """
        t0 = time.perf_counter()
        logger.info("=" * 60)
        logger.info("[Orchestrator] START  topic=%r", topic)

        async with self.memory:
            # 0. Log query
            await self.memory.log_query(topic)

            # 1 & 3 — search + GitHub run concurrently
            logger.info("[Orchestrator] Step 1/3 — searching web & GitHub concurrently")
            search_results, github_snapshots = await asyncio.gather(
                self.search_agent.search(topic),
                self.github_agent.monitor(topic),
                return_exceptions=True,
            )

            if isinstance(search_results, Exception):
                logger.error("[Orchestrator] SearchAgent failed: %s", search_results)
                search_results = []
            if isinstance(github_snapshots, Exception):
                logger.error("[Orchestrator] GitHubAgent failed: %s", github_snapshots)
                github_snapshots = []

            # 2. Deduplicate URLs
            logger.info("[Orchestrator] Step 2 — deduplicating %d URLs", len(search_results))
            fresh_results = await self._deduplicate_articles(search_results, topic)
            logger.info("[Orchestrator] %d fresh articles after dedup", len(fresh_results))

            # 3. Scrape
            logger.info("[Orchestrator] Step 3 — scraping articles")
            scraped = await self.scraper_agent.scrape(fresh_results)

            # Build article list for analyst (mix scraped + description-only)
            articles_for_analysis: list[dict] = []
            for art in scraped:
                articles_for_analysis.append(art.to_dict())
            # pad with search snippets if we have few scraped articles
            if len(articles_for_analysis) < 5:
                for r in search_results:
                    if r["url"] not in {a["url"] for a in articles_for_analysis}:
                        articles_for_analysis.append(
                            {
                                "url": r["url"],
                                "title": r["title"],
                                "content": r.get("description", ""),
                                "success": False,
                            }
                        )

            # 4. Save article metadata to memory
            logger.info("[Orchestrator] Step 4 — persisting article metadata")
            for art in scraped:
                if art.success:
                    await self.memory.save_article(
                        url=art.url,
                        title=art.title,
                        summary=art.content[:200],
                        topic=topic,
                    )

            # 5. Save GitHub snapshots
            logger.info("[Orchestrator] Step 5 — persisting GitHub snapshots")
            gh_dicts = [s.to_dict() for s in github_snapshots]
            for snap in github_snapshots:
                await self.memory.save_repo_snapshot(
                    repo_full_name=snap.full_name,
                    stars=snap.stars,
                    forks=snap.forks,
                    open_issues=snap.open_issues,
                    latest_release=snap.latest_release,
                    topic=topic,
                )

            # 6. Analyse
            logger.info("[Orchestrator] Step 6 — running LLM analysis")
            analysis = await self.analyst_agent.analyse(
                topic=topic,
                articles=articles_for_analysis,
                github_repos=gh_dicts,
            )

            # 7. Write report
            logger.info("[Orchestrator] Step 7 — writing report")
            report = self.report_writer.write(
                topic=topic,
                analysis=analysis.to_dict(),
                github_repos=gh_dicts,
                sources=articles_for_analysis,
            )

            # 8. Persist report
            await self.memory.save_report(topic, report)

        elapsed = time.perf_counter() - t0
        logger.info("[Orchestrator] DONE  elapsed=%.1fs", elapsed)
        report["_elapsed_seconds"] = round(elapsed, 2)
        return report

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _deduplicate_articles(
        self, results: list[dict], topic: str
    ) -> list[dict]:
        fresh = []
        for r in results:
            url = r.get("url", "")
            if not url:
                continue
            if not await self.memory.is_article_seen(url):
                fresh.append(r)
        return fresh

    async def get_history(self, limit: int = 20) -> list[dict]:
        """Return recent query history."""
        async with self.memory:
            return await self.memory.get_query_history(limit)

    async def get_repo_history(self, repo_full_name: str) -> list[dict]:
        """Return star-count snapshots for a repo (for trend charts)."""
        async with self.memory:
            return await self.memory.get_repo_history(repo_full_name)

    async def get_all_topics(self) -> list[str]:
        async with self.memory:
            return await self.memory.get_all_topics()

    async def get_past_reports(self, topic: str, limit: int = 5) -> list[dict]:
        async with self.memory:
            return await self.memory.get_reports_for_topic(topic, limit)
