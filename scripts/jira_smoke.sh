#!/usr/bin/env bash
# Live Jira smoke test: publish a saved analysis (no model calls), then re-publish to prove idempotency.
#   bash scripts/jira_smoke.sh [path/to/saved_result.json]
set -euo pipefail
cd "$(dirname "$0")/.."
SRC="${1:-eval/results/gemini_v3_returns_portal.json}"
PY=.venv/bin/python; [ -x "$PY" ] || PY=python3
set -a; . ./.env; set +a
echo "→ Jira preflight"; $PY scripts/preflight.py 2>/dev/null | grep -i jira || true
echo "→ dry run from $SRC"
$PY -m storyforge.cli "$SRC" --from-json --publish --dry-run --quiet | head -3
echo "→ live publish"
$PY -m storyforge.cli "$SRC" --from-json --publish --quiet
echo "→ publish again (should skip everything)"
$PY -m storyforge.cli "$SRC" --from-json --publish --quiet
echo "✔ open $JIRA_BASE_URL/jira/software/projects/${JIRA_PROJECT_KEY:-SCRUM}/boards/1/backlog"
