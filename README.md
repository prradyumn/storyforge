# StoryForge

**Stakeholder notes in → INVEST-reviewed user stories out → pushed to Jira.**

An agentic requirements workflow for business analysts. Paste a discovery
transcript; five specialised agents turn it into a structured brief, atomic
requirements with verbatim evidence, epics and stories with Gherkin acceptance
criteria, an INVEST review with an automatic revise loop, and a gap report with
the questions to take back to stakeholders. One click publishes to Jira Cloud.

> The hard part is not generating stories. It is producing stories a delivery
> team would accept — and being able to point at the sentence each one came from.

<!-- demo: __DEMO_URL__ -->

---

## What it does

```
notes ─► Intake ─► Requirements ─► [traceability guardrail]
                                 └► Stories ─► INVEST Review ─┐  failing stories
                                        ▲                     │  + feedback
                                        └─────────────────────┘  (≤ 2 rounds)
                                                              └► Gap analysis ─► BRD · Backlog · Jira
```

| Stage | Agent output | What checks it |
|---|---|---|
| **Intake** | Title, business goals, stakeholders, constraints, out-of-scope, open questions | Schema |
| **Requirements** | Atomic "The system shall…" statements, MoSCoW priority, type, **verbatim evidence quote** | Schema + **string-match traceability** (evidence must exist in the notes) |
| **Stories** | Epics, stories (role / want / benefit), Given-When-Then criteria, requirement links | Schema + Gherkin validity + role/size/coverage checks |
| **Review** | INVEST scores 1–5, pass/fail, concrete fix instructions, duplicates, conflicts | Pass = model says pass **and** every score ≥ 3 **and** deterministic checks clean |
| **Revise loop** | Only failing stories rewritten with the reviewer's feedback | Bounded to 2 rounds; every round in the trace |
| **Gaps** | Uncovered goals, missing NFRs, conflicts, ambiguities, missing stakeholders — each with a question to ask | Schema |

Outputs: `BRD.md`, `backlog.md` with a **traceability matrix** (requirement ↔ stories ↔ evidence), Jira-importable CSV, raw JSON, and live **Jira Cloud** epics + stories via REST API v3.

## Measured, not asserted

Quality is scored on a golden set of 8 synthetic discovery transcripts across
8 domains (retail, HR, fintech, healthcare, logistics, edtech, SaaS billing,
hospitality) — 83 labelled requirements and 16 distractor sentences that sound
like requirements but are not. The rubric is deterministic (keyword groups +
string matching), fixed before any prompt was tuned.

<!-- eval-table:start -->
| Backend · prompts | Req. recall | Req. precision | Traceable | Distractor leak | Priority acc. | Must/should covered | Stories sprint-ready | Generic 'user' role | Out-of-scope recall | Mean s / transcript |
|---|---|---|---|---|---|---|---|---|---|---|
| `stub` · v3 | 74% | 70% | 100% | 6% | 57% | 74% | 71% | 0% | 0% | 0 |
| `gemini` · v3 | 82% | 57% | 99.5% | 25% | 82% | 76% | 85% | 0% | 62% | 245 |
_8 transcripts · lower is better for distractor leak and generic role · stub = offline heuristic baseline (it copies sentences verbatim, which the keyword rubric rewards on precision; read precision together with traceability)._
<!-- eval-table:end -->

Full methodology and every prompt change with its before/after numbers:
[`eval/DECISIONS.md`](eval/DECISIONS.md).

## Run it

```bash
git clone https://github.com/prradyumn/storyforge && cd storyforge
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # add GEMINI_API_KEY (free at aistudio.google.com) and/or GROQ_API_KEY (console.groq.com)

uvicorn storyforge.api:app --reload        # → http://localhost:8000
```

No keys? Everything still runs on the offline stub backend:

```bash
STORYFORGE_BACKEND=stub uvicorn storyforge.api:app
python -m storyforge.cli examples/returns_portal.txt --backend stub --out out/
pytest -q                                  # 43 tests, no network
python eval/run_eval.py --backend stub     # the eval harness end to end
```

### Publish to Jira

Set `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY` in `.env`, then use the **Export & Jira** tab or:

```bash
python -m storyforge.cli notes.txt --publish --dry-run   # shows the exact REST payloads
python -m storyforge.cli notes.txt --publish             # creates epics + stories
```

Publishing is idempotent (label + summary); re-running the same analysis skips issues that already exist.

### Deploy the demo (Hugging Face Spaces, free)

```bash
bash scripts/deploy_hf.sh      # creates the Space, pushes HEAD, sets secrets, waits for the build, runs preflight
```

Public-demo guards: `STORYFORGE_DAILY_LIVE_LIMIT` caps live model runs per day (stub is unlimited) and
`STORYFORGE_ADMIN_KEY` is required for live Jira publishing (dry run is open).

### API

```
POST /api/analyze   {"notes": "...", "backend": "gemini,groq", "prompt_version": "v3", "max_review_rounds": 2}
POST /api/publish   {"result": <AnalysisResult>, "dry_run": true}
POST /api/export    {"result": <AnalysisResult>, "format": "brd" | "backlog" | "csv"}
GET  /api/health
```
Interactive docs at `/docs`.

## Repository map

```
storyforge/
  schemas.py            Pydantic contracts every agent must satisfy
  agents/               five agents; base.py = call → validate → repair loop; __init__.py = what each agent sees
  prompts/v1 … v4/      versioned system prompts — never edited, only superseded
  guardrails/           deterministic checks: traceability, Gherkin, role, size, coverage, duplicates
  pipeline.py           the orchestrator and the bounded review/revise loop
  llm/                  groq, gemini, stub clients + fallback router (httpx, no SDKs)
  publishers/           Jira Cloud v3 (ADF descriptions, idempotent), Markdown BRD/backlog, CSV
  api.py · cli.py       FastAPI service and command line
web/index.html          single-file UI: brief, requirements, backlog, gaps, trace, export/Jira
eval/
  golden/*.json         8 transcripts, 83 labelled requirements, distractors, out-of-scope, constraints
  run_eval.py           deterministic scorer; one JSON report per backend × prompt version
  DECISIONS.md          what was measured, what changed, and why
docs/
  PRD.md                the product spec for StoryForge itself
  ARCHITECTURE.md       why five agents, context engineering table, guardrail design
  UAT.md                14-step acceptance script
tests/                  43 tests, offline
```

## Design decisions in one breath

Decompose instead of one mega-prompt, so each agent can be given only the
context it needs (the story writer never sees the raw notes — it works from
approved requirements, which is what keeps scope honest). Make the model quote
its evidence and check the quote with code, not with another model call. Let a
reviewer fail stories and feed only the failures back, bounded. Version every
prompt and measure every version against the same fixed rubric. Zero paid APIs,
so that "ask a bigger model" is never the fix.

## Built with

Python 3.10+ · FastAPI · Pydantic v2 · httpx · Gemini 2.5 Flash · Groq (gpt-oss-120b) · Jira Cloud REST v3 · pytest · ruff · GitHub Actions · Docker.
Developed with Claude Code; every design decision and prompt iteration is documented in `eval/DECISIONS.md`.

MIT © 2026 Pradyumn Awasthi
