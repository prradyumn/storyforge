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
| Gemini `gemini-2.5-flash` | Free tier covered the whole 24-run matrix in one sitting. | **Primary** |

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
_Pending — filled from eval/results once the live matrix completes._
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
