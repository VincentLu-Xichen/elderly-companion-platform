#!/usr/bin/env python3
"""Start the self-contained ESDS voice demo."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import logging
import os
import secrets
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from dataclasses import replace
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"

# `python scripts/run_local.py` works without manually activating the venv.
if PROJECT_PYTHON.is_file() and Path(sys.executable).resolve() != PROJECT_PYTHON.resolve():
    os.execv(
        str(PROJECT_PYTHON),
        [str(PROJECT_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]],
    )

SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from esds_voice.config import Settings
from esds_voice.server import Gateway

SENSEVOICE_DIR = (
    PROJECT_ROOT
    / ".models"
    / "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17"
)
EMOTION2VEC_DIR = PROJECT_ROOT / ".models" / "emotion2vec_plus_base"
OLLAMA_MODELS_DIR = PROJECT_ROOT / ".models" / "ollama"


class RuntimeConfigHandler(SimpleHTTPRequestHandler):
    runtime_config: dict[str, object] = {}

    def end_headers(self) -> None:
        # This is a local development UI; always serve the latest client code
        # after a gateway restart instead of reusing a stale browser cache.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self) -> None:
        if self.path.split("?", 1)[0] == "/runtime-config.js":
            payload = (
                "window.ESDS_CONFIG="
                + json.dumps(self.runtime_config, ensure_ascii=False)
                + ";\n"
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        super().do_GET()

    def log_message(self, format: str, *args: object) -> None:
        logging.getLogger("esds.ui").debug(format, *args)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the ESDS voice gateway and voice-only browser client"
    )
    parser.add_argument("--gateway-port", type=int, default=None)
    parser.add_argument("--ui-port", type=int, default=8080)
    parser.add_argument("--no-open", action="store_true")
    return parser.parse_args()


def _prompt_secret(prompt: str) -> str:
    try:
        return getpass.getpass(prompt).strip()
    except EOFError as exc:
        raise SystemExit(
            "当前终端无法安全读取百炼 Key。请先执行 "
            "`export DASHSCOPE_API_KEY='你的 Key'` 后重试。"
        ) from exc


def configure_runtime() -> None:
    """Discover bundled resources and collect secrets for this process only."""
    os.environ.setdefault("ESDS_RUNTIME_PROVIDER", "local")
    os.environ.setdefault("ESDS_ASR_PROVIDER", "sensevoice")
    os.environ.setdefault("ESDS_EMOTION_BACKEND", "emotion2vec")
    os.environ.setdefault("ESDS_TTS_PROVIDER", "qwen")
    os.environ.setdefault("ESDS_SENSEVOICE_MODEL_DIR", str(SENSEVOICE_DIR))
    os.environ.setdefault("ESDS_EMOTION2VEC_MODEL_DIR", str(EMOTION2VEC_DIR))

    runtime = os.environ["ESDS_RUNTIME_PROVIDER"].strip().lower()
    asr = os.environ["ESDS_ASR_PROVIDER"].strip().lower()
    tts = os.environ["ESDS_TTS_PROVIDER"].strip().lower()
    needs_bailian = runtime == "qwen_realtime" or (
        runtime == "local" and (asr == "qwen" or tts == "qwen")
    )
    if needs_bailian and not (os.getenv("DASHSCOPE_API_KEY") or "").strip():
        key = _prompt_secret(
            "请输入百炼 DASHSCOPE API Key（不会显示，仅保存在当前进程内）: "
        )
        if not key:
            raise SystemExit("未输入百炼 DASHSCOPE_API_KEY，启动已取消。")
        os.environ["DASHSCOPE_API_KEY"] = key


def _ollama_tags(base_url: str) -> set[str] | None:
    try:
        with urllib.request.urlopen(
            f"{base_url.rstrip('/')}/api/tags", timeout=1.5
        ) as response:
            payload = json.load(response)
    except (OSError, urllib.error.URLError, ValueError):
        return None
    return {
        str(item.get("name"))
        for item in payload.get("models", [])
        if item.get("name")
    }


def _find_ollama() -> str:
    configured = (os.getenv("OLLAMA_EXECUTABLE") or "").strip()
    if configured:
        executable = Path(configured).expanduser().resolve()
        if executable.is_file():
            return str(executable)
        raise SystemExit(f"OLLAMA_EXECUTABLE 不存在：{executable}")

    system = shutil.which("ollama")
    if system:
        return system
    bundled = sorted((PROJECT_ROOT / ".tools").glob("ollama-*/ollama"), reverse=True)
    if bundled:
        return str(bundled[0])
    raise SystemExit(
        "未找到 Ollama 运行时。请重新执行项目环境安装，或设置 OLLAMA_EXECUTABLE。"
    )


def _bundled_ollama_model_exists(model: str) -> bool:
    name, separator, tag = model.partition(":")
    tag = tag if separator else "latest"
    return (
        OLLAMA_MODELS_DIR
        / "manifests"
        / "registry.ollama.ai"
        / "library"
        / name
        / tag
    ).is_file()


def _unused_local_ollama_url() -> str:
    for port in range(11435, 11455):
        url = f"http://127.0.0.1:{port}"
        if _ollama_tags(url) is None:
            return url
    raise SystemExit("11435–11454 端口均被占用，无法启动项目内置 Ollama。")


def prepare_local_runtime() -> subprocess.Popen[bytes] | None:
    if os.environ["ESDS_RUNTIME_PROVIDER"].strip().lower() != "local":
        return None

    if os.environ["ESDS_ASR_PROVIDER"].strip().lower() == "sensevoice":
        asr_root = Path(os.environ["ESDS_SENSEVOICE_MODEL_DIR"]).expanduser()
        if not (asr_root / "tokens.txt").is_file() or not any(
            (asr_root / name).is_file() for name in ("model.int8.onnx", "model.onnx")
        ):
            raise SystemExit(f"SenseVoice 模型不完整：{asr_root}")
    if os.environ["ESDS_EMOTION_BACKEND"].strip().lower() == "emotion2vec":
        emotion_root = Path(os.environ["ESDS_EMOTION2VEC_MODEL_DIR"]).expanduser()
        if not (emotion_root / "model.pt").is_file():
            raise SystemExit(f"emotion2vec 模型不完整：{emotion_root}")

    # Agent Bridge owns dialogue generation and persistence. In this profile,
    # local means modular ASR/chat/TTS and must not launch Ollama.
    if os.getenv("ESDS_CHAT_PROVIDER", "ollama").strip().lower() in {
        "agent_bridge",
        "cbt_agent_bridge",
    }:
        return None

    configured_url = (os.getenv("ESDS_OLLAMA_URL") or "").strip()
    base_url = configured_url or "http://127.0.0.1:11434"
    model = os.getenv("ESDS_OLLAMA_MODEL", "qwen3:4b-instruct")
    executable = _find_ollama()
    environment = os.environ.copy()
    environment.setdefault("OLLAMA_MODELS", str(OLLAMA_MODELS_DIR))
    process: subprocess.Popen[bytes] | None = None
    tags = _ollama_tags(base_url)

    # A separately installed Ollama may already own 11434 while using another
    # model store. Keep it untouched and launch this project's self-contained
    # runtime on a spare loopback port.
    if (
        tags is not None
        and model not in tags
        and f"{model}:latest" not in tags
        and not configured_url
        and _bundled_ollama_model_exists(model)
    ):
        base_url = _unused_local_ollama_url()
        tags = None

    if tags is None:
        print("正在启动项目内置 Ollama …")
        environment["OLLAMA_HOST"] = base_url.removeprefix("http://")
        process = subprocess.Popen(
            [executable, "serve"],
            env=environment,
            cwd=str(Path(executable).parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            tags = _ollama_tags(base_url)
            if tags is not None:
                break
            if process.poll() is not None:
                raise SystemExit("Ollama 启动失败。")
            time.sleep(0.2)
        else:
            process.terminate()
            raise SystemExit("Ollama 在 30 秒内没有就绪。")

    assert tags is not None
    os.environ["ESDS_OLLAMA_URL"] = base_url
    if model not in tags and f"{model}:latest" not in tags:
        print(f"正在下载本地对话模型 {model} …")
        completed = subprocess.run([executable, "pull", model], env=environment)
        if completed.returncode:
            if process is not None:
                process.terminate()
            raise SystemExit(f"下载 Ollama 模型 {model} 失败。")
    return process


async def run(args: argparse.Namespace) -> None:
    try:
        from websockets.asyncio.server import serve
    except ImportError as exc:
        raise SystemExit("请先安装项目依赖：python -m pip install -e .") from exc

    settings = Settings.from_env()
    token = settings.device_token or secrets.token_urlsafe(24)
    settings = replace(
        settings,
        host="127.0.0.1",
        port=args.gateway_port or settings.port,
        device_token=token,
    )
    gateway = Gateway(settings)

    RuntimeConfigHandler.runtime_config = {
        "wsUrl": f"ws://127.0.0.1:{settings.port}/v1/device",
        "deviceToken": token,
    }
    handler = partial(RuntimeConfigHandler, directory=str(PROJECT_ROOT / "web"))
    httpd = ThreadingHTTPServer(("127.0.0.1", args.ui_port), handler)
    http_thread = threading.Thread(
        target=httpd.serve_forever,
        name="esds-local-ui",
        daemon=True,
    )

    try:
        async with serve(
            gateway.handle,
            settings.host,
            settings.port,
            max_size=settings.max_ws_message_bytes,
            max_queue=4,
            compression=None,
            ping_interval=20,
            ping_timeout=20,
        ):
            http_thread.start()
            url = f"http://127.0.0.1:{args.ui_port}"
            print(f"\nESDS Voice 已启动：{url}")
            print(f"运行模式：{settings.runtime_provider}")
            print("页面只请求麦克风权限，不请求摄像头。按 Ctrl+C 停止。\n")
            if not args.no_open:
                await asyncio.to_thread(webbrowser.open, url)
            await asyncio.Future()
    finally:
        if http_thread.is_alive():
            await asyncio.to_thread(httpd.shutdown)
            http_thread.join(timeout=2)
        httpd.server_close()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level="INFO",
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    configure_runtime()
    ollama_process = prepare_local_runtime()
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\nESDS Voice 已停止。")
    finally:
        if ollama_process is not None and ollama_process.poll() is None:
            ollama_process.terminate()
            try:
                ollama_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                ollama_process.kill()


if __name__ == "__main__":
    main()
