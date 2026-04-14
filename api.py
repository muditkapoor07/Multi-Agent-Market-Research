"""
api.py — FastAPI REST interface + background scheduler for always-on mode.

Endpoints:
  POST /research            — run full pipeline for a topic
  GET  /research/history    — recent query history
  GET  /research/topics     — all researched topics
  GET  /research/report     — latest saved report for a topic
  GET  /health              — liveness check

Background scheduler:
  Runs every Monday at 08:00 UTC for DEFAULT_TOPICS.
  Reports saved to reports/ directory.
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from config import (
    DEFAULT_TOPICS,
    REPORTS_DIR,
    SCHEDULER_CRON_HOUR,
    SCHEDULER_CRON_MINUTE,
    validate_required_keys,
)
from orchestrator import ResearchOrchestrator

logger = logging.getLogger(__name__)

# ── In-progress tracking ──────────────────────────────────────────────────────
_running_topics: set[str] = set()


# ── Scheduler ─────────────────────────────────────────────────────────────────

scheduler = AsyncIOScheduler(timezone="UTC")


async def _scheduled_research(topic: str) -> None:
    """Background task called by the scheduler."""
    logger.info("[Scheduler] Running scheduled research for: %s", topic)
    try:
        orch = ResearchOrchestrator()
        report = await orch.run(topic)
        logger.info(
            "[Scheduler] Completed %r — saved to %s",
            topic,
            report.get("_file_paths", {}).get("json", "?"),
        )
    except Exception as e:
        logger.error("[Scheduler] Failed for %r: %s", topic, e)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start scheduler
    for topic in DEFAULT_TOPICS:
        scheduler.add_job(
            _scheduled_research,
            CronTrigger(day_of_week="mon", hour=SCHEDULER_CRON_HOUR, minute=SCHEDULER_CRON_MINUTE),
            args=[topic],
            id=f"weekly_{topic[:30]}",
            replace_existing=True,
        )
    scheduler.start()
    logger.info(
        "[Scheduler] Started — %d topics scheduled every Mon %02d:%02d UTC",
        len(DEFAULT_TOPICS),
        SCHEDULER_CRON_HOUR,
        SCHEDULER_CRON_MINUTE,
    )
    yield
    scheduler.shutdown(wait=False)


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Competitive Intelligence & Market Research API",
    description="Multi-agent system powered by Brave Search, GitHub, Fetch MCP + Groq LLaMA 3.3",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / response models ─────────────────────────────────────────────────

class ResearchRequest(BaseModel):
    topic: str = Field(..., min_length=3, max_length=200, example="OpenAI competitors")
    async_mode: bool = Field(
        False, description="If true, return immediately and run in background"
    )


class ResearchStatus(BaseModel):
    topic: str
    status: str          # "running" | "completed" | "queued"
    message: str


# ── Background runner ─────────────────────────────────────────────────────────

async def _run_and_track(topic: str) -> None:
    _running_topics.add(topic)
    try:
        orch = ResearchOrchestrator()
        await orch.run(topic)
    except Exception as e:
        logger.error("[API] Background research failed for %r: %s", topic, e)
    finally:
        _running_topics.discard(topic)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict:
    missing = validate_required_keys()
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "missing_keys": missing,
        "scheduler_running": scheduler.running,
    }


@app.post("/research", response_model=None)
async def research(
    req: ResearchRequest,
    background_tasks: BackgroundTasks,
) -> Any:
    topic = req.topic.strip()

    if req.async_mode:
        if topic in _running_topics:
            return JSONResponse(
                {"topic": topic, "status": "running", "message": "Already in progress"},
                status_code=202,
            )
        background_tasks.add_task(_run_and_track, topic)
        return JSONResponse(
            {"topic": topic, "status": "queued", "message": "Research started in background"},
            status_code=202,
        )

    # Synchronous (blocking) mode
    if topic in _running_topics:
        raise HTTPException(409, detail=f"Research for '{topic}' is already running")

    _running_topics.add(topic)
    try:
        orch = ResearchOrchestrator()
        report = await orch.run(topic)
        return JSONResponse(report)
    except Exception as e:
        logger.exception("[API] Research failed for %r", topic)
        raise HTTPException(500, detail=str(e))
    finally:
        _running_topics.discard(topic)


@app.get("/research/history")
async def get_history(limit: int = 20) -> list[dict]:
    orch = ResearchOrchestrator()
    return await orch.get_history(limit)


@app.get("/research/topics")
async def list_topics() -> list[str]:
    orch = ResearchOrchestrator()
    return await orch.get_all_topics()


@app.get("/research/report")
async def get_report(topic: str, limit: int = 1) -> Any:
    orch = ResearchOrchestrator()
    reports = await orch.get_past_reports(topic, limit)
    if not reports:
        raise HTTPException(404, detail=f"No reports found for topic: {topic!r}")
    return reports


@app.get("/research/reports/files")
async def list_report_files() -> list[dict]:
    """List all report JSON files on disk."""
    files = sorted(REPORTS_DIR.glob("*.json"), reverse=True)
    result = []
    for f in files[:50]:
        result.append(
            {
                "filename": f.name,
                "size_bytes": f.stat().st_size,
                "modified": datetime.fromtimestamp(f.stat().st_mtime, timezone.utc).isoformat(),
            }
        )
    return result


@app.get("/research/reports/files/{filename}")
async def get_report_file(filename: str) -> Any:
    """Return the content of a specific saved report JSON file."""
    # Security: only allow .json files in REPORTS_DIR
    if not filename.endswith(".json") or "/" in filename or "\\" in filename:
        raise HTTPException(400, detail="Invalid filename")
    path = REPORTS_DIR / filename
    if not path.exists():
        raise HTTPException(404, detail="File not found")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/scheduler/jobs")
async def list_scheduled_jobs() -> list[dict]:
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append(
            {
                "id": job.id,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            }
        )
    return jobs


# ── Dev runner ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    from config import API_HOST, API_PORT

    uvicorn.run("api:app", host=API_HOST, port=API_PORT, reload=True)
