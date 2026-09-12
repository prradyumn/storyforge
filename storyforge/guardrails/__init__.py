"""Deterministic checks that run after the LLM, never instead of it.

The principle (borrowed from Homework Saathi): a guardrail must not depend on
the model being honest about itself. So traceability is string matching, not
a self-report; Gherkin validity is a grammar check; INVEST heuristics are
counts. The LLM reviewer adds judgement on top — it does not replace these.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from ..schemas import Backlog, Requirement, Story

# --------------------------------------------------------------------------- #
# Traceability: does each requirement's evidence quote exist in the notes?
# --------------------------------------------------------------------------- #
_WS = re.compile(r"\s+")


def _norm(s: str) -> str:
    s = s.lower().replace("’", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"[^\w\s'\"%$.,-]", " ", s)
    return _WS.sub(" ", s).strip()


def trace_score(evidence: str, source: str) -> float:
    """1.0 if the quote is a verbatim substring (after whitespace/case
    normalisation); otherwise the best fuzzy ratio against a sliding window of
    the source, so light paraphrase still scores high and invention scores low."""
    ev, src = _norm(evidence), _norm(source)
    if not ev:
        return 0.0
    if ev in src:
        return 1.0
    n = len(ev)
    if n >= len(src):
        return SequenceMatcher(None, ev, src).ratio()
    best = 0.0
    step = max(1, n // 4)
    for i in range(0, len(src) - n + 1, step):
        window = src[i : i + n + n // 2]
        r = SequenceMatcher(None, ev, window).quick_ratio()
        if r > best:
            r = SequenceMatcher(None, ev, window).ratio()
            best = max(best, r)
            if best > 0.98:
                break
    return round(best, 3)


def check_traceability(requirements: list[Requirement], notes: str, threshold: float = 0.82) -> list[str]:
    flags = []
    for r in requirements:
        r.trace_score = trace_score(r.evidence, notes)
        r.traceable = r.trace_score >= threshold
        if not r.traceable:
            flags.append(f"{r.id}: evidence not found in notes (score {r.trace_score})")
    return flags


# --------------------------------------------------------------------------- #
# Gherkin validity
# --------------------------------------------------------------------------- #
_VAGUE = re.compile(r"\b(works|properly|correctly|appropriately|as expected|user[- ]friendly|fast|easy|etc\.?)\b", re.I)


def gherkin_issues(story: Story) -> list[str]:
    issues = []
    for i, ac in enumerate(story.acceptance_criteria, start=1):
        for part, text in (("given", ac.given), ("when", ac.when), ("then", ac.then)):
            t = text.strip()
            if len(t) < 6:
                issues.append(f"AC{i}.{part} too short")
            if re.match(rf"^{part}\b", t, re.I):
                issues.append(f"AC{i}.{part} repeats the keyword")
        if _VAGUE.search(ac.then):
            issues.append(f"AC{i}.then is not observable ('{_VAGUE.search(ac.then).group(0)}')")
        if not re.search(r"\d|\b(displays?|shows?|returns?|sends?|receives?|creates?|records?|rejects?|within|equals?|contains?|is|are|marked|status|error|message|email|list|redirect|saved|stored|visible|appears?)\b", ac.then, re.I):
            issues.append(f"AC{i}.then has no observable outcome verb")
    return issues


# --------------------------------------------------------------------------- #
# Story hygiene: template conformance, size, traceability to requirements
# --------------------------------------------------------------------------- #
def story_issues(story: Story, requirement_ids: set[str]) -> list[str]:
    issues = gherkin_issues(story)
    if len(story.i_want.split()) > 30:
        issues.append("i_want is over 30 words — probably more than one story")
    if re.search(r"\b(and|or)\b.*\b(and|or)\b", story.i_want, re.I) and len(story.i_want.split()) > 18:
        issues.append("i_want chains several capabilities with and/or")
    if story.as_a.lower() in {"user", "the user", "a user"} and len(story.as_a) <= 8:
        issues.append("as_a is the generic 'user' — name the role")
    if not story.so_that or len(story.so_that.split()) < 3:
        issues.append("so_that is missing or trivial")
    if any(rid not in requirement_ids for rid in story.requirement_ids):
        issues.append("references an unknown requirement id")
    if not story.requirement_ids:
        issues.append("no requirement linked — untraceable scope")
    return issues


def check_backlog(backlog: Backlog, requirements: list[Requirement]) -> dict[str, list[str]]:
    req_ids = {r.id for r in requirements}
    report = {}
    for s in backlog.stories:
        issues = story_issues(s, req_ids)
        if issues:
            report[s.id] = issues
    covered = {rid for s in backlog.stories for rid in s.requirement_ids}
    for r in requirements:
        if r.priority.value in ("must", "should") and r.id not in covered:
            report.setdefault("__coverage__", []).append(f"{r.id} ({r.priority.value}) has no story")
    return report


# --------------------------------------------------------------------------- #
# Duplicate detection: near-identical stories
# --------------------------------------------------------------------------- #
def duplicate_pairs(stories: list[Story], threshold: float = 0.86) -> list[tuple[str, str]]:
    pairs = []
    sigs = [(s.id, _norm(f"{s.as_a} {s.i_want}")) for s in stories]
    for i in range(len(sigs)):
        for j in range(i + 1, len(sigs)):
            if SequenceMatcher(None, sigs[i][1], sigs[j][1]).ratio() >= threshold:
                pairs.append((sigs[i][0], sigs[j][0]))
    return pairs
