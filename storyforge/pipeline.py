"""The orchestrator.

    notes ─► Intake ─► Requirements ─► [traceability guardrail]
                                     └► Stories ─► Review ─┐
                                            ▲              │ failing stories + feedback
                                            └──────────────┘  (max N rounds)
                                                           └► Gaps ─► AnalysisResult

The review loop is the "agentic" part: the reviewer's structured feedback is
fed back to the writer, and only the stories that failed are rewritten. The
loop is bounded, every round is recorded in the trace, and deterministic
guardrails run alongside the LLM reviewer so a story can fail on evidence the
model missed.
"""
from __future__ import annotations

import uuid

from . import guardrails
from .agents import GapsAgent, IntakeAgent, RequirementsAgent, ReviewAgent, StoriesAgent
from .llm.router import build_router
from .prompts import DEFAULT_VERSION
from .schemas import AnalysisResult, Backlog, ReviewReport, RunTrace, StoryReview

MAX_REVIEW_ROUNDS = 2
PASS_MIN_SCORE = 3  # every INVEST dimension must be >= this


def _merge_revisions(backlog: Backlog, revised: Backlog, round_no: int) -> int:
    by_id = {s.id: s for s in revised.stories}
    n = 0
    for i, s in enumerate(backlog.stories):
        if s.id in by_id:
            new = by_id[s.id]
            new.review_round = round_no
            new.epic_id = new.epic_id or s.epic_id
            backlog.stories[i] = new
            n += 1
    return n


def _passed(review: StoryReview, hard_issues: list[str]) -> bool:
    return review.passed and review.scores.minimum >= PASS_MIN_SCORE and not hard_issues


def analyze(
    notes: str,
    *,
    backend: str | None = None,
    prompt_version: str = DEFAULT_VERSION,
    max_review_rounds: int = MAX_REVIEW_ROUNDS,
    llm=None,
    on_progress=None,
) -> AnalysisResult:
    """Run the five-agent pipeline.

    `on_progress(event: dict)` — optional; called as each stage starts and finishes
    (``{"stage": "requirements", "status": "done", "count": 12, ...}``) so a UI can show
    the real hand-off between agents instead of guessing from elapsed time."""
    if not notes or len(notes.strip()) < 40:
        raise ValueError("notes are too short to analyse (need at least a few sentences)")

    def emit(stage: str, status: str, **info):
        if on_progress:
            on_progress({"stage": stage, "status": status, **info})

    llm = llm or build_router(backend)
    trace = RunTrace(run_id=uuid.uuid4().hex[:10], prompt_version=prompt_version, backend=llm.name)

    # 1. Intake
    emit("intake", "running")
    brief = IntakeAgent(llm, prompt_version, trace).run(notes=notes)
    emit("intake", "done", goals=len(brief.business_goals), stakeholders=len(brief.stakeholders))

    # 2. Requirements + traceability guardrail
    emit("requirements", "running")
    reqs = RequirementsAgent(llm, prompt_version, trace).run(notes=notes, brief=brief).requirements
    trace.guardrail_flags += guardrails.check_traceability(reqs, notes)
    emit("requirements", "done", count=len(reqs), traceable=sum(1 for r in reqs if r.traceable))

    # 3. Stories
    emit("stories", "running")
    writer = StoriesAgent(llm, prompt_version, trace)
    backlog = writer.run(brief=brief, requirements=reqs)
    emit("stories", "done", epics=len(backlog.epics), stories=len(backlog.stories))

    # 4. Review loop
    reviewer = ReviewAgent(llm, prompt_version, trace)
    report = ReviewReport(reviews=[])
    for round_no in range(1, max_review_rounds + 2):
        emit("review", "running", round=round_no)
        report = reviewer.run(backlog=backlog, requirements=reqs)
        hard = guardrails.check_backlog(backlog, reqs)
        report.duplicate_pairs = list({*map(tuple, report.duplicate_pairs), *guardrails.duplicate_pairs(backlog.stories)})
        trace.review_rounds = round_no

        failing_ids = []
        for rv in report.reviews:
            issues = hard.get(rv.story_id, [])
            if not _passed(rv, issues):
                rv.passed = False
                rv.issues = list(dict.fromkeys(rv.issues + issues))
                failing_ids.append(rv.story_id)
        # Stories the reviewer forgot to mention still get the deterministic checks
        reviewed = {rv.story_id for rv in report.reviews}
        for sid in hard:
            if sid not in reviewed and sid != "__coverage__":
                failing_ids.append(sid)
                trace.guardrail_flags.append(f"{sid}: not reviewed by model; failed deterministic checks")

        emit("review", "done", round=round_no, passed=len(backlog.stories) - len(failing_ids), failing=len(failing_ids))
        if not failing_ids or round_no > max_review_rounds:
            break

        emit("revise", "running", round=round_no, stories=len(failing_ids))
        to_fix = [s for s in backlog.stories if s.id in failing_ids]
        feedback = [rv for rv in report.reviews if rv.story_id in failing_ids]
        revised = writer.run(brief=brief, requirements=reqs, revise=to_fix, reviews=feedback, existing=backlog)
        n = _merge_revisions(backlog, revised, round_no)
        trace.stories_revised += n
        emit("revise", "done", round=round_no, revised=n)

    if "__coverage__" in guardrails.check_backlog(backlog, reqs):
        for msg in guardrails.check_backlog(backlog, reqs)["__coverage__"]:
            trace.guardrail_flags.append("coverage: " + msg)

    # 5. Gaps
    emit("gaps", "running")
    gaps = GapsAgent(llm, prompt_version, trace).run(brief=brief, requirements=reqs, backlog=backlog)
    emit("gaps", "done", count=len(gaps.gaps))

    return AnalysisResult(brief=brief, requirements=reqs, backlog=backlog, reviews=report, gaps=gaps, trace=trace)
