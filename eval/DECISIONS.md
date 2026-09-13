# Decisions — what was measured, what changed, and why

Every number below comes from `eval/results/*.json`, produced by
`eval/run_eval.py` on the golden set in `eval/golden/`. Nothing here is
estimated. Where a number is missing, it was not measured.

## 0. How the eval works, and its limits

- **Golden set.** 8 synthetic discovery transcripts (350–560 words, 4 speakers
  each) across retail, HR, fintech, healthcare, logistics, edtech, SaaS billing
  and hospitality. Each is labelled with 9–12 expected requirements (83 total),
  2 distractor sentences (complaints/anecdotes with no ask, 16 total), explicit
  out-of-scope statements and constraints.
- **Rubric.** A produced requirement matches an expected one when *every*
  concept group in the label's `must_mention` appears in the produced
  statement + evidence (case-insensitive). Concept groups are short and specific
  (numbers, system names, nouns). The rubric was written before any prompt was
  tuned and has not been changed since.
- **What it is good at.** Recall (did the model find the ask?), traceability
  (is the evidence quote really in the notes? — pure string matching),
  distractor leakage, and story-quality checks that are deterministic (Gherkin
  shape, role specificity, coverage of must/should requirements).
- **What it is bad at.** Precision. If the model splits one labelled
  requirement into two sensible halves, the rubric counts neither half as a
  match (each half lacks one concept group). So "precision" here is a
  *strictness-of-decomposition* signal, not a hallucination signal — that is
  what traceability is for. Read the two together.
- **Stub baseline.** `stub` is an offline heuristic backend (sentence
  splitting on modal verbs). It exists so tests and CI run without keys; it
  also anchors the table — a model has to beat regex.

## 1. Provider decisions (Sep 2026, free tiers only)

| Option | What happened | Decision |
|---|---|---|
| Groq `llama-3.3-70b-versatile` | No longer offered on the account | — |
| Groq `groq/compound` | Answers JSON, no daily token cap on paper. In practice each request consumed 25–60K tokens internally (its own reasoning/tool loop), tripping its 70K/min cap and llama-4-scout's 30K/min on nearly every call. Two full eval attempts: 0/8 cases completed. | **Rejected** |
| Groq `openai/gpt-oss-120b`, `gpt-oss-20b`, `qwen3.x-27b` | 8K tokens/min, 200K tokens/day each — a single story-writer call is ~5–7K tokens. Only viable by spreading cases across models and trimming review rounds. Kept as the fallback plan in `scripts/run_live_evals.sh`. | Fallback |
| Gemini `gemini-2.5-flash` | Free tier ran the full 8-case v3 matrix in ~35 minutes with no rate-limit failures; one read timeout at 60 s (fixed by raising the client timeout to 180 s). | **Primary** |

Consequence for the product: the router order is `gemini,groq`, and the
Groq client gained a client-side tokens-per-minute throttle and exponential
back-off — not because Groq is worse, but because its free-tier limits are
tight enough that "retry on 429" is not a strategy.

## 2. Prompt versions

| Version | What changed | Why |
|---|---|---|
| v1 | One-paragraph task descriptions. No evidence rule, no INVEST detail, no role rule. | The naive baseline anyone would write first. |
| v2 | Adds: verbatim-evidence requirement, MoSCoW definitions, INVEST scoring rules, "observable outcome" rule for Gherkin, pass threshold. Still no context engineering — same inputs as v1. | Tests how far prompt *wording* alone goes. |
| v3 | Adds: per-agent context (the story writer never sees the raw notes; the reviewer gets requirements + stories only), explicit role rule ("never the bare word user"), threshold-with-rule guidance, duplicate/conflict detection, gap taxonomy, plain-language coverage note. | Tests whether *what the model sees* matters more than how it is asked. |
| v4 | Requirements prompt only: anecdotes are not asks; constraints are not requirements; keep a threshold with its rule; no goal restatements; expect 8–15 requirements. Other four prompts identical to v3. | Motivated by the v3 failure analysis below. Single-variable change so the effect can be attributed. |

## 3. Results

<!-- results-table:start -->
Full matrix on `gemini-2.5-flash`, 2 review rounds, 8 transcripts, same
golden set and rubric for every row. v3 is the shipped default; v4 is the
requirements-prompt revision from §2. The README table is generated from the
same files by `scripts/render_eval_table.py`.

| Metric | stub baseline | v1 | v2 | v3 (shipped) | v4 |
|---|---|---|---|---|---|
| Requirement recall | 74% | 81% | **87%** | 82% | 82% |
| Requirement precision (strict) | 70% | 59% | 63% | 57% | **75%** |
| Requirements produced (83 labelled) | 90 | 168 | 155 | 200 | **95** (7 cases, 71 labelled) |
| Traceability (evidence verbatim in notes) | 100% | 74% | 99.4% | **99.5%** | 97.9% |
| Evidence quotes below the 0.82 guardrail | 0 | 44 | 1 | 1 | 2 |
| Distractor leakage (of 16) | 6% | 25% | 12% | 25% | **7%** (1 / 14) |
| Priority accuracy (MoSCoW) | 57% | **93%** | 83% | 82% | 88% |
| Type accuracy | 57% | 82% | **86%** | 79% | **86%** |
| Must/should requirements with ≥ 1 story | 74% | 76% | **82%** | 76% | 80% |
| Stories sprint-ready after loop | 71% | 35% | 77% | **85%** (93 / 109) | 84% (76 / 90) |
| Gherkin-clean stories | 100% | 75% | 95% | **98%** | 96% |
| Generic "as a user" stories | 0% | 1% | **0%** | **0%** | **0%** |
| Out-of-scope recall | 0% | 50% | **62%** | **62%** | 57% |
| Schema repairs | 0 | 0 | 3 | **0** in 68 calls | 0 (but see the HR failure below) |
| Stories revised by the loop | 116 | 153 | 85 | 83 | 69 |
| Mean latency / tokens per transcript | 0 s | 298 s / 95.6K | 254 s / 90.9K | 245 s / 88.7K | 240 s / 85.7K |

v4 numbers are over 7 of the 8 transcripts: the HR case failed in the
stories agent because both providers returned JSON the repair pass could not
fix (`Expecting ',' delimiter`). It is re-run and the row updated when it lands;
until then the v4 column is not strictly comparable on the story-side metrics.

Three things the matrix says, in order of how much they mattered:

**v1 → v2 is the big jump, and it is almost entirely the evidence rule.**
Asking for a *verbatim* quote took traceability from 74% to 99.4%. Under v1
the model paraphrased freely — 44 of 168 evidence quotes fell below the
guardrail threshold, and in the HR case only 4 of 21 requirements could be
traced to the notes at all. The same version adds INVEST scoring rules and the
"observable outcome" rule for Gherkin, which is why sprint-ready stories more
than doubled (35% → 77%) and Gherkin validity went from 75% to 95%. v1 is what
a one-paragraph prompt gets you: it *looks* fine and a third of it cannot be
checked.

**v2 → v3 traded requirements quality for story quality.** v3 changed what
each agent *sees*: the story writer works from approved requirements instead
of the raw notes, and the reviewer gets requirements + stories only. That is
where the story-side gains come from — sprint-ready 77% → 85%, Gherkin 95% →
98%, and the loop had less to fix (85 → 83 revisions with more stories
passing first time). But v3 also rewrote the requirements prompt with more
guidance (threshold-with-rule, duplicate and conflict detection), and the
model responded by producing *more*: 200 requirements against 83 labelled,
versus 155 under v2. More output meant more splitting (precision 63% → 57%),
more inference (distractor leakage 12% → 25%, HR case 2 of 2 leaked) and
slightly lower recall (87% → 82%, because split halves stop matching the
rubric). Nothing hallucinated — traceability held at 99.5% — but a PO would
have to merge a fifth of it in refinement.

**Priority accuracy went the other way from everything else.** v1 scored 93%
on MoSCoW with no MoSCoW definitions in the prompt; adding definitions (v2,
v3) cost 10 points. The likely reason: the labelled priorities follow the
stakeholders' *language* ("must", "we need", "would be nice"), and the
definitions pushed the model to reason about business value instead of
transcribing intent. That is arguably better BA practice and worse rubric
performance; it is flagged rather than fixed.

So v4 was a single-variable change to the requirements prompt only, keeping
v3's context engineering (which the story metrics say is right) and
targeting the v3 regression on the requirements side. Section 4 lists the
specific failures it addressed, and §4b what happened.

**v4 did what it was designed to do.** The requirements agent produced 95
requirements for 71 labelled ones (1.3×) instead of v3's 2.4×; strict
precision rose from 57% to 75% and distractor leakage fell from 25% to 7% —
the single leak is one logistics anecdote. Recall held at 82%, so the
tighter prompt did not buy precision by dropping real asks. Priority and
type accuracy recovered most of what v2 and v3 had lost. Story-side metrics
were unchanged within noise (84% vs 85% sprint-ready), which is what a
change to one prompt out of five should look like.

**What it cost.** Two evidence quotes in the returns case fell below the
0.82 guardrail (scores 0.69 and 0.73): the stakeholder said customers should
get an email "at each step: item received, refund approved, refund issued",
and the model split that into per-step requirements, each quoting a
*reassembled* fragment ("Customers should get an email at each step: refund
issued.") rather than a verbatim span. Splitting was correct; the quote was
not. The v3 instruction "one requirement per sentence" is gone in v4 and this
is the side-effect. A v5 rule would be: when one sentence yields several
requirements, every one of them quotes the whole sentence. Out-of-scope recall
also dropped 62% → 57% (one fewer exclusion caught), which is within the
noise of a 14-item denominator but is noted.

<!-- results-table:end -->

## 4. Failure analysis on v3 (what the numbers hide)

Read from the saved outputs, not from the aggregate.

**Traceability held.** 124 of the first 125 produced requirements quoted the
notes verbatim (score 1.0); the one miss scored 0.79 — a light paraphrase, not
an invention. The string-match guardrail is doing what it was built for, and
the model learned to respect it from the prompt alone.

**Over-splitting is the main precision cost.** HR case: 25 produced vs 12
labelled. "Flag overtime after 30 minutes at 1.5x" became two requirements
(R-015 threshold, R-016 rate); "pull biometric punches" and "integrate with
biometric scanners" both appeared; the initiative itself ("consolidate
attendance and leave") was emitted as R-001. None of these are hallucinations
— all trace — but a PO would merge them in refinement.

**Constraints promoted to requirements.** "8 lakh budget" and "live before the
April audit" appeared as `non_functional` / `must` requirements. They belong
in the brief (where the intake agent had already put them).

**Anecdotes became asks.** The two HR distractors — a complaint about WhatsApp
screenshots and a story about redoing payroll after an edited record — became
R-021 (track approver identity) and R-008 (lock data after export), both
`must`. These are *reasonable inferences*, which is exactly the problem: a
requirements document should not contain reasonable inferences presented as
stakeholder asks. This is the classic BA failure mode, reproduced by a model.

**Out-of-scope recall was uneven** (3 of 5 in the first five cases): the
intake agent sometimes recorded an exclusion as a constraint rather than in
`out_of_scope`.

Each of these is a prompt rule in v4. The measurement of v4 against the same
rubric is what decides whether they helped.

## 4b. v4 failure analysis

Read from `eval/results/gemini_v4_*.json`.

**The HR case did not complete.** The stories agent received a response
that was not valid JSON from Gemini, retried, then failed over to Groq, which
also produced malformed JSON; the one repair pass each is allowed did not fix
it and the pipeline surfaced the error rather than shipping a partial
backlog. That is the intended behaviour — a half-backlog silently published
to Jira would be worse — but it means the default of one repair attempt is
too tight for a 40-story output. Options, in order of preference: raise the
repair budget to two for the stories agent only; ask for the stories in two
halves when the requirement count exceeds ~20; or fall back to the previous
round's stories with the failing ones marked. Not changed yet; the case is
re-run first so the row can be compared like for like.

**Fintech: 20 requirements for 10 labelled, 5 of 11 stories sprint-ready.**
Two different things went wrong here. The requirements agent split
faithfully but finely — "OFAC match → freeze, route to compliance, never
auto-approve" became R-009, R-010 and R-011 — so precision suffered without
anything being invented. The story failures are a different cause: all six
failing stories scored **1 on Testable** with the same reviewer note, that the
acceptance criteria describe internal actions ("sends the applicant's details
to the sanctions screening service", "stores the full Experian payload")
rather than outcomes a tester can observe. The stories prompt is unchanged
since v2, so this is not a v4 regression; it is an integration-heavy domain
exposing that the "observable outcome" rule has no example of *how* to phrase
an integration criterion (e.g. "Then the application shows status *Screening
complete* within 60 s"). That is a stories-prompt change for v5, and it was
found by reading the reviewer's issues, not the aggregate.

**Logistics: the one leak.** The distractor "Last month we had a rider go
completely off-route for two hours and nobody noticed until the customer
called to complain, that shouldn't be able to happen again" became R-012,
"alert operations personnel when a rider deviates significantly from their
assigned route". The v4 rule says anecdotes are not asks — but this one ends
with "that shouldn't be able to happen again", which is as close to an ask as
an anecdote gets. The label calls it a distractor because the stakeholder
never said what should happen; the model chose the obvious remedy. A human BA
would probably have written it down too, then asked. Arguably the label is
harsh; it stays, because changing labels after seeing results is how evals
stop meaning anything.

## 5. Things that were wrong before they were right

- **First live run design.** `groq/compound` was chosen because it had no
  daily token cap. The cap that mattered was per-minute, and the model's
  internal token use made it unusable. Two eval attempts were lost before the
  provider was switched — the lesson is to probe a provider with a *realistic*
  request, not a 10-token ping.
- **Retry strategy.** The first Groq client retried 429s with the wait the API
  suggested. Under a sliding window that suggestion is optimistic; six retries
  in a row failed. Replaced with a client-side token window that paces
  requests *before* sending, plus exponential back-off as a safety net.
- **Python version.** The code used 3.11-only features (`StrEnum`,
  `datetime.UTC`); the Mac that had to run the evals had 3.10. Made 3.10
  compatible rather than asking for an upgrade.

## 6. What I would measure next

- **A human-judged sample.** 20 stories rated by a PO for "would you accept
  this into a sprint as written?" — the eval's `story_pass_rate` is the
  reviewer *agent's* opinion plus deterministic checks, not a human's.
- **Rubric tolerance for splits.** A secondary precision that credits a
  produced requirement when it matches *any one* concept group of an expected
  requirement — reported alongside, not instead of, the strict one.
- **Cost per transcript** in tokens, by version — v3's richer prompts are not
  free; the trade should be explicit.
