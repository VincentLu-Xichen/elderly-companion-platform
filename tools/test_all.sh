#!/usr/bin/env bash
set -euo pipefail

BUNDLE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VOICE_DIR="$BUNDLE_ROOT/ESDS/voice-gateway"
AGENT_DIR="$BUNDLE_ROOT/ESDS/elderly-companion-agent"
export PYTHONDONTWRITEBYTECODE=1

test -x "$VOICE_DIR/.venv/bin/python"
test -x "$AGENT_DIR/.venv/bin/python"

(
  cd "$VOICE_DIR"
  .venv/bin/python -m unittest discover -s tests -v
  .venv/bin/python -m compileall -q src scripts tests
)

(
  cd "$AGENT_DIR"
  .venv/bin/python -m unittest discover tests -v
  .venv/bin/python -m unittest discover cbt_course_llm_freeform/tests -v
  .venv/bin/python -m compileall -q daily_agent cbt_course cbt_course_llm_freeform webapp tests
  if command -v node >/dev/null 2>&1; then
    node --check webapp/static/app.js
    node --check webapp/static/cbt_course/course.js
  fi
)

echo "全部离线回归通过。"
