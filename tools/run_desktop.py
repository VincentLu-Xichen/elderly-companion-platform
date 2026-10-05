#!/usr/bin/env python3
"""Start the portable Agent and browser voice gateway as one local stack."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


BUNDLE_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = BUNDLE_ROOT / ".runtime"
VOICE_DIR = BUNDLE_ROOT / "ESDS" / "voice-gateway"
AGENT_DIR = BUNDLE_ROOT / "ESDS" / "elderly-companion-agent"


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        raise SystemExit(f"缺少配置：{path}；请先运行 tools/configure_local.py。")
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            name, value = line.split("=", 1)
            values[name.strip()] = value.strip()
    return values


def wait_for_agent(process: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise SystemExit(f"Agent 启动失败，退出码 {process.returncode}。")
        try:
            with urllib.request.urlopen("http://127.0.0.1:8000/healthz", timeout=1) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(0.25)
    raise SystemExit("Agent 在 30 秒内没有就绪。")


def stop(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()

    agent_python = AGENT_DIR / ".venv" / "bin" / "python"
    voice_python = VOICE_DIR / ".venv" / "bin" / "python"
    if not agent_python.is_file() or not voice_python.is_file():
        raise SystemExit("虚拟环境不存在；请先运行 tools/setup.sh。")

    agent_values = read_env(RUNTIME_DIR / "agent.env")
    voice_values = read_env(RUNTIME_DIR / "voice.env")
    if agent_values.get("VOICE_CONSENT_ACKNOWLEDGED") != "true":
        raise SystemExit("持久化同意尚未确认；请阅读指南后显式运行 --acknowledge-consent。")
    if agent_values.get("VOICE_BRIDGE_TOKEN") != voice_values.get("ESDS_AGENT_BRIDGE_TOKEN"):
        raise SystemExit("Agent 与 Voice Bridge Token 不一致，请重新配置。")

    agent_env = os.environ.copy()
    agent_env.update(agent_values)
    voice_env = os.environ.copy()
    voice_env.update(voice_values)
    agent_env["PYTHONDONTWRITEBYTECODE"] = "1"
    voice_env["PYTHONDONTWRITEBYTECODE"] = "1"

    subprocess.run(
        [str(agent_python), "-m", "alembic", "upgrade", "head"],
        cwd=AGENT_DIR,
        env=agent_env,
        check=True,
    )

    agent: subprocess.Popen[bytes] | None = None
    voice: subprocess.Popen[bytes] | None = None
    try:
        agent = subprocess.Popen(
            [
                str(agent_python),
                "-m",
                "uvicorn",
                "webapp.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
            ],
            cwd=AGENT_DIR,
            env=agent_env,
        )
        wait_for_agent(agent)
        command = [str(voice_python), str(VOICE_DIR / "scripts" / "run_local.py")]
        if args.no_open:
            command.append("--no-open")
        voice = subprocess.Popen(command, cwd=VOICE_DIR, env=voice_env)
        print("ESDS 便携语音栈已启动；按 Ctrl+C 停止。")
        while True:
            if agent.poll() is not None:
                raise SystemExit(f"Agent 意外退出，退出码 {agent.returncode}。")
            if voice.poll() is not None:
                raise SystemExit(voice.returncode or 0)
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        stop(voice)
        stop(agent)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    main()
