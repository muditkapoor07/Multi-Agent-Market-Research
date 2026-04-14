"""
agents/report_writer.py — Structured weekly intelligence briefing generator.

Combines analysis results, GitHub data, and sources into a rich
JSON report and optionally a Markdown document.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import REPORTS_DIR

logger = logging.getLogger(__name__)


# ── Report schema ─────────────────────────────────────────────────────────────

def _build_report(
    topic: str,
    analysis: dict,
    github_repos: list[dict],
    sources: list[dict],
) -> dict:
    """Assemble the canonical report dict."""
    now = datetime.now(timezone.utc).isoformat()

    # Source list — title, url, short summary
    source_list = []
    for s in sources:
        source_list.append(
            {
                "title": s.get("title", s.get("url", "")),
                "url": s.get("url", ""),
                "summary": (s.get("content", "") or s.get("description", ""))[:300],
            }
        )

    # GitHub section
    gh_section = []
    for r in github_repos:
        gh_section.append(
            {
                "full_name": r.get("full_name", ""),
                "description": r.get("description", ""),
                "stars": r.get("stars", 0),
                "forks": r.get("forks", 0),
                "open_issues": r.get("open_issues", 0),
                "language": r.get("language", ""),
                "latest_release": r.get("latest_release", "N/A"),
                "latest_release_date": r.get("latest_release_date", ""),
                "recent_commits": r.get("recent_commits", 0),
                "topics": r.get("topics", []),
            }
        )

    # Timeline — ordered events extracted from article titles + dates
    timeline = _build_timeline(sources)

    return {
        "meta": {
            "topic": topic,
            "generated_at": now,
            "version": "1.0",
        },
        "executive_briefing": {
            "headline": f"Weekly Intelligence Briefing: {topic}",
            "summary": analysis.get("executive_summary", ""),
            "sentiment": analysis.get("sentiment", "neutral"),
            "sentiment_score": analysis.get("sentiment_score", 0.0),
            "key_trends": analysis.get("key_trends", []),
            "threats": analysis.get("threats", []),
            "opportunities": analysis.get("opportunities", []),
            "key_entities": analysis.get("key_entities", []),
        },
        "recommended_actions": analysis.get("recommended_actions", []),
        "github_trends": gh_section,
        "sources": source_list,
        "timeline": timeline,
    }


def _build_timeline(sources: list[dict]) -> list[dict]:
    """Build a simple timeline from source titles (best-effort)."""
    events = []
    for s in sources:
        title = s.get("title", "")
        url = s.get("url", "")
        if title and url:
            events.append(
                {
                    "title": title,
                    "url": url,
                    "date": "",   # date extraction would require NLP; left empty for now
                }
            )
    return events[:20]


# ── Markdown renderer ─────────────────────────────────────────────────────────

def _render_markdown(report: dict) -> str:
    meta = report["meta"]
    eb = report["executive_briefing"]
    actions = report.get("recommended_actions", [])
    gh = report.get("github_trends", [])
    sources = report.get("sources", [])
    timeline = report.get("timeline", [])

    sentiment_emoji = {"positive": "📈", "neutral": "➡️", "negative": "📉"}.get(
        eb["sentiment"], "➡️"
    )

    lines = [
        f"# {eb['headline']}",
        f"",
        f"> Generated: {meta['generated_at'][:10]}  |  "
        f"Sentiment: {sentiment_emoji} {eb['sentiment'].capitalize()} "
        f"({eb['sentiment_score']:+.2f})",
        f"",
        f"## Executive Summary",
        f"",
        eb["summary"],
        f"",
    ]

    if eb["key_trends"]:
        lines += ["## Key Trends", ""]
        for t in eb["key_trends"]:
            lines.append(f"- {t}")
        lines.append("")

    if eb["threats"]:
        lines += ["## Threats", ""]
        for t in eb["threats"]:
            lines.append(f"- ⚠️  {t}")
        lines.append("")

    if eb["opportunities"]:
        lines += ["## Opportunities", ""]
        for o in eb["opportunities"]:
            lines.append(f"- ✅  {o}")
        lines.append("")

    if actions:
        lines += ["## Recommended Actions", ""]
        for i, a in enumerate(actions, 1):
            lines.append(f"{i}. {a}")
        lines.append("")

    if gh:
        lines += ["## GitHub Trends", "", "| Repository | Stars | Language | Latest Release |", "|---|---|---|---|"]
        for r in gh[:10]:
            lines.append(
                f"| [{r['full_name']}](https://github.com/{r['full_name']}) "
                f"| ⭐ {r['stars']:,} "
                f"| {r['language']} "
                f"| {r['latest_release']} |"
            )
        lines.append("")

    if sources:
        lines += ["## Sources", ""]
        for s in sources[:15]:
            lines.append(f"- [{s['title']}]({s['url']})")
            if s.get("summary"):
                lines.append(f"  > {s['summary'][:120]}…")
        lines.append("")

    if timeline:
        lines += ["## Timeline", ""]
        for e in timeline[:10]:
            lines.append(f"- **{e['title']}** — {e['url']}")
        lines.append("")

    return "\n".join(lines)


# ── Public interface ──────────────────────────────────────────────────────────

class ReportWriter:
    """Assembles a full intelligence report and persists it to disk."""

    def __init__(self, reports_dir: Path = REPORTS_DIR) -> None:
        self.reports_dir = reports_dir
        self.reports_dir.mkdir(exist_ok=True)

    def write(
        self,
        topic: str,
        analysis: dict,
        github_repos: list[dict],
        sources: list[dict],
    ) -> dict:
        """
        Build the report dict, save JSON + Markdown to disk, return the report.
        """
        logger.info("[ReportWriter] Writing report for: %s", topic)

        report = _build_report(topic, analysis, github_repos, sources)

        slug = _topic_slug(topic)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        base_name = f"{slug}_{ts}"

        # JSON
        json_path = self.reports_dir / f"{base_name}.json"
        json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("[ReportWriter] Saved JSON: %s", json_path)

        # Markdown
        md_path = self.reports_dir / f"{base_name}.md"
        md_path.write_text(_render_markdown(report), encoding="utf-8")
        logger.info("[ReportWriter] Saved MD : %s", md_path)

        report["_file_paths"] = {"json": str(json_path), "markdown": str(md_path)}
        return report


def _topic_slug(topic: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "_", topic.lower()).strip("_")[:40]
