"""
config.py — Central configuration for the Multi-Agent CI/Market Research System.
Loads all environment variables, MCP server paths, and model settings.
"""

import os
import ssl
import sys
from pathlib import Path
from dotenv import load_dotenv

# ── Load .env ─────────────────────────────────────────────────────────────────
load_dotenv()

# ── Base paths ────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
REPORTS_DIR = BASE_DIR / "reports"
DB_PATH     = BASE_DIR / "memory" / "research.db"

REPORTS_DIR.mkdir(exist_ok=True)
(BASE_DIR / "memory").mkdir(exist_ok=True)

# ── API Keys ──────────────────────────────────────────────────────────────────
GROQ_API_KEY    = os.getenv("GROQ_API_KEY", "")
TAVILY_API_KEY  = os.getenv("TAVILY_API_KEY", "")
GITHUB_TOKEN    = os.getenv("GITHUB_TOKEN", "")

# ── Groq / LLM ────────────────────────────────────────────────────────────────
GROQ_BASE_URL   = "https://api.groq.com/openai/v1"
GROQ_MODEL      = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.3"))
LLM_MAX_TOKENS  = int(os.getenv("LLM_MAX_TOKENS", "4096"))

# ── MCP Server commands ───────────────────────────────────────────────────────
# Each value is (command, [args], {env_overrides})
MCP_SERVERS = {
    "tavily": {
        # Tavily search — REST API only (no MCP stdio server needed)
        "command": None,
        "args": [],
        "env": {"TAVILY_API_KEY": TAVILY_API_KEY},
    },
    "fetch": {
        # mcp-server-fetch is a Python package (pip install mcp-server-fetch)
        "command": "python",
        "args": ["-m", "mcp_server_fetch"],
        "env": {},
    },
    "github": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": GITHUB_TOKEN},
    },
    "memory": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-memory"],
        "env": {},
    },
}

# ── MCP timeouts (seconds) ────────────────────────────────────────────────────
MCP_INIT_TIMEOUT  = int(os.getenv("MCP_INIT_TIMEOUT", "30"))
MCP_CALL_TIMEOUT  = int(os.getenv("MCP_CALL_TIMEOUT", "60"))

# ── Search settings ───────────────────────────────────────────────────────────
MAX_SEARCH_RESULTS  = int(os.getenv("MAX_SEARCH_RESULTS", "10"))
MAX_SCRAPE_ARTICLES = int(os.getenv("MAX_SCRAPE_ARTICLES", "5"))
MAX_GITHUB_REPOS    = int(os.getenv("MAX_GITHUB_REPOS", "10"))

# ── Scheduler ─────────────────────────────────────────────────────────────────
SCHEDULER_CRON_HOUR   = int(os.getenv("SCHEDULER_CRON_HOUR", "8"))
SCHEDULER_CRON_MINUTE = int(os.getenv("SCHEDULER_CRON_MINUTE", "0"))
# Comma-separated list of default topics for the always-on scheduler
DEFAULT_TOPICS = [
    t.strip()
    for t in os.getenv(
        "DEFAULT_TOPICS",
        "OpenAI competitors,Anthropic Claude,AI agent frameworks",
    ).split(",")
    if t.strip()
]

# ── FastAPI ───────────────────────────────────────────────────────────────────
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("PORT", "8000"))

# ── SSL fix for Windows ───────────────────────────────────────────────────────
def patch_ssl_windows() -> None:
    """Use truststore on Windows to avoid SSL certificate verification errors."""
    if sys.platform == "win32":
        try:
            import truststore
            truststore.inject_into_ssl()
        except ImportError:
            # Fallback: create an unverified context (dev only)
            ssl._create_default_https_context = ssl._create_unverified_context  # noqa: SLF001

patch_ssl_windows()

# ── Validation helper ─────────────────────────────────────────────────────────
def validate_required_keys() -> list[str]:
    """Return a list of missing required environment variable names."""
    missing = []
    if not GROQ_API_KEY:
        missing.append("GROQ_API_KEY")
    # TAVILY_API_KEY is optional — DuckDuckGo is used as free fallback
    return missing


if __name__ == "__main__":
    missing = validate_required_keys()
    if missing:
        print(f"[config] WARNING — missing keys: {missing}")
    else:
        print("[config] All required keys present.")
    print(f"[config] Model : {GROQ_MODEL}")
    print(f"[config] DB    : {DB_PATH}")
    print(f"[config] Reports: {REPORTS_DIR}")
