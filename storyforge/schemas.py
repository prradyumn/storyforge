"""Data contracts for the StoryForge pipeline.

Every agent produces one of these models. The LLM is asked for JSON that
matches the model's schema; anything that does not validate is rejected and
repaired (see agents/base.py). This is the first guardrail: no free-text
output ever reaches the backlog.
"""
from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


# --------------------------------------------------------------------------- #
# Intake
# --------------------------------------------------------------------------- #
class Stakeholder(BaseModel):
    name: str = Field(description="Name or role label as it appears in the source")
    role: str = Field(description="Their role, e.g. 'Head of Operations'")
    concerns: list[str] = Field(default_factory=list, description="What they care about most")


class IntakeBrief(BaseModel):
    """Structured summary of the raw input, produced by the Intake agent."""

    title: str = Field(description="Short working title for the initiative")
    business_goals: list[str] = Field(description="Outcomes the business wants, in their words")
    stakeholders: list[Stakeholder] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list, description="Budget, timeline, tech, regulatory")
    out_of_scope: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list, description="Things the notes leave unanswered")
    domain: str = Field(description="One or two words, e.g. 'retail', 'HR', 'fintech'")


# --------------------------------------------------------------------------- #
# Requirements
# --------------------------------------------------------------------------- #
class Priority(StrEnum):
    MUST = "must"
    SHOULD = "should"
    COULD = "could"
    WONT = "wont"


class RequirementType(StrEnum):
    FUNCTIONAL = "functional"
    NON_FUNCTIONAL = "non_functional"
    DATA = "data"
    INTEGRATION = "integration"
    COMPLIANCE = "compliance"


class Requirement(BaseModel):
    id: str = Field(description="R-001, R-002, ...")
    statement: str = Field(description="One atomic, testable requirement in 'The system shall ...' form")
    type: RequirementType
    priority: Priority
    rationale: str = Field(default="", description="Why the stakeholder wants this")
    evidence: str = Field(
        description="Verbatim quote from the source notes that this requirement is derived from"
    )
    stakeholder: str = Field(default="", description="Who asked for it")
    assumptions: list[str] = Field(default_factory=list)
    # Filled by guardrails, not by the LLM
    traceable: bool | None = Field(default=None, description="Did the evidence quote match the source?")
    trace_score: float | None = None

    @field_validator("id")
    @classmethod
    def _id_format(cls, v: str) -> str:
        v = v.strip().upper()
        if not v.startswith("R-"):
            raise ValueError("requirement id must look like R-001")
        return v


class RequirementSet(BaseModel):
    requirements: list[Requirement]


# --------------------------------------------------------------------------- #
# Backlog
# --------------------------------------------------------------------------- #
class AcceptanceCriterion(BaseModel):
    given: str
    when: str
    then: str

    def as_gherkin(self) -> str:
        return f"Given {self.given}\nWhen {self.when}\nThen {self.then}"


class Story(BaseModel):
    id: str = Field(description="S-001, S-002, ...")
    epic_id: str
    title: str = Field(description="Short imperative title")
    as_a: str = Field(description="The user role")
    i_want: str
    so_that: str
    acceptance_criteria: list[AcceptanceCriterion] = Field(min_length=1)
    requirement_ids: list[str] = Field(description="Requirements this story satisfies (traceability)")
    priority: Priority
    story_points: int | None = Field(default=None, ge=1, le=13)
    notes: str = ""

    # Filled by the reviewer loop
    review_round: int = 0

    def as_sentence(self) -> str:
        return f"As a {self.as_a}, I want {self.i_want}, so that {self.so_that}."


class Epic(BaseModel):
    id: str = Field(description="E-01, E-02, ...")
    title: str
    goal: str
    requirement_ids: list[str] = Field(default_factory=list)


class Backlog(BaseModel):
    epics: list[Epic]
    stories: list[Story]


# --------------------------------------------------------------------------- #
# Review (INVEST)
# --------------------------------------------------------------------------- #
class InvestScores(BaseModel):
    independent: int = Field(ge=1, le=5)
    negotiable: int = Field(ge=1, le=5)
    valuable: int = Field(ge=1, le=5)
    estimable: int = Field(ge=1, le=5)
    small: int = Field(ge=1, le=5)
    testable: int = Field(ge=1, le=5)

    @property
    def total(self) -> int:
        return sum(self.model_dump().values())

    @property
    def minimum(self) -> int:
        return min(self.model_dump().values())


class StoryReview(BaseModel):
    story_id: str
    scores: InvestScores
    passed: bool = Field(description="True if the story is ready for a sprint as written")
    issues: list[str] = Field(default_factory=list, description="Concrete problems found")
    fix_instructions: str = Field(default="", description="What the writer should change")


class ReviewReport(BaseModel):
    reviews: list[StoryReview]
    duplicate_pairs: list[tuple[str, str]] = Field(default_factory=list)
    conflict_pairs: list[tuple[str, str]] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Gap analysis
# --------------------------------------------------------------------------- #
class Gap(BaseModel):
    kind: Literal["uncovered_goal", "missing_nfr", "conflict", "ambiguity", "missing_stakeholder"]
    description: str
    severity: Literal["high", "medium", "low"]
    related_ids: list[str] = Field(default_factory=list)
    suggested_question: str = Field(default="", description="What to ask the stakeholder")


class GapReport(BaseModel):
    gaps: list[Gap]
    coverage_note: str = Field(default="", description="One paragraph on how well the backlog covers the goals")


# --------------------------------------------------------------------------- #
# Run trace — what happened, for the UI and the eval
# --------------------------------------------------------------------------- #
class LLMCall(BaseModel):
    agent: str
    model: str
    provider: str
    prompt_version: str
    latency_ms: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    attempt: int = 1
    ok: bool = True
    error: str | None = None


class RunTrace(BaseModel):
    run_id: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    prompt_version: str
    backend: str
    calls: list[LLMCall] = Field(default_factory=list)
    review_rounds: int = 0
    stories_revised: int = 0
    guardrail_flags: list[str] = Field(default_factory=list)

    @property
    def total_latency_ms(self) -> int:
        return sum(c.latency_ms for c in self.calls)

    @property
    def total_tokens(self) -> int:
        return sum((c.prompt_tokens or 0) + (c.completion_tokens or 0) for c in self.calls)


class AnalysisResult(BaseModel):
    """Everything the pipeline produces for one set of notes."""

    brief: IntakeBrief
    requirements: list[Requirement]
    backlog: Backlog
    reviews: ReviewReport
    gaps: GapReport
    trace: RunTrace

    def traceability_matrix(self) -> list[dict]:
        """Requirement -> stories -> evidence. The artefact a BA actually hands over."""
        by_req: dict[str, list[str]] = {r.id: [] for r in self.requirements}
        for s in self.backlog.stories:
            for rid in s.requirement_ids:
                by_req.setdefault(rid, []).append(s.id)
        return [
            {
                "requirement_id": r.id,
                "statement": r.statement,
                "priority": r.priority.value,
                "traceable": r.traceable,
                "stories": by_req.get(r.id, []),
                "evidence": r.evidence,
            }
            for r in self.requirements
        ]
