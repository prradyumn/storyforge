# Demo recording script — StoryForge (≈ 2 minutes)

Recorded with Recordly (or any screen recorder) at 1440 × 900, browser zoom 110 %, light theme.
Two tabs open before you press record: the GitHub thread and the StoryForge demo.

## Before you record (10 minutes, off camera)

1. Open <https://storyforge-livid.vercel.app>. Wait until the header says **models online** (the
   backend wakes in under a minute).
2. Load example **Github Thread Family Photo Library**, backend **Live**, prompt **v3** (or v4 if it
   has landed), **2 rounds**. Click **Run analysis**. Let it finish (4–6 minutes for 2,600 words).
   The result is now saved under *Recent runs on this browser*, so you can reopen it instantly on camera.
3. Open the Jira backlog in another tab and sign in:
   <https://pradyumn-storyforge.atlassian.net/jira/software/projects/SCRUM/boards/1/backlog>.
   Have the `STORYFORGE_ADMIN_KEY` value ready to paste (it is in your `.env` on the Mac).
4. Open the source thread: <https://github.com/immich-app/immich/discussions/7362>.
5. Reload the StoryForge tab so it is on the empty state.

## On camera

| Time | Screen | Say (roughly) |
|---|---|---|
| 0:00 | GitHub thread, scroll slowly | "This is a real product discussion: thirty-four people, two years, hundreds of opinions about how a family photo library should be shared. No structure, no requirements, plenty of complaints. This is what a business analyst is handed." |
| 0:15 | StoryForge empty state | "StoryForge turns notes like these into a backlog a delivery team would accept. Five specialised agents, deterministic guardrails after every model call, and every requirement has to quote the sentence it came from." |
| 0:25 | Load the example → backend **Live** → **Run analysis** | "I'll paste the thread in and run it live." Let the **Agent pipeline** panel show *Intake* running for a few seconds. "Intake first: goals, stakeholders, constraints. Then requirements, stories, an INVEST review that sends failing stories back to the writer, then a gap analysis." |
| 0:45 | Cut (trim in Recordly) → click the saved run under **Recent runs** | "The full run takes about five minutes on free-tier models, so here is the finished result." |
| 0:50 | **Brief** tab | "Stakeholders are the real participants. Out of scope and open questions come straight from what they said." |
| 1:00 | **Requirements** tab, hover one trace badge | "Each requirement carries the verbatim quote it came from, and a string-match guardrail checks that the quote really exists in the notes. That score is code, not another model opinion." |
| 1:15 | **Backlog** tab, point at INVEST chips and a *revised r1* badge | "Stories with Given/When/Then criteria. The reviewer scores INVEST; anything below threshold is rewritten with the reviewer's feedback, and the badge shows which stories went through that loop." |
| 1:30 | **Gaps** tab | "What the thread never answered, each with the question to take back to stakeholders." |
| 1:38 | **Run trace** tab | "Every model call, its latency, tokens, and every guardrail flag. Nothing is hidden." |
| 1:45 | **Export & Jira** → **Dry run** → paste admin key → **Publish to Jira** → click a created issue link | "One click creates the epics and stories in Jira Cloud with parent links. Publishing is idempotent: run it twice and the second run skips everything that already exists." |
| 2:00 | Jira board tab, scroll the backlog | "Real issues, real acceptance criteria, traceable back to a GitHub comment." |
| 2:08 | README eval table on GitHub | "And it is measured: eight golden transcripts, four prompt versions, same rubric. Recall, traceability, distractor leakage, sprint-ready rate. The decisions doc explains every change and what it cost." |
| 2:20 | End card | Repo URL · demo URL · your name. |

## Tips

- Keep the cursor still while talking; move it only to point.
- If the live run is already cached from step 2, do **not** run the GitHub example live a second time
  on camera — the free-tier budget is 40 live runs a day and the first run is the one you will show.
- If Jira publishing on camera feels risky, publish off camera first and show the **already existed** result
  — it demonstrates idempotency, which is the more interesting property anyway.
- Export the recording at 1080p; LinkedIn caps at 10 minutes and compresses text heavily, so keep zoom at 110 %.
