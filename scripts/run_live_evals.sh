#!/usr/bin/env bash
# One command to run the live evaluation on a machine that can reach api.groq.com.
#
#   bash scripts/run_live_evals.sh            # v3, v2, v1 on all 8 cases, resumable
#   bash scripts/run_live_evals.sh v3         # one version only
#
# Model choice (measured, Sep 2026): Gemini 2.5 Flash's free tier comfortably
# covers all 24 runs, so it is preferred when GEMINI_API_KEY is set. Groq's free
# tier cannot: groq/compound burns 25-60K tokens per request internally and
# trips its own 70K/min cap; the 200K-tokens/day models are capped at 8K/min.
# Without a Gemini key the script spreads cases across those four models so each
# case still sees the SAME model for v1, v2 and v3 (rounds and tokens trimmed).
set -euo pipefail
cd "$(dirname "$0")/.."

if [ $# -gt 0 ]; then VERSIONS=("$@"); else VERSIONS=(v3 v2 v1); fi

# --- python env -------------------------------------------------------------
if [ ! -x .venv/bin/python ]; then
  if command -v uv >/dev/null 2>&1; then
    uv venv --python 3.11 .venv >/dev/null 2>&1 || uv venv .venv >/dev/null
    uv pip install -q -r requirements-dev.txt --python .venv/bin/python
  else
    python3 -m venv .venv
    .venv/bin/pip install -q -r requirements-dev.txt
  fi
fi
PY=.venv/bin/python
[ -f .env ] || { echo "✖ .env missing — copy .env.example and add GROQ_API_KEY"; exit 1; }
set -a; . ./.env; set +a
export STORYFORGE_VERBOSE=1

# --- pick a model plan --------------------------------------------------------
probe_groq() {  # $1 = model  → 0 if a tiny JSON call works
  GROQ_MODEL="$1" $PY - <<'EOF' >/dev/null 2>&1
from storyforge.llm.groq_client import GroqClient
p, u = GroqClient().complete_json("Return JSON only.", 'Return {"ok": true}')
assert p.get("ok") is True
EOF
}
probe_gemini() {
  $PY - <<'EOF' >/dev/null 2>&1
from storyforge.llm.gemini_client import GeminiClient
p, u = GeminiClient().complete_json("Return JSON only.", 'Return {"ok": true}')
assert p.get("ok") is True
EOF
}

echo "→ probing models…"
BACKEND="groq"; PLAN="spread"
if [ -n "${GEMINI_API_KEY:-}" ] && probe_gemini; then
  BACKEND="gemini"; PLAN="single"
  echo "  ✔ Gemini (${GEMINI_MODEL:-gemini-2.5-flash}) answers JSON — using it for every case"
elif probe_groq "openai/gpt-oss-120b"; then
  echo "  ⚠ no Gemini key — spreading cases across Groq's 200K/day models (same model per case for all versions, 8K TPM each)"
  export GROQ_TPM=8000 GROQ_MAX_TOKENS=3500 GROQ_REASONING_EFFORT=low
else
  echo "✖ neither Gemini nor Groq answered — check the keys in .env"; exit 1
fi

CASES=(edtech_teacher_dashboard fintech_kyc_onboarding healthcare_outpatient_scheduling hospitality_housekeeping \
       hr_leave_attendance logistics_driver_dispatch returns_portal saas_usage_billing)
SPREAD=(openai/gpt-oss-120b openai/gpt-oss-120b openai/gpt-oss-20b openai/gpt-oss-20b \
        qwen/qwen3.6-27b qwen/qwen3.6-27b qwen/qwen3.8-27b qwen/qwen3.8-27b)

# --- run ------------------------------------------------------------------------
START=$(date +%s)
for v in "${VERSIONS[@]}"; do
  echo; echo "══════ prompts $v ══════"
  if [ "$PLAN" = "single" ]; then
    $PY eval/run_eval.py --backend "$BACKEND" --prompt-version "$v" --resume
  else
    for i in "${!CASES[@]}"; do
      GROQ_MODEL="${SPREAD[$i]}" $PY eval/run_eval.py --backend groq --prompt-version "$v" --rounds 1 --resume --only "${CASES[$i]}" | grep -E "^\s+(↺|✖|[a-z_]+ +recall)" || true
    done
    # re-aggregate the merged report
    $PY eval/run_eval.py --backend groq --prompt-version "$v" --rounds 1 --resume | sed -n '/---/,$p'
  fi
done

echo; echo "✔ done in $(( ($(date +%s) - START) / 60 )) min. Results: eval/results/${BACKEND}_v*.json (+ one output json per case)"
$PY scripts/render_eval_table.py
