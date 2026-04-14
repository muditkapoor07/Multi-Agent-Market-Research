"""
data/sample_topics.py — 10 pre-configured research topics.

Each entry has a display name and optional description / search hints.
"""

from __future__ import annotations

# ── Topic list ────────────────────────────────────────────────────────────────

SAMPLE_TOPICS: list[str] = [
    "OpenAI competitors",
    "Anthropic Claude AI updates",
    "AI agent frameworks 2025",
    "HR tech market trends",
    "Autonomous vehicle software",
    "Large language model fine-tuning",
    "Cybersecurity threat intelligence",
    "Generative AI in healthcare",
    "Open source LLM ecosystem",
    "Cloud infrastructure pricing wars",
]

# ── Enriched metadata (optional — used for sidebar descriptions) ──────────────

TOPIC_METADATA: dict[str, dict] = {
    "OpenAI competitors": {
        "description": "Track Anthropic, Google Gemini, Mistral, xAI and others competing with OpenAI.",
        "github_query": "llm api openai alternative",
        "icon": "🤖",
    },
    "Anthropic Claude AI updates": {
        "description": "Latest Claude model releases, API changes, safety research.",
        "github_query": "anthropic claude sdk",
        "icon": "🧠",
    },
    "AI agent frameworks 2025": {
        "description": "AutoGen, LangChain, CrewAI, LlamaIndex and emerging agent orchestration tools.",
        "github_query": "ai agent framework autonomous",
        "icon": "⚙️",
    },
    "HR tech market trends": {
        "description": "AI-powered recruiting, HRIS systems, workforce analytics platforms.",
        "github_query": "hr tech recruitment automation",
        "icon": "👥",
    },
    "Autonomous vehicle software": {
        "description": "Tesla FSD, Waymo, Cruise, Mobileye — sensor fusion & perception stacks.",
        "github_query": "autonomous driving perception",
        "icon": "🚗",
    },
    "Large language model fine-tuning": {
        "description": "LoRA, QLoRA, RLHF toolkits, training infrastructure updates.",
        "github_query": "llm fine-tuning lora rlhf",
        "icon": "🔧",
    },
    "Cybersecurity threat intelligence": {
        "description": "CVE disclosures, ransomware groups, zero-day exploits, SIEM updates.",
        "github_query": "threat intelligence SIEM security",
        "icon": "🛡️",
    },
    "Generative AI in healthcare": {
        "description": "Medical imaging AI, drug discovery, clinical NLP tools.",
        "github_query": "medical ai healthcare llm",
        "icon": "🏥",
    },
    "Open source LLM ecosystem": {
        "description": "Llama, Mistral, Falcon, Phi-3 and community-driven model releases.",
        "github_query": "open source LLM transformer model",
        "icon": "🌐",
    },
    "Cloud infrastructure pricing wars": {
        "description": "AWS vs Azure vs GCP pricing changes, new instance types, cost optimisation.",
        "github_query": "cloud cost optimization aws azure gcp",
        "icon": "☁️",
    },
}
