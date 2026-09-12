"""The five agents. Each declares exactly which upstream artefacts it sees."""
from __future__ import annotations

from ..schemas import (
    Backlog,
    GapReport,
    IntakeBrief,
    Requirement,
    RequirementSet,
    ReviewReport,
    Story,
    StoryReview,
)
from .base import Agent, dump, tag


class IntakeAgent(Agent[IntakeBrief]):
    name = "intake"
    output_model = IntakeBrief

    def render_user(self, *, notes: str) -> str:
        return tag("notes", notes)


class RequirementsAgent(Agent[RequirementSet]):
    name = "requirements"
    output_model = RequirementSet

    def render_user(self, *, notes: str, brief: IntakeBrief) -> str:
        # Needs the raw notes: every requirement must quote its evidence verbatim.
        return tag("brief", dump(brief)) + "\n\n" + tag("notes", notes)


class StoriesAgent(Agent[Backlog]):
    name = "stories"
    output_model = Backlog
    temperature = 0.3

    def render_user(
        self,
        *,
        brief: IntakeBrief,
        requirements: list[Requirement],
        revise: list[Story] | None = None,
        reviews: list[StoryReview] | None = None,
        existing: Backlog | None = None,
    ) -> str:
        # Does NOT see the raw notes. It works from the requirement statements,
        # which keeps the stories traceable and stops the writer inventing scope.
        compact_reqs = "\n".join(
            f"{r.id} [{r.type.value}/{r.priority.value}] {r.stakeholder or 'stakeholder'}: {r.statement}" for r in requirements
        )
        parts = [
            tag("context", f"Initiative: {brief.title}\nDomain: {brief.domain}\nGoals:\n- " + "\n- ".join(brief.business_goals)),
            tag("requirements", compact_reqs),
        ]
        if revise and reviews and existing:
            parts.append(tag("epics", dump(existing.epics)))
            parts.append(tag("stories_to_revise", dump(revise)))
            parts.append(tag("reviewer_feedback", dump(reviews)))
            parts.append(
                "<instruction>\nRevise ONLY the stories in <stories_to_revise>, keeping their ids and epic_ids. "
                "Apply the reviewer feedback. Return the full Backlog object containing the same epics and ONLY the revised stories.\n</instruction>"
            )
        return "\n\n".join(parts)


class ReviewAgent(Agent[ReviewReport]):
    name = "review"
    output_model = ReviewReport
    temperature = 0.1

    def render_user(self, *, backlog: Backlog, requirements: list[Requirement]) -> str:
        compact_reqs = "\n".join(f"{r.id}: {r.statement}" for r in requirements)
        return tag("requirements", compact_reqs) + "\n\n" + tag("stories", dump(backlog.stories))


class GapsAgent(Agent[GapReport]):
    name = "gaps"
    output_model = GapReport

    def render_user(self, *, brief: IntakeBrief, requirements: list[Requirement], backlog: Backlog) -> str:
        compact_reqs = "\n".join(f"{r.id} [{r.type.value}] {r.statement}" for r in requirements)
        story_summary = "\n".join(f"{s.id} ({', '.join(s.requirement_ids)}): {s.title}" for s in backlog.stories)
        return "\n\n".join(
            [tag("brief", dump(brief)), tag("requirements", compact_reqs), tag("backlog_summary", story_summary)]
        )
