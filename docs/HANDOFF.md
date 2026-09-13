# StoryForge — project context and handoff

Written 13 Sep 2026 at the end of the build session. Read this first if you are
picking the project up again (a person or an AI assistant). It says what exists,
where it runs, how it is wired, what the UI is built on, and what is still open.

## 1. What StoryForge is

A requirements-to-backlog agentic workflow for product and business analysis
work. Paste discovery notes (meeting transcript, interview, messy forum thread);
five LLM agents produce a brief, atomic requirements with verbatim evidence,
epics and INVEST-reviewed user stories with Given/When/Then criteria, and a gap
report. One click publishes epics and stories to Jira Cloud.

Owner: Pradyumn Awasthi (prradyumn on GitHub). MIT licence.

Live:
- Front end (Vercel, edge, auto-deploys from `main`): https://storyforge-livid.vercel.app
- Backend API (Render free tier, Docker, auto-deploys from `main`): https://storyforge-lsnr.onrender.com — `/api/health`, `/docs`
- Repo: https://github.com/prradyumn/storyforge
- Jira project used by the demo: https://pradyumn-storyforge.atlassian.net (project key `SCRUM`)

## 2. Architecture in one screen

```
notes → Intake → Requirements → [traceability guardrail]
                              └→ Stories → INVEST Review ─┐ failing stories + feedback
                                     ▲                    │ (≤ 2 rounds)
                                     └────────────────────┘
                                                          └→ Gaps → BRD · backlog.md · CSV · Jira
```

| Layer | Where | Notes |
|---|---|---|
| Schemas | `storyforge/schemas.py` | Pydantic v2 contracts every agent output must satisfy. `AnalysisResult` = brief, requirements, backlog, reviews, gaps, trace. |
| Agents | `storyforge/agents/base.py`, `agents/__init__.py` | `base.py`: call → validate → one repair pass. `__init__.py` defines what each agent *sees* (story writer never sees raw notes). |
| Prompts | `storyforge/prompts/v1 … v4/*.md` | Versioned, never edited, only superseded. v3 is the default (`DEFAULT_VERSION`); v4 changes the requirements prompt only. |
| Guardrails | `storyforge/guardrails/__init__.py` | Deterministic: traceability (string match, threshold 0.82), Gherkin shape, role, size, coverage, duplicates. |
| Pipeline | `storyforge/pipeline.py` | Orchestrator, bounded review/revise loop, optional `on_progress(event)` callback used by the UI. |
| LLM clients | `storyforge/llm/` | `gemini_client.py` (primary, gemini-2.5-flash, 180 s timeout), `groq_client.py` (fallback, gpt-oss-120b, client-side TPM throttle), `stub_client.py` (offline heuristics), `router.py` (fallback order from `STORYFORGE_BACKEND`, default `gemini,groq`). httpx only, no SDKs. |
| Publishers | `storyforge/publishers/jira.py`, `markdown.py` | Jira Cloud REST v3 with ADF descriptions, parent epics, idempotent by label + summary, dry-run mode. Markdown BRD, backlog with traceability matrix, CSV. |
| API | `storyforge/api.py` | FastAPI. `POST /api/analyze` (sync), `POST /api/analyze/start` + `GET /api/jobs/{id}` (background thread, progress events), `POST /api/publish` (X-Admin-Key for live), `POST /api/export`, `GET /api/health`, `GET /api/examples`. `DailyBudget` caps live runs per UTC day. |
| CLI | `storyforge/cli.py` | `python -m storyforge.cli notes.txt --backend stub --out out/`, `--from-json` to republish a saved result, `--publish [--dry-run]`. |
| Web UI | `web/index.html` | Single file, no build step, no framework. Served by FastAPI at `/` and by Vercel as static. |
| Eval | `eval/golden/*.json`, `eval/run_eval.py`, `eval/results/`, `eval/DECISIONS.md` | 8 synthetic transcripts, 83 labelled requirements, 16 distractors. Deterministic rubric. One JSON report per backend × prompt version plus one output JSON per case. |
| Tests / CI | `tests/` (47, offline), `.github/workflows/ci.yml`, `ruff` | `pytest -q` and `ruff check .` must pass before every push. |
| Deploy | `Dockerfile` (port 7860), `render.yaml`, `vercel.json` | See §4. |
| Docs | `docs/PRD.md`, `ARCHITECTURE.md`, `UAT.md`, `DEMO.md`, `StoryForge_Overview.pdf`, this file | |

## 3. The web UI — what it is built on and how to change it

`web/index.html` is the entire front end: ~330 lines of CSS, ~120 lines of HTML,
~200 lines of vanilla JS. No bundler, no framework, no dependencies except
Google Fonts. Keep it that way unless there is a strong reason; it is the reason
the UI can be served unchanged from both FastAPI and Vercel.

### Design system (CSS custom properties at the top of the file)

| Token | Value | Use |
|---|---|---|
| `--page` / `--surface` / `--inset` | `#f4f5f7` / `#fff` / `#f8f9fa` | page background, panels, table headers and inset blocks |
| `--ink` / `--ink2` / `--muted` / `--faint` | `#1b2530` / `#3d4a5a` / `#6b7684` / `#98a2ae` | text hierarchy |
| `--line` / `--line2` | `#dde2e8` / `#ebeef2` | borders, row dividers |
| `--brand` / `--brand-soft` | `#0f5c73` / `#e6f0f4` | primary button, active tab underline, epic and story IDs, Gherkin keywords |
| `--bar` / `--bar-ink` / `--bar-muted` | `#16212d` / `#e9edf2` / `#9aa7b6` | top bar and the dark publish log |
| `--ok` `--warn` `--bad` `--info` (+ `-soft`) | greens, ambers, reds, blues | tags: sprint-ready / needs work / trace fail / revised |
| `--sans` / `--mono` | IBM Plex Sans / IBM Plex Mono | text / IDs, Gherkin, trace, tags |
| `--r` | `4px` | radius everywhere; deliberately square |

Layout: 52 px dark top bar (brand + status pills + links) → `.wrap` (max 1360 px) →
`.grid` two columns `400px | 1fr` (stacks under 980 px). Left column: **Source
notes** panel (example picker, textarea, word count, controls, Run) and **Agent
pipeline** panel (five steps, driven by real progress events). Right column:
results panel with a six-cell metric strip, underline tabs (Brief, Requirements,
Backlog, Gaps, Run trace, Export & Jira) and the content area.

Design intent (from the redesign brief): restrained enterprise tool, not a
landing page. No gradients, no glass, no emoji, no purple. Dense tables with
uppercase 11 px headers, monospace for anything identifier-like, colour used
only for status. If you restyle, change tokens first; component CSS is written
against tokens.

### JS structure (all in one `<script>`)

- `init()` — fetches `/api/health` (fills status pills, prompt versions, disables live if no keys; shows "waking the backend" after 4 s because Render sleeps) and `/api/examples`, then `renderRecent()`.
- `$('#run').onclick` — POST `/api/analyze/start`, poll `/api/jobs/{id}` every 300 ms (stub) or 2.5 s (live), call `applyProgress(j.progress)` to animate the pipeline, then `saveRecent()` and `render()`.
- `applyProgress(events)` / `stageLabel(e)` — maps pipeline events (`intake`, `requirements`, `stories`, `review`, `revise`, `gaps`; status `running`/`done` plus counts) onto the five `<li data-s>` rows.
- `render()` — metric strip, tab counts, then one of `brief() reqs() backlog() gaps() trace() exportPanel()` which return HTML strings; `wireExport()` binds download and Jira buttons.
- Recent runs: last five results in `localStorage['sf:recent']`, listed on the empty state, reopenable. Per browser only.
- `esc()` escapes all model output before it hits `innerHTML`. Keep doing that.

### Ideas that were discussed but not built

Dark theme (tokens are already there to add `@media (prefers-color-scheme: dark)`),
keyboard shortcut to run, a diff view between two prompt versions on the same
notes, a real "load a saved JSON" button (the CLI has `--from-json`; the UI only
has recent runs), progress inside the review loop (which stories are being
rewritten), and a proper story title (the model sometimes returns lower-case
fragments like "to see all my photos…" — a prompt fix in the stories prompt).

## 4. Deployment and infrastructure

- **Render** (backend): blueprint `render.yaml`, Docker, free instance, sleeps after 15 idle minutes (first request up to ~1 min). Env vars set in the Render dashboard: `GEMINI_API_KEY`, `GROQ_API_KEY`, `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY`, `STORYFORGE_ADMIN_KEY`, optional `STORYFORGE_DAILY_LIVE_LIMIT` (default 40), `STORYFORGE_LOCK_BACKEND`. Auto-deploy on push works because the Render GitHub app is installed on the repo (it was not at first; the blueprint alone does not install a webhook).
- **Vercel** (front end): `vercel.json` with `framework: null`, `outputDirectory: web`, rewrites `/api/*`, `/docs`, `/openapi.json` to the Render URL. Imported with the "Other" preset. Project `storyforge` under prradyumn's Hobby team. Env vars there are unused placeholders from `.env.example`.
- **Hugging Face Spaces**: `scripts/deploy_hf.sh` still exists but Docker Spaces need PRO as of Sep 2026. Not used.
- **Secrets** live only in `.env` (gitignored) on Pradyumn's Mac at `~/Downloads/storyforge/.env` and in the Render dashboard. Never commit them. `.env.example` lists the names.
- **Network quirk during the build**: the assistant's cloud shell could not reach Gemini, Groq, Atlassian, Render or push to GitHub, so live evals and Jira smoke tests ran from the Mac terminal (`scripts/run_live_evals.sh`, `scripts/jira_smoke.sh`) and pushes went through a git bundle applied on the Mac. From a normal laptop none of this matters: `git push` works.

## 5. Evaluation state

Numbers are in `eval/DECISIONS.md` §3 and the README table (regenerate with
`python scripts/render_eval_table.py --write`). Summary on gemini-2.5-flash, 8
transcripts, 2 review rounds:

| | v1 | v2 | v3 (default) | v4 |
|---|---|---|---|---|
| Requirement recall | 81% | 87% | 82% | 82% |
| Precision (strict) | 59% | 63% | 57% | 75% |
| Traceable | 74% | 99.4% | 99.5% | 98% |
| Distractor leak | 25% | 12% | 25% | 7% |
| Sprint-ready stories | 35% | 77% | 85% | 84% |

v4 was measured on 7 of 8 cases: the HR case failed in the stories agent
(malformed JSON from both providers, repair pass could not fix it). To finish:
`bash scripts/run_live_evals.sh v4` on a machine with keys (it resumes and
redoes only the missing case), copy `eval/results/gemini_v4*.json` into the
repo, rerun the table script, update DECISIONS §3 wording ("7 of 8") and the
`(1 case(s) failed)` label, commit.

Not yet decided: whether to make v4 the default. It is better on requirements
and equal on stories; the argument against is two evidence quotes that fell
below the trace threshold because of sentence splitting (see DECISIONS §4b).

## 6. Known issues and the v5 ideas

1. **Traceability proves the quote exists, not that it supports the requirement.** Public feedback on the launch post made this point well. Planned v5: a second reviewer that sees only the quote and the requirement (never the full notes) and answers "would a reasonable reader write this requirement from this sentence alone". When a requirement needs two sentences, the writer quotes both.
2. **Stories agent JSON failure** on long outputs (HR case, 40+ stories). Options: allow two repair passes for the stories agent, or split the request when requirements > ~20.
3. **Fintech case**: six stories failed Testable=1 because acceptance criteria described internal actions ("sends to Persona API") rather than observable outcomes. The stories prompt needs an example of how to phrase an integration criterion.
4. **Story titles** sometimes arrive as lower-case fragments. Prompt fix.
5. **Free-tier limits**: Gemini free tier handled the eval; Groq's 8K TPM makes it a weak fallback. If Groq is ever primary, the throttle in `groq_client.py` matters.
6. **Email mismatch**: LinkedIn account email is pradyumnawasthi2702@gmail.com, resume and forms use Pradyumnawasthi03@gmail.com. Not a code issue, noted for job applications.

## 7. Everyday commands

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt
cp .env.example .env                        # add keys
uvicorn storyforge.api:app --reload         # http://localhost:8000
STORYFORGE_BACKEND=stub uvicorn storyforge.api:app     # no keys
pytest -q && ruff check .                   # before every commit
python eval/run_eval.py --backend stub      # eval harness offline
bash scripts/run_live_evals.sh v4           # live eval, resumable
bash scripts/jira_smoke.sh                  # publish a saved result twice, second run must skip all
python scripts/render_eval_table.py --write # regenerate README table
python scripts/preflight.py                 # check keys, Jira, models
```

Examples: `examples/*.txt` — four synthetic transcripts plus
`github_thread_family_photo_library.txt`, a real public GitHub discussion
(immich-app/immich #7362, 34 participants, 2,600 words) used for the demo and
the LinkedIn screenshots.

## 8. Related material outside the repo

On Pradyumn's Mac: `~/Downloads/storyforge/linkedin/` (seven screenshots of a real run plus the post text, highlighted variant), `~/Downloads/Job Applications/` (resume PDF and cover letters). The resume source is LaTeX and was built with pdflatex; the StoryForge bullet cites 99.5% traceable, 82% recall, 85% sprint-ready, precision 57%→75% with v4, 47 tests.

## 9. If you want to improve the UI, start here

1. Run locally with the stub backend; load the GitHub-thread example; every tab renders in under two seconds.
2. Change tokens in `:root` first and look at all six tabs before touching component CSS.
3. Keep `esc()` around every model string; keep the page a single file; keep `vercel.json` rewrites in sync if you add API routes.
4. Test at 400 px width; the grid stacks and the metric strip goes to three columns at 700 px.
5. Push to `main`; both Vercel and Render redeploy on their own. Vercel takes ~20 s, Render ~40 s.
