# UAT script — StoryForge v0.1

Run through before a release. Each step has an expected result; tick or note a
defect. Steps 1–8 work offline on the stub backend; 9–12 need live keys.

| # | Step | Expected | ✓ |
|---|---|---|---|
| 1 | `pytest -q` | 43 passed, 0 failed | |
| 2 | `ruff check .` | All checks passed | |
| 3 | `STORYFORGE_BACKEND=stub uvicorn storyforge.api:app` → open `/` | UI loads; header says "stub only (no keys)"; example dropdown lists 1+ examples | |
| 4 | Load "Returns Portal" example → Analyse | Results in < 2 s; KPIs show 12 requirements, 12/12 traceable, 12 stories | |
| 5 | Requirements tab | Every row shows an evidence quote and a green ✓ trace badge | |
| 6 | Backlog tab | Each story has role / want / benefit, ≥ 1 Given/When/Then, INVEST chips, "revised r1" badge (stub fails round 1 by design) | |
| 7 | Trace tab | 7 calls: intake, requirements, stories, review, stories, review, gaps; 0 guardrail flags | |
| 8 | Export tab → Dry run | Log lists 13 `POST /rest/api/3/issue` lines (1 epic + 12 stories) and the first payload JSON | |
| 9 | With `GROQ_API_KEY` set, backend "Live" → Analyse on the Returns Portal example | Completes in ≤ 120 s; ≥ 10 requirements; traceability ≥ 90%; roles are specific (no "user") | |
| 10 | Requirements tab (live) | R-002 (30-day window) is `must`; R-008 (page load 2 s) is `non_functional`; exchanges appear in Out of scope on Brief tab | |
| 11 | Gaps tab (live) | ≥ 1 gap with a concrete question; coverage note is readable by a non-technical sponsor | |
| 12 | With `JIRA_*` set → Publish to Jira | Epics and stories created; each story shows its parent epic in Jira; description renders Given/When/Then as a numbered list; second publish reports "already existed" for all | |
| 13 | `python eval/run_eval.py --backend groq --prompt-version v3` | Aggregate recall ≥ 0.85, traceability ≥ 0.95, story pass ≥ 0.80; report written to `eval/results/groq_v3.json` | |
| 14 | `python -m storyforge.cli examples/returns_portal.txt --backend stub --out /tmp/o` | brd.md, backlog.md, jira.csv, backlog.json written; CSV opens in a spreadsheet with 13 rows | |

Sign-off: ____________  Date: ________  Build: `git rev-parse --short HEAD` ________
