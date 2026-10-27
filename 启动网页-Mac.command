#!/bin/zsh
cd "${0:A:h}"
exec ./ESDS/elderly-companion-agent/.venv/bin/python -B tools/run_web_mac.py
