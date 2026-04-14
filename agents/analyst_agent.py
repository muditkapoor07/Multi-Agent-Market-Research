"""
agents/analyst_agent.py — LLM-powered intelligence analysis via Groq LLaMA 3.3 70B.

Responsibilities:
  • Trend detection across scraped articles
  • Competitive threat & opportunity identification
  • Sentiment analysis (positive / neutral / negative)
  • Key entity extraction (companies, products, people)
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from config import GROQ_API_KEY, GROQ_BASE_URL, GROQ_MODEL, LLM_MAX_TOKENS, LLM_TEMPERATURE

logger = logging.getLogger(__name__)

# ── Data models ───────────────────────────────────────────────────────────────

@dataclass
class AnalysisResult:
    topic: str
    key_trends: list[str]
    threats: list[str]
    opportunities: list[str]
    key_entities: list[str]          # companies / products mentioned
    sentiment: str                   # "positive" | "neutral" | "negative"
    sentiment_score: float           # -1.0 … +1.0
    executive_summary: str
    recommended_actions: list[str]
    raw_llm_response: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_client() -> AsyncOpenAI:
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY is not set. Check your .env file.")
    return AsyncOpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL)


# ── Prompt builders ───────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a senior competitive intelligence analyst. Your role is to analyse web content,
identify strategic trends, threats and opportunities, and produce actionable intelligence
briefings. Be specific, factual, and concise. Avoid filler language."""


def _build_analysis_prompt(
    topic: str,
    articles: list[dict],
    github_repos: list[dict],
) -> str:
    # Compress article content for the prompt
    article_block = ""
    for i, a in enumerate(articles[:8], 1):
        title = a.get("title", "")
        url = a.get("url", "")
        content = (a.get("content", "") or a.get("description", ""))[:800]
        article_block += f"\n--- Article {i}: {title} ({url}) ---\n{content}\n"

    # GitHub repo summary
    repo_block = ""
    for r in github_repos[:5]:
        repo_block += (
            f"• {r.get('full_name','')} — ⭐{r.get('stars',0):,} "
            f"| {r.get('language','')} "
            f"| {r.get('description','')[:100]}\n"
        )

    return f"""Analyse the following intelligence data about: **{topic}**

=== WEB ARTICLES ===
{article_block or "No articles available."}

=== GITHUB TRENDING REPOS ===
{repo_block or "No GitHub data available."}

Provide a structured JSON response with EXACTLY these keys:
{{
  "key_trends": ["<trend 1>", "<trend 2>", ...],      // 3-6 key trends
  "threats": ["<threat 1>", ...],                      // 2-4 strategic threats
  "opportunities": ["<opportunity 1>", ...],           // 2-4 strategic opportunities
  "key_entities": ["<Company/Product 1>", ...],        // notable companies/products
  "sentiment": "<positive|neutral|negative>",
  "sentiment_score": <float -1.0 to 1.0>,
  "executive_summary": "<2-3 sentence executive summary>",
  "recommended_actions": ["<action 1>", ...]           // 3-5 concrete recommended actions
}}

Return ONLY the JSON object. No markdown fences, no extra text."""


# ── Main agent ────────────────────────────────────────────────────────────────

class AnalystAgent:
    """Runs LLM analysis on scraped articles and GitHub data."""

    def __init__(self) -> None:
        self._client = _get_client()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=15))
    async def analyse(
        self,
        topic: str,
        articles: list[dict],
        github_repos: list[dict],
    ) -> AnalysisResult:
        """
        Run LLM analysis and return a structured AnalysisResult.
        Falls back to a minimal result if the LLM is unavailable.
        """
        logger.info("[AnalystAgent] Analysing topic: %s (%d articles)", topic, len(articles))

        prompt = _build_analysis_prompt(topic, articles, github_repos)

        try:
            response = await self._client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=LLM_TEMPERATURE,
                max_tokens=LLM_MAX_TOKENS,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content or ""
            logger.debug("[AnalystAgent] Raw LLM response: %s…", raw[:200])
            parsed = self._parse_response(raw)
            parsed["topic"] = topic
            parsed["raw_llm_response"] = raw
            return AnalysisResult(**parsed)

        except Exception as e:
            logger.error("[AnalystAgent] LLM call failed: %s", e)
            return self._fallback_result(topic, articles, str(e))

    # ── helpers ───────────────────────────────────────────────────────────────
    @staticmethod
    def _parse_response(raw: str) -> dict[str, Any]:
        import json
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Try to extract JSON block
            import re
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            data = json.loads(m.group()) if m else {}

        defaults: dict[str, Any] = {
            "key_trends": [],
            "threats": [],
            "opportunities": [],
            "key_entities": [],
            "sentiment": "neutral",
            "sentiment_score": 0.0,
            "executive_summary": "Analysis not available.",
            "recommended_actions": [],
            "raw_llm_response": raw,
        }
        for k, v in defaults.items():
            if k not in data:
                data[k] = v
        return data

    @staticmethod
    def _fallback_result(topic: str, articles: list[dict], error: str) -> AnalysisResult:
        titles = [a.get("title", "") for a in articles[:5] if a.get("title")]
        return AnalysisResult(
            topic=topic,
            key_trends=titles[:3],
            threats=["LLM analysis unavailable"],
            opportunities=["Review sources manually"],
            key_entities=[],
            sentiment="neutral",
            sentiment_score=0.0,
            executive_summary=f"Automated analysis failed ({error}). Manual review recommended.",
            recommended_actions=["Check GROQ_API_KEY", "Review raw sources in the Sources tab"],
            raw_llm_response=f"ERROR: {error}",
        )
