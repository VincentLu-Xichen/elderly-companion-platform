#!/usr/bin/env python3
"""Configure private Daily Chat Agent and ESDS environment files on the Pi."""

from __future__ import annotations

import argparse
import base64
import os
import secrets
from pathlib import Path


VOICE_ENV = Path.home() / ".config" / "esds-voice" / "env"
AGENT_ENV = Path.home() / ".config" / "elderly-agent" / "env"
AGENT_DATA = Path.home() / ".local" / "share" / "elderly-agent"


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        values[name.strip()] = value.strip().strip("'\"")
    return values


def write_env(path: Path, values: dict[str, str], comment: str) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    temporary = path.with_suffix(".tmp")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        0o600,
    )
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        output.write(comment + "\n")
        for name, value in values.items():
            output.write(f"{name}={value}\n")
    temporary.chmod(0o600)
    temporary.replace(path)
    path.chmod(0o600)


def device_id() -> str:
    suffix = Path("/etc/machine-id").read_text(encoding="ascii").strip()[:12]
    return f"esds-pi-{suffix}"


def configure(*, acknowledge_consent: bool) -> None:
    voice = read_env(VOICE_ENV)
    api_key = voice.get("DASHSCOPE_API_KEY", "").strip()
    if not api_key:
        raise SystemExit(
            "缺少 DASHSCOPE_API_KEY；请先运行 scripts/configure_pi.py。"
        )
    agent = read_env(AGENT_ENV)
    bridge_token = (
        voice.get("ESDS_AGENT_BRIDGE_TOKEN")
        or agent.get("VOICE_BRIDGE_TOKEN")
        or secrets.token_urlsafe(32)
    )
    enrolled_device = device_id()

    voice.update(
        {
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
            "ESDS_AGENT_BRIDGE_DEVICE_ID": enrolled_device,
            "ESDS_AGENT_BRIDGE_TIMEOUT_SECONDS": "65",
        }
    )

    AGENT_DATA.mkdir(mode=0o700, parents=True, exist_ok=True)
    AGENT_DATA.chmod(0o700)
    encryption_key = agent.get("DATA_ENCRYPTION_KEY") or base64.urlsafe_b64encode(
        secrets.token_bytes(32)
    ).decode("ascii")
    consent = agent.get("VOICE_CONSENT_ACKNOWLEDGED", "false").lower()
    if acknowledge_consent:
        consent = "true"
    agent_values = {
        "APP_ENV": "production",
        "APP_SECRET": agent.get("APP_SECRET") or secrets.token_urlsafe(48),
        "DATA_ENCRYPTION_KEY": encryption_key,
        "DATABASE_URL": f"sqlite:///{AGENT_DATA / 'roleplay_chat.db'}",
        "DATABASE_POOL_MODE": "application",
        "INVITE_CODES": agent.get("INVITE_CODES")
        or f"esds-voice-user:{secrets.token_urlsafe(24)}",
        "ADMIN_PASSWORD": agent.get("ADMIN_PASSWORD") or secrets.token_urlsafe(32),
        "CONSENT_VERSION": agent.get("CONSENT_VERSION", "2026-07-v1"),
        "CBT_COURSE_AGENT_VERSION": agent.get(
            "CBT_COURSE_AGENT_VERSION", "course-v1"
        ),
        "DAILY_CHAT_AGENT_VERSION": "daily-chat-v1-dashscope",
        "COOKIE_SECURE": "false",
        "SESSION_HOURS": "12",
        "MAX_MESSAGE_CHARS": "2000",
        "RATE_LIMIT_PER_MINUTE": "30",
        "DAILY_CHAT_PROVIDER": "dashscope",
        "DASHSCOPE_API_KEY": api_key,
        "DASHSCOPE_CHAT_MODEL": agent.get("DASHSCOPE_CHAT_MODEL", "qwen-plus"),
        "DASHSCOPE_CHAT_BASE_URL": (
            "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ),
        "VOICE_BRIDGE_ENABLED": "true",
        "VOICE_BRIDGE_TOKEN": bridge_token,
        "VOICE_DEVICE_ID": enrolled_device,
        "VOICE_PARTICIPANT_LABEL": "esds-voice-user",
        "VOICE_CONSENT_ACKNOWLEDGED": consent,
    }
    write_env(
        VOICE_ENV,
        voice,
        "# ESDS integrated Daily Chat profile; contains secrets.",
    )
    write_env(
        AGENT_ENV,
        agent_values,
        "# Elderly Agent Raspberry Pi profile; contains secrets.",
    )
    if consent == "true":
        print("Daily Chat 集成配置已写入；持久化记录同意已确认；密钥未显示。")
    else:
        print(
            "Daily Chat 集成配置已写入；持久化记录同意尚未确认；密钥未显示。"
        )


def check() -> int:
    voice = read_env(VOICE_ENV)
    agent = read_env(AGENT_ENV)
    expected = {
        "ESDS_RUNTIME_PROVIDER": "local",
        "ESDS_ASR_PROVIDER": "qwen",
        "ESDS_CHAT_PROVIDER": "agent_bridge",
        "ESDS_TTS_PROVIDER": "qwen",
    }
    missing = [
        name
        for name in (
            "DASHSCOPE_API_KEY",
            "ESDS_AGENT_BRIDGE_TOKEN",
            "ESDS_AGENT_BRIDGE_DEVICE_ID",
        )
        if not voice.get(name)
    ]
    missing.extend(
        name
        for name in (
            "DASHSCOPE_API_KEY",
            "DATA_ENCRYPTION_KEY",
            "VOICE_BRIDGE_TOKEN",
            "VOICE_DEVICE_ID",
        )
        if not agent.get(name)
    )
    mismatch = [
        name for name, value in expected.items() if voice.get(name) != value
    ]
    if voice.get("ESDS_AGENT_BRIDGE_TOKEN") != agent.get("VOICE_BRIDGE_TOKEN"):
        mismatch.append("bridge token")
    if voice.get("ESDS_AGENT_BRIDGE_DEVICE_ID") != agent.get("VOICE_DEVICE_ID"):
        mismatch.append("device ID")
    if agent.get("VOICE_CONSENT_ACKNOWLEDGED") != "true":
        mismatch.append("VOICE_CONSENT_ACKNOWLEDGED")
    if missing or mismatch:
        print("配置检查失败：" + ", ".join(missing + mismatch))
        return 1
    print("Daily Chat 集成配置检查通过；密钥未显示。")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--acknowledge-consent",
        action="store_true",
        help="确认当前工程测试参与者已同意持久化保存转写文本、回复和审计元数据",
    )
    args = parser.parse_args()
    if args.check:
        raise SystemExit(check())
    configure(acknowledge_consent=args.acknowledge_consent)


if __name__ == "__main__":
    main()
