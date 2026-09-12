#!/usr/bin/env bash
# One command to run the live evaluation on a machine that can reach api.groq.com.
#
#   bash scripts/run_live_evals.sh            # v3, v2, v1 on all 8 cases, resumable
#   bash scripts/run_live_evals.sh v3         # one version only
#
# Free-tier budget on Groq (Sep 2026): the 200K-tokens/day models can't cover
# 24 runs, so the script prefers groq/compound (no daily token cap, 250 req/day).
# If compound rejects JSON mode or is unavailable it spreads cases across the
# four 200K/day models so each case still sees the SAME model for v1, v2 and v3.
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
probe() {  # $1 = model  → 0 if a tiny JSON call works
  GROQ_MODEL="$1" $PY - <<'EOF' >/dev/null 2>&1
from storyforge.llm.groq_client import GroqClient
p, u = GroqClient().complete_json("Return JSON only.", 'Return {"ok": true}')
assert p.get("ok") is True
EOF
}

echo "→ probing models on your Groq account…"
if probe "groq/compound"; then
  PLAN="single"; MODEL="groq/compound"
  echo "  ✔ groq/compound answers JSON — using it for every case (no daily token cap)"
else
  PLAN="spread"
  echo "  ⚠ groq/compound unavailable — spreading cases across 200K/day models (same model per case for all versions)"
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
    GROQ_MODEL="$MODEL" $PY eval/run_eval.py --backend groq --prompt-version "$v" --resume
  else
    for i in "${!CASES[@]}"; do
      GROQ_MODEL="${SPREAD[$i]}" $PY eval/run_eval.py --backend groq --prompt-version "$v" --resume --only "${CASES[$i]}" | grep -E "^\s+(↺|✖|[a-z_]+ +recall)" || true
    done
    # re-aggregate the merged report
    $PY eval/run_eval.py --backend groq --prompt-version "$v" --resume | sed -n '/---/,$p'
  fi
done

echo; echo "✔ done in $(( ($(date +%s) - START) / 60 )) min. Results: eval/results/groq_v*.json (+ one output json per case)"
$PY scripts/render_eval_table.py
