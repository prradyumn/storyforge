"""HTTP surface. Three endpoints do the work; the rest is diagnostics.

    POST /api/analyze   notes in  -> AnalysisResult (JSON)
    POST /api/publish   result in -> Jira PublishReport (dry_run by default)
    GET  /api/export    result -> BRD.md / backlog.md / jira.csv
    GET  /api/health    which backends and integrations are configured
    GET  /              the single-file web UI
"""
from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

import os
import threading
import time
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

from . import __version__
from .agents.base import AgentError
from .llm.base import LLMError
from .pipeline import analyze
from .prompts import DEFAULT_VERSION, available_versions
from .publishers import jira as jira_pub
from .publishers.markdown import render_backlog, render_brd, render_csv
from .schemas import AnalysisResult

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


class DailyBudget:
    """Public-demo protection: at most N live (non-stub) analyses per UTC day.

    In-memory and per-process, which is exactly right for a single free-tier
    container — it resets on restart and needs no storage."""

    def __init__(self, limit: int):
        self.limit = limit
        self._day = ""
        self._used = 0
        self._lock = threading.Lock()

    def take(self) -> tuple[bool, int]:
        today = time.strftime("%Y-%m-%d", time.gmtime())
        with self._lock:
            if today != self._day:
                self._day, self._used = today, 0
            if self._used >= self.limit:
                return False, 0
            self._used += 1
            return True, self.limit - self._used

    @property
    def remaining(self) -> int:
        today = time.strftime("%Y-%m-%d", time.gmtime())
        return self.limit if today != self._day else max(0, self.limit - self._used)


BUDGET = DailyBudget(int(os.environ.get("STORYFORGE_DAILY_LIVE_LIMIT", "40")))


class Jobs:
    """Background analyses so a slow model run never has to fit inside one HTTP request.

    In-memory, single process: right for one container. Finished jobs expire after an hour."""

    TTL = 3600

    def __init__(self):
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()

    def start(self, fn) -> str:
        import uuid

        job_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._jobs[job_id] = {"status": "running", "started": time.time(), "result": None, "error": None}

        def run():
            try:
                res = fn()
                with self._lock:
                    self._jobs[job_id].update(status="done", result=res, finished=time.time())
            except Exception as e:  # noqa: BLE001 — surfaced to the client as the job's error
                with self._lock:
                    self._jobs[job_id].update(status="error", error=str(e)[:500], finished=time.time())

        threading.Thread(target=run, daemon=True).start()
        self._sweep()
        return job_id

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            return self._jobs.get(job_id)

    def _sweep(self):
        now = time.time()
        with self._lock:
            for k in [k for k, j in self._jobs.items() if j.get("finished") and now - j["finished"] > self.TTL]:
                self._jobs.pop(k, None)


JOBS = Jobs()

app = FastAPI(
    title="StoryForge",
    version=__version__,
    description="Requirements-to-Backlog agentic workflow: stakeholder notes in, INVEST-reviewed user stories out.",
)


class AnalyzeRequest(BaseModel):
    notes: str = Field(min_length=40, max_length=40_000, description="Raw discovery notes / transcript")
    backend: str | None = Field(default=None, description="e.g. 'groq,gemini' or 'stub'. Default from env.")
    prompt_version: str = Field(default=DEFAULT_VERSION)
    max_review_rounds: int = Field(default=2, ge=0, le=4)


class PublishRequest(BaseModel):
    result: AnalysisResult
    dry_run: bool = True
    label: str | None = None


class ExportRequest(BaseModel):
    result: AnalysisResult
    format: Literal["brd", "backlog", "csv"] = "brd"


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "version": __version__,
        "default_backend": os.environ.get("STORYFORGE_BACKEND", "gemini,groq"),
        "backends": {
            "groq": bool(os.environ.get("GROQ_API_KEY")),
            "gemini": bool(os.environ.get("GEMINI_API_KEY")),
            "stub": True,
        },
        "jira_configured": all(os.environ.get(k) for k in ("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN")),
        "jira_project": os.environ.get("JIRA_PROJECT_KEY", "SCRUM"),
        "prompt_versions": available_versions(),
        "default_prompt_version": DEFAULT_VERSION,
        "live_runs_remaining_today": BUDGET.remaining,
        "publish_requires_admin_key": bool(os.environ.get("STORYFORGE_ADMIN_KEY")),
    }


@app.post("/api/analyze", response_model=AnalysisResult)
def api_analyze(req: AnalyzeRequest):
    if req.backend and req.backend != "stub" and os.environ.get("STORYFORGE_LOCK_BACKEND") == "1":
        raise HTTPException(403, "backend selection is disabled on this deployment")
    if req.backend != "stub":
        ok, left = BUDGET.take()
        if not ok:
            raise HTTPException(429, "This demo's daily budget of live model runs is used up — try the stub backend, or come back tomorrow (resets 00:00 UTC).")
    try:
        return analyze(req.notes, backend=req.backend, prompt_version=req.prompt_version, max_review_rounds=req.max_review_rounds)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    except (AgentError, LLMError) as e:
        raise HTTPException(502, f"model call failed: {e}") from e


@app.post("/api/analyze/start")
def api_analyze_start(req: AnalyzeRequest):
    """Start an analysis in the background; poll /api/jobs/{id} for the result."""
    if req.backend and req.backend != "stub" and os.environ.get("STORYFORGE_LOCK_BACKEND") == "1":
        raise HTTPException(403, "backend selection is disabled on this deployment")
    if req.backend != "stub":
        ok, _ = BUDGET.take()
        if not ok:
            raise HTTPException(429, "This demo's daily budget of live model runs is used up — try the stub backend, or come back tomorrow (resets 00:00 UTC).")
    if len(req.notes.strip()) < 40:
        raise HTTPException(422, "notes are too short to analyse")
    job_id = JOBS.start(lambda: analyze(req.notes, backend=req.backend, prompt_version=req.prompt_version, max_review_rounds=req.max_review_rounds))
    return {"job_id": job_id, "status": "running"}


@app.get("/api/jobs/{job_id}")
def api_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "unknown or expired job")
    out = {"job_id": job_id, "status": job["status"], "elapsed_s": round(time.time() - job["started"], 1)}
    if job["status"] == "done":
        out["result"] = job["result"]
    if job["status"] == "error":
        out["error"] = job["error"]
    return out


@app.post("/api/publish")
def api_publish(req: PublishRequest, x_admin_key: str | None = Header(default=None)):
    admin = os.environ.get("STORYFORGE_ADMIN_KEY")
    if not req.dry_run and admin and x_admin_key != admin:
        raise HTTPException(401, "Live publishing on this deployment needs the admin key (X-Admin-Key header). Dry run is open to everyone.")
    try:
        cfg = jira_pub.JiraConfig.from_env() if not req.dry_run else jira_pub.JiraConfig(
            base_url=os.environ.get("JIRA_BASE_URL", "https://example.atlassian.net"),
            email=os.environ.get("JIRA_EMAIL", "dry-run@example.com"),
            api_token="dry-run",
            project_key=os.environ.get("JIRA_PROJECT_KEY", "SCRUM"),
        )
        report = jira_pub.publish(req.result, cfg, dry_run=req.dry_run, label=req.label)
    except jira_pub.JiraError as e:
        raise HTTPException(502, str(e)) from e
    return report


@app.post("/api/export", response_class=PlainTextResponse)
def api_export(req: ExportRequest):
    if req.format == "brd":
        return render_brd(req.result)
    if req.format == "backlog":
        return render_backlog(req.result)
    return PlainTextResponse(render_csv(req.result), media_type="text/csv")


@app.get("/api/examples")
def examples():
    ex_dir = WEB_DIR.parent / "examples"
    out = []
    for p in sorted(ex_dir.glob("*.txt")):
        out.append({"name": p.stem.replace("_", " ").title(), "notes": p.read_text(encoding="utf-8")})
    return out
