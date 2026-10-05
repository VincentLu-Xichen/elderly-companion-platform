#!/usr/bin/env python3
"""Generate private local Daily Chat bridge configuration without exposing secrets."""

from __future__ import annotations

import argparse
import base64
import getpass
import os
import secrets
from pathlib import Path


BUNDLE_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = BUNDLE_ROOT / ".runtime"
AGENT_ENV = RUNTIME_DIR / "agent.env"
VOICE_ENV = RUNTIME_DIR / "voice.env"
DATABASE_PATH = RUNTIME_DIR / "roleplay_chat.db"


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        values[name.strip()] = value.strip()
    return values


def write_env(path: Path, values: dict[str, str], comment: str) -> None:
    RUNTIME_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    RUNTIME_DIR.chmod(0o700)
    temporary = path.with_suffix(".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        output.write(comment + "\n")
        for name, value in values.items():
            output.write(f"{name}={value}\n")
    temporary.chmod(0o600)
    temporary.replace(path)
    path.chmod(0o600)


def configure(*, acknowledge_consent: bool) -> None:
    old_agent = read_env(AGENT_ENV)
    old_voice = read_env(VOICE_ENV)
    api_key = old_voice.get("DASHSCOPE_API_KEY") or old_agent.get("DASHSCOPE_API_KEY")
    if not api_key:
        api_key = getpass.getpass("百炼 DASHSCOPE API Key（不会显示）: ").strip()
    if not api_key:
        raise SystemExit("未输入百炼 Key，配置取消。")

    bridge_token = (
        old_voice.get("ESDS_AGENT_BRIDGE_TOKEN")
        or old_agent.get("VOICE_BRIDGE_TOKEN")
        or secrets.token_urlsafe(32)
    )
    device_id = (
        old_voice.get("ESDS_AGENT_BRIDGE_DEVICE_ID")
        or old_agent.get("VOICE_DEVICE_ID")
        or f"esds-desktop-{secrets.token_hex(6)}"
    )
    consent = old_agent.get("VOICE_CONSENT_ACKNOWLEDGED", "false").lower()
    if acknowledge_consent:
        consent = "true"

    voice = {
        "ESDS_HOST": "127.0.0.1",
        "ESDS_PORT": "8765",
        "ESDS_RUNTIME_PROVIDER": "local",
        "ESDS_ASR_PROVIDER": "qwen",
        "ESDS_CHAT_PROVIDER": "agent_bridge",
        "ESDS_TTS_PROVIDER": "qwen",
        "ESDS_EMOTION_BACKEND": "heuristic",
        "ESDS_QWEN_ASR_REGION": "beijing",
        "ESDS_QWEN_TTS_REGION": "beijing",
        "ESDS_QWEN_TTS_VOICE": "Cherry",
        "ESDS_AGENT_BRIDGE_URL": "http://127.0.0.1:8000",
        "ESDS_AGENT_BRIDGE_TOKEN": bridge_token,
        "ESDS_AGENT_BRIDGE_DEVICE_ID": device_id,
        "ESDS_AGENT_BRIDGE_TIMEOUT_SECONDS": "65",
        "DASHSCOPE_API_KEY": api_key,
    }
    encryption_key = old_agent.get("DATA_ENCRYPTION_KEY") or base64.urlsafe_b64encode(
        secrets.token_bytes(32)
    ).decode("ascii")
    agent = {
        "APP_ENV": "production",
        "APP_SECRET": old_agent.get("APP_SECRET") or secrets.token_urlsafe(48),
        "DATA_ENCRYPTION_KEY": encryption_key,
        "DATABASE_URL": f"sqlite:///{DATABASE_PATH}",
        "DATABASE_POOL_MODE": "application",
        "INVITE_CODES": old_agent.get("INVITE_CODES") or f"esds-local:{secrets.token_urlsafe(24)}",
        "ADMIN_PASSWORD": old_agent.get("ADMIN_PASSWORD") or secrets.token_urlsafe(32),
        "CONSENT_VERSION": old_agent.get("CONSENT_VERSION", "2026-07-v1"),
        "CBT_COURSE_AGENT_VERSION": old_agent.get("CBT_COURSE_AGENT_VERSION", "course-v1"),
        "DAILY_CHAT_AGENT_VERSION": "daily-chat-v1-dashscope",
        "COOKIE_SECURE": "false",
        "SESSION_HOURS": "12",
        "MAX_MESSAGE_CHARS": "2000",
        "RATE_LIMIT_PER_MINUTE": "30",
        "DAILY_CHAT_PROVIDER": "dashscope",
        "DASHSCOPE_API_KEY": api_key,
        "DASHSCOPE_CHAT_MODEL": "qwen-plus",
        "DASHSCOPE_CHAT_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "VOICE_BRIDGE_ENABLED": "true",
        "VOICE_BRIDGE_TOKEN": bridge_token,
        "VOICE_DEVICE_ID": device_id,
        "VOICE_PARTICIPANT_LABEL": "esds-voice-user",
        "VOICE_CONSENT_ACKNOWLEDGED": consent,
    }
    write_env(VOICE_ENV, voice, "# Private portable ESDS voice configuration.")
    write_env(AGENT_ENV, agent, "# Private portable Elderly Agent configuration.")
    state = "已确认" if consent == "true" else "尚未确认"
    print(f"配置已写入 {RUNTIME_DIR}；持久化同意{state}；密钥未显示。")


def check() -> int:
    agent = read_env(AGENT_ENV)
    voice = read_env(VOICE_ENV)
    issues: list[str] = []
    for name in ("DASHSCOPE_API_KEY", "ESDS_AGENT_BRIDGE_TOKEN", "ESDS_AGENT_BRIDGE_DEVICE_ID"):
        if not voice.get(name):
            issues.append(name)
    for name in ("DASHSCOPE_API_KEY", "DATA_ENCRYPTION_KEY", "VOICE_BRIDGE_TOKEN", "VOICE_DEVICE_ID"):
        if not agent.get(name):
            issues.append(name)
    if voice.get("ESDS_AGENT_BRIDGE_TOKEN") != agent.get("VOICE_BRIDGE_TOKEN"):
        issues.append("bridge token mismatch")
    if voice.get("ESDS_AGENT_BRIDGE_DEVICE_ID") != agent.get("VOICE_DEVICE_ID"):
        issues.append("device ID mismatch")
    if agent.get("VOICE_CONSENT_ACKNOWLEDGED") != "true":
        issues.append("VOICE_CONSENT_ACKNOWLEDGED")
    if issues:
        print("配置检查失败：" + ", ".join(issues))
        return 1
    print("本地集成配置检查通过；密钥未显示。")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--acknowledge-consent",
        action="store_true",
        help="确认参与者已同意保存转写、回复和审计元数据（不保存原始音频）",
    )
    args = parser.parse_args()
    if args.check:
        raise SystemExit(check())
    configure(acknowledge_consent=args.acknowledge_consent)


if __name__ == "__main__":
    main()
