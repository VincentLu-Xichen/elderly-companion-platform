#!/usr/bin/env python3
"""Run the local Mac web app using module API settings and separate private data."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
AGENT = ROOT / "ESDS" / "elderly-companion-agent"
sys.path.insert(0, str(AGENT))
from dotenv import load_dotenv
load_dotenv(AGENT / ".env", override=True, encoding="utf-8-sig")
load_dotenv(ROOT / ".runtime" / "web.env", override=True)
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
os.chdir(AGENT)
subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
print("网页：http://127.0.0.1:8000/；本机测试邀请码：mac-local-2026；Ctrl+C 停止。", flush=True)
import uvicorn
uvicorn.run("webapp.main:app", host="127.0.0.1", port=8000)
