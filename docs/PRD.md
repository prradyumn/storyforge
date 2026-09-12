# PRD — StoryForge

*Requirements-to-Backlog agentic workflow. Owner: Pradyumn Awasthi. Status: v0.1 shipped.*

## 1. Problem

A business analyst's first week on any initiative is the same: read the
discovery notes, pull out what is actually being asked for, write it up as
requirements, break it into stories a team can pick up, and go back to the
stakeholders with the questions the notes did not answer. It is 60–70% of a
BA's time on a new engagement and it is where scope goes wrong — a requirement
nobody actually said, a "should" upgraded to a "must", a goal with no story
against it.

LLMs are good at the drafting part and bad at the discipline part: they invent,
they smooth over ambiguity, and they produce stories that read well and cannot
be tested. The product problem is not "generate stories". It is **generate
stories a delivery team would accept, and make every one of them traceable to
something a stakeholder said.**

## 2. Users

| User | Job to be done | What they need from the output |
|---|---|---|
| Business analyst / AI BA | Turn a transcript into a first-cut BRD and backlog in an hour, not a week | Traceability to the notes; a clear list of open questions to take back |
| Product owner | Get a sprint-ready backlog with acceptance criteria | INVEST-checked stories, Gherkin ACs with the real numbers in them, Jira issues created |
| Engineering lead | Understand scope and integrations before estimating | Requirement types (integration / NFR / compliance) called out; constraints surfaced |
| Sponsor | Confidence that the backlog covers the goals | A coverage note and gap list in plain language |

## 3. Goals and non-goals

**Goals**
1. From raw notes to BRD + backlog + gap report in one run (< 2 minutes on a free-tier model).
2. Every requirement carries a verbatim evidence quote, verified mechanically.
3. Every story links to ≥ 1 requirement; every must/should requirement has ≥ 1 story.
4. Stories are reviewed against INVEST and revised automatically when they fail, with the loop bounded and visible.
5. Push the result into Jira with one click, idempotently.
6. Quality is measured, not asserted: a golden set and an eval that runs in CI.

**Non-goals (v0.1)**
- Replacing stakeholder interviews. The gap report *generates* questions; humans ask them.
- Estimation accuracy — story points are a suggestion.
- Multi-document synthesis, versioned requirement history, or a persistent workspace.
- Fine-tuning. Quality comes from decomposition, context control and guardrails.

## 4. User stories (the product's own backlog)

| ID | Story | Acceptance criteria (abridged) |
|---|---|---|
| SF-1 | As a BA, I want to paste notes and get a structured brief, so that I can confirm my understanding with the sponsor before writing requirements. | Given ≥ 40 chars of notes, when I run analysis, then I see title, goals, stakeholders, constraints, out-of-scope and open questions. |
| SF-2 | As a BA, I want each requirement to quote the sentence it came from, so that I can defend it in review. | Then every requirement shows an evidence quote and a ✓/✗ traceability badge; ✗ requirements are flagged in the trace, not silently dropped. |
| SF-3 | As a PO, I want INVEST-reviewed stories with Gherkin ACs, so that the team can start without a refinement meeting. | Then each story has role/want/benefit, 1–4 Given/When/Then criteria, INVEST scores and a ready / needs-work badge. |
| SF-4 | As a PO, I want failing stories to be revised automatically, so that I do not hand-fix the same defects every time. | Then failing stories are rewritten using reviewer feedback for ≤ 2 rounds; revised stories are marked with the round. |
| SF-5 | As a BA, I want a gap report with questions, so that I know what to ask next. | Then gaps are typed (uncovered goal, missing NFR, conflict, ambiguity, missing stakeholder) with severity and a question. |
| SF-6 | As a PO, I want to publish to Jira, so that the backlog lives where the team works. | Given Jira credentials, when I publish, then epics and stories are created with parent links and ADF descriptions; re-publishing skips existing issues. Without credentials, dry-run shows the exact payloads. |
| SF-7 | As a BA, I want the BRD and backlog as documents, so that I can circulate them. | Then I can download BRD.md, backlog.md (with traceability matrix) and a Jira CSV. |
| SF-8 | As the builder, I want to measure quality per prompt version, so that changes are justified by numbers. | Then `eval/run_eval.py` reports recall, precision, traceability, story pass rate, etc. per version, and CI runs it on the stub backend. |

## 5. Success metrics

Measured on the golden set (`eval/`), reported in `eval/DECISIONS.md`:

| Metric | Target v0.1 |
|---|---|
| Requirement recall vs labelled set | ≥ 0.85 |
| Traceability rate (evidence found in notes) | ≥ 0.95 |
| Distractor leakage (anecdotes becoming requirements) | ≤ 0.10 |
| Story pass rate after loop (reviewer + guardrails) | ≥ 0.80 |
| Generic-role stories ("as a user") | 0 |
| Schema repairs per run | ≤ 1 |
| Wall time per transcript (free tier) | ≤ 120 s |

## 6. Constraints and decisions

- **Zero paid APIs.** Groq (Llama 3.3 70B) primary, Gemini 2.0 Flash fallback. This is a product constraint (cost per analysis must round to zero for a portfolio tool) and it forces the guardrails to be deterministic rather than "ask a bigger model".
- **No SDKs.** Every integration (Groq, Gemini, Jira) is plain HTTPS + JSON so the request shapes are visible and testable.
- **Offline by default in tests.** The stub backend makes the whole pipeline runnable in CI with no secrets.
- **Versioned prompts.** `prompts/v1..v3` are immutable; changing a prompt means a new version and a new eval row.

## 7. Risks

| Risk | Mitigation |
|---|---|
| Model invents plausible requirements | Verbatim evidence + string-match guardrail; flagged in UI and trace |
| Reviewer is lenient | Deterministic checks can fail a story the model passed; pass needs both |
| Free-tier rate limits | Router retries with backoff and fails over to Gemini; eval records failures |
| Keyword rubric in eval is gameable | Rubric is fixed before prompt iteration; DECISIONS.md records every change and its effect |
| Jira team-managed projects reject some fields | Publisher retries without `priority`; dry-run shows payloads before anything is sent |

## 8. Milestones

| Week | Deliverable | Status |
|---|---|---|
| 1 | Schemas, agents, stub backend, tests | done |
| 1 | Web UI, API, CLI, Jira publisher | done |
| 1 | Golden set (8 domains), eval harness | done |
| 2 | Live evals, prompt v1→v3 iteration, DECISIONS.md | done |
| 2 | Jira live publish, hosted demo, README | done |
| later | Multi-doc input, requirement versioning, PostHog usage analytics | not started |
