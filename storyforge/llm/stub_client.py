"""A deterministic, offline stand-in for an LLM.

Used by the test-suite, CI and `--backend stub` demos so the whole pipeline
runs end-to-end with no network and no keys. It reads the agent name that
every prompt declares in its first line (`# agent: requirements`) and returns
a schema-valid answer derived from the input text with simple heuristics.

It is intentionally mediocre: the eval harness should show the real models
beating it.
"""
from __future__ import annotations

import re

from .base import Usage

_MODAL = re.compile(r"\b(must|should|need|needs|want|wants|have to|has to|require|requires|shall|can't|cannot)\b", re.I)
_SPEAKER = re.compile(r"^\s*([A-Z][\w .'-]{1,40}?)\s*(?:\(([^)]{2,60})\))?\s*:\s*(.+)$")


def _sentences(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        line = line.strip().lstrip("-•* ")
        if not line:
            continue
        m = _SPEAKER.match(line)
        if m:
            line = m.group(3)
        for s in re.split(r"(?<=[.!?])\s+", line):
            s = s.strip()
            if len(s) > 12:
                out.append(s)
    return out


class StubClient:
    name = "stub"
    model = "stub-heuristics-v1"

    def complete_json(self, system: str, user: str, *, temperature: float = 0.2, agent: str = "") -> tuple[dict, Usage]:
        agent = agent or self._agent_from_prompt(system)
        handler = getattr(self, f"_{agent}", None)
        if handler is None:
            raise ValueError(f"stub has no handler for agent {agent!r}")
        return handler(user), Usage(prompt_tokens=len(system + user) // 4, completion_tokens=200, model=self.model, provider=self.name)

    @staticmethod
    def _agent_from_prompt(system: str) -> str:
        m = re.search(r"^#\s*agent:\s*(\w+)", system, re.M)
        return m.group(1) if m else ""

    # ---- per-agent heuristics ------------------------------------------- #
    @staticmethod
    def _source(user: str) -> str:
        # Agents put the raw notes between <notes> tags (see agents/base.py)
        m = re.search(r"<notes>(.*?)</notes>", user, re.S)
        return m.group(1) if m else user

    def _intake(self, user: str) -> dict:
        src = self._source(user)
        stakeholders = []
        seen = set()
        for line in src.splitlines():
            m = _SPEAKER.match(line.strip())
            if m and m.group(1) not in seen:
                seen.add(m.group(1))
                stakeholders.append({"name": m.group(1), "role": m.group(2) or "stakeholder", "concerns": []})
        goals = [s for s in _sentences(src) if _MODAL.search(s)][:4]
        first = next((line.strip() for line in src.splitlines() if line.strip()), "Untitled initiative")
        return {
            "title": first[:80],
            "business_goals": goals or ["Improve the current process"],
            "stakeholders": stakeholders,
            "constraints": [s for s in _sentences(src) if re.search(r"\b(budget|deadline|by q[1-4]|weeks?|months?|compliance|gdpr)\b", s, re.I)][:3],
            "out_of_scope": [],
            "open_questions": ["Which metric defines success for launch?"],
            "domain": "general",
        }

    def _requirements(self, user: str) -> dict:
        src = self._source(user)
        reqs = []
        for i, s in enumerate([s for s in _sentences(src) if _MODAL.search(s)][:12], start=1):
            reqs.append(
                {
                    "id": f"R-{i:03d}",
                    "statement": "The system shall " + re.sub(r"^(we|i|they|users?|customers?)\s+(also\s+)?(must|should|need|want|have)\s+(to\s+)?(be able to\s+)?", "", s, flags=re.I).rstrip(".") + ".",
                    "type": "non_functional" if re.search(r"\b(second|seconds|uptime|secure|encrypt|load|fast|performance)\b", s, re.I) else "functional",
                    "priority": "must" if re.search(r"\b(must|need|have to|cannot|can't)\b", s, re.I) else "should",
                    "rationale": "",
                    "evidence": s,
                    "stakeholder": "",
                    "assumptions": [],
                }
            )
        return {"requirements": reqs}

    def _stories(self, user: str) -> dict:
        revising = "<reviewer_feedback>" in user
        if revising:
            ids = list(dict.fromkeys(re.findall(r'"id":\s*"(S-\d{3})"', user.split("<stories_to_revise>")[1].split("</stories_to_revise>")[0])))
            rid_of = dict(re.findall(r'"id":\s*"(S-\d{3})".*?"requirement_ids":\s*\[\s*"(R-\d{3})"', user, re.S))
        else:
            ids = list(dict.fromkeys(re.findall(r"\b(R-\d{3})\b", user))) or ["R-001"]
        stories = []
        for i, key in enumerate(ids, start=1):
            rid = rid_of.get(key, "R-001") if revising else key
            sid = key if revising else f"S-{i:03d}"
            m = re.search(rid + r"[^\n]*?:\s*(.+)", user)
            what = (m.group(1) if m else "the requested capability").strip().rstrip(".")
            what = re.sub(r"^The system shall\s+", "", what, flags=re.I)
            stories.append(
                {
                    "id": sid,
                    "epic_id": "E-01",
                    "title": what[:60].capitalize(),
                    "as_a": "operations manager" if revising else "user",
                    "i_want": what,
                    "so_that": "the team spends less time on manual handling" if revising else "I can achieve the business goal",
                    "acceptance_criteria": [
                        {"given": "I am an authenticated user", "when": f"I {what[:80]}", "then": "the return status is displayed as submitted and a confirmation email is sent"}
                    ],
                    "requirement_ids": [rid],
                    "priority": "must",
                    "story_points": 3,
                    "notes": "",
                }
            )
        req_ids = sorted({s["requirement_ids"][0] for s in stories})
        return {"epics": [{"id": "E-01", "title": "Core capability", "goal": "Deliver the requested capability", "requirement_ids": req_ids}], "stories": stories}

    def _review(self, user: str) -> dict:
        blocks = re.findall(r'\{\s*"id":\s*"(S-\d{3})".*?"review_round"', user, re.S)
        reviews = []
        for sid in blocks:
            block = user.split(f'"id": "{sid}"')[1].split('"review_round"')[0]
            # Fail stories whose 'so_that' is the generic placeholder, to exercise the revision loop
            generic = "achieve the business goal" in block or '"as_a": "user"' in block
            reviews.append(
                {
                    "story_id": sid,
                    "scores": {"independent": 4, "negotiable": 4, "valuable": 2 if generic else 4, "estimable": 4, "small": 4, "testable": 3},
                    "passed": not generic,
                    "issues": ["Value statement is generic"] if generic else [],
                    "fix_instructions": "State the concrete outcome for the user in 'so that'." if generic else "",
                }
            )
        return {"reviews": reviews, "duplicate_pairs": [], "conflict_pairs": []}

    def _gaps(self, user: str) -> dict:
        return {
            "gaps": [
                {
                    "kind": "missing_nfr",
                    "description": "No non-functional requirements for performance or availability were stated.",
                    "severity": "medium",
                    "related_ids": [],
                    "suggested_question": "What response time and uptime do you expect at launch?",
                }
            ],
            "coverage_note": "Stub analysis: each stated need maps to one story; non-functional coverage is thin.",
        }
