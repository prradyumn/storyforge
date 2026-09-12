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
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
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
        "default_backend": os.environ.get("STORYFORGE_BACKEND", "groq,gemini"),
        "backends": {
            "groq": bool(os.environ.get("GROQ_API_KEY")),
            "gemini": bool(os.environ.get("GEMINI_API_KEY")),
            "stub": True,
        },
        "jira_configured": all(os.environ.get(k) for k in ("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN")),
        "jira_project": os.environ.get("JIRA_PROJECT_KEY", "SCRUM"),
        "prompt_versions": available_versions(),
        "default_prompt_version": DEFAULT_VERSION,
    }


@app.post("/api/analyze", response_model=AnalysisResult)
def api_analyze(req: AnalyzeRequest):
    if req.backend and req.backend != "stub" and os.environ.get("STORYFORGE_LOCK_BACKEND") == "1":
        raise HTTPException(403, "backend selection is disabled on this deployment")
    try:
        return analyze(req.notes, backend=req.backend, prompt_version=req.prompt_version, max_review_rounds=req.max_review_rounds)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    except (AgentError, LLMError) as e:
        raise HTTPException(502, f"model call failed: {e}") from e


@app.post("/api/publish")
def api_publish(req: PublishRequest):
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
