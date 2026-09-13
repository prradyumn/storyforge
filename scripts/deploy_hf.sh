#!/usr/bin/env bash
# Deploy StoryForge to a Hugging Face Space (Docker SDK, free CPU tier).
#
#   bash scripts/deploy_hf.sh            # create/update the Space, push, set secrets, wait, preflight
#
# Needs in .env: HF_TOKEN (write), HF_USER, and the runtime secrets you want on
# the Space (GEMINI_API_KEY, GROQ_API_KEY, JIRA_*). Secrets are sent to the
# Space's secret store over the HF API — they are never committed.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] || { echo "✖ .env missing"; exit 1; }
set -a; . ./.env; set +a
: "${HF_TOKEN:?set HF_TOKEN in .env}"; : "${HF_USER:?set HF_USER in .env}"
SPACE="${HF_SPACE:-storyforge}"
REPO_ID="$HF_USER/$SPACE"
API="https://huggingface.co/api"
AUTH=(-H "Authorization: Bearer $HF_TOKEN" -H "Content-Type: application/json")
PY=${PY:-.venv/bin/python}; [ -x "$PY" ] || PY=python3

echo "→ ensuring Space $REPO_ID exists (docker sdk, public)"
code=$(curl -sS -o /tmp/hf_create.json -w "%{http_code}" "${AUTH[@]}" -X POST "$API/repos/create" \
  -d "{\"type\":\"space\",\"name\":\"$SPACE\",\"sdk\":\"docker\",\"private\":false}")
case "$code" in
  200|201) echo "  ✔ created";;
  409) echo "  ✔ already exists";;
  *) echo "  ✖ create failed ($code): $(cat /tmp/hf_create.json)"; exit 1;;
esac

echo "→ setting Space secrets"
ADMIN_KEY="${STORYFORGE_ADMIN_KEY:-$(LC_ALL=C tr -dc 'a-z0-9' </dev/urandom | head -c 20)}"
grep -q '^STORYFORGE_ADMIN_KEY=' .env || echo "STORYFORGE_ADMIN_KEY=$ADMIN_KEY" >> .env
set_secret() { # key value
  [ -z "${2:-}" ] && return 0
  curl -sS -o /dev/null -w "  %{http_code} $1\n" "${AUTH[@]}" -X POST "$API/spaces/$REPO_ID/secrets" \
    -d "$(printf '{"key":"%s","value":"%s"}' "$1" "$2")"
}
set_secret GEMINI_API_KEY "${GEMINI_API_KEY:-}"
set_secret GROQ_API_KEY "${GROQ_API_KEY:-}"
set_secret JIRA_BASE_URL "${JIRA_BASE_URL:-}"
set_secret JIRA_EMAIL "${JIRA_EMAIL:-}"
set_secret JIRA_API_TOKEN "${JIRA_API_TOKEN:-}"
set_secret JIRA_PROJECT_KEY "${JIRA_PROJECT_KEY:-SCRUM}"
set_secret STORYFORGE_ADMIN_KEY "$ADMIN_KEY"
set_secret STORYFORGE_BACKEND "gemini,groq"
set_secret STORYFORGE_DAILY_LIVE_LIMIT "${STORYFORGE_DAILY_LIVE_LIMIT:-40}"
set_secret GEMINI_MODEL "${GEMINI_MODEL:-gemini-2.5-flash}"
set_secret GROQ_MODEL "${GROQ_MODEL:-openai/gpt-oss-120b}"

echo "→ building Space repo from HEAD ($(git rev-parse --short HEAD))"
TMP=$(mktemp -d)
git archive HEAD | tar -x -C "$TMP"
{
  cat <<EOF
---
title: StoryForge
emoji: 🧭
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Stakeholder notes → INVEST-reviewed user stories → Jira
---

EOF
  sed "s|https://storyforge-lsnr.onrender.com|this Space|g" README.md
} > "$TMP/README.md"
(
  cd "$TMP"
  git init -q -b main
  git -c user.name="Pradyumn Awasthi" -c user.email="Pradyumnawasthi03@gmail.com" add -A
  git -c user.name="Pradyumn Awasthi" -c user.email="Pradyumnawasthi03@gmail.com" commit -q -m "deploy $(date -u +%Y-%m-%dT%H:%MZ) from $(git -C "$OLDPWD" rev-parse --short HEAD)"
  GIT_ASKPASS=/bin/true git -c credential.helper= push -q --force "https://$HF_USER:$HF_TOKEN@huggingface.co/spaces/$REPO_ID" main 2>&1 | sed "s/$HF_TOKEN/***/g"
)
rm -rf "$TMP"
URL="https://$(echo "$HF_USER" | tr '[:upper:]' '[:lower:]')-$SPACE.hf.space"
echo "  ✔ pushed → https://huggingface.co/spaces/$REPO_ID"
echo "→ waiting for the build (usually 2–4 min)…"
for i in $(seq 1 40); do
  sleep 15
  st=$(curl -sS "${AUTH[@]}" "$API/spaces/$REPO_ID/runtime" | $PY -c 'import sys,json; print(json.load(sys.stdin).get("stage",""))' 2>/dev/null || echo "")
  printf "  %s\n" "${st:-?}"
  [ "$st" = "RUNNING" ] && break
  case "$st" in BUILD_ERROR|RUNTIME_ERROR|CONFIG_ERROR) echo "✖ Space failed: $st — see https://huggingface.co/spaces/$REPO_ID/logs"; exit 1;; esac
done
echo "→ preflight against $URL"
$PY scripts/preflight.py --url "$URL" || true
echo
echo "✔ Demo: $URL"
echo "  Admin key for live Jira publishing (kept in .env as STORYFORGE_ADMIN_KEY): $ADMIN_KEY"
