#!/usr/bin/env bash
set -euo pipefail

BUNDLE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VOICE_DIR="$BUNDLE_ROOT/ESDS/voice-gateway"
AGENT_DIR="$BUNDLE_ROOT/ESDS/elderly-companion-agent"

python3 -c 'import sys; assert sys.version_info >= (3, 11), "需要 Python 3.11+"'

if [[ ! -x "$VOICE_DIR/.venv/bin/python" ]]; then
  python3 -m venv "$VOICE_DIR/.venv"
fi
"$VOICE_DIR/.venv/bin/python" -m pip install --upgrade pip setuptools wheel
"$VOICE_DIR/.venv/bin/python" -m pip install -e "$VOICE_DIR"

if [[ ! -x "$AGENT_DIR/.venv/bin/python" ]]; then
  python3 -m venv "$AGENT_DIR/.venv"
fi
"$AGENT_DIR/.venv/bin/python" -m pip install --upgrade pip setuptools wheel
"$AGENT_DIR/.venv/bin/python" -m pip install -r "$AGENT_DIR/requirements.txt"

echo "依赖安装完成。下一步：python3 tools/configure_local.py"
