"""Offline regression in a fresh database, including the course package suite."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import subprocess


def main():
    project = Path(__file__).resolve().parents[1]
    os.chdir(project)
    sys.path.insert(0, str(project))
    with tempfile.TemporaryDirectory(prefix="elderly-agent-regression-") as directory:
        os.environ.update({"DATABASE_URL": "sqlite:///" + (Path(directory) / "test.db").as_posix(), "APP_ENV": "development", "APP_SECRET": "test-app-secret", "INVITE_CODES": "student-test:test-invite", "ADMIN_PASSWORD": "test-admin-password", "COOKIE_SECURE": "false", "DATA_ENCRYPTION_KEY": "", "VERCEL": "false", "VOICE_BRIDGE_ENABLED": "false", "CBT_REFLECTION_POLICY": "none"})
        failures = 0
        # Local real-model credentials must never leak into an offline regression.
        os.environ.update({"CBT_COURSE_PROVIDER": "dashscope", "CBT_COURSE_MODEL": "qwen-plus",
            "DEEPSEEK_API_KEY": "", "DASHSCOPE_API_KEY": "", "AZURE_OPENAI_API_KEY": ""})
        for index, folder in enumerate(("tests", "cbt_course_llm_freeform/tests")):
            env = {**os.environ, "DATABASE_URL": "sqlite:///" + (Path(directory) / f"test-{index}.db").as_posix(), "PYTHONUTF8": "1"}
            result = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", folder, "-v"], cwd=project, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
            print(f"{folder}: " + ("passed" if result.returncode == 0 else "FAILED"))
            output = result.stdout + result.stderr
            print(output if result.returncode else "\n".join(output.strip().splitlines()[-4:]))
            failures += result.returncode != 0
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
