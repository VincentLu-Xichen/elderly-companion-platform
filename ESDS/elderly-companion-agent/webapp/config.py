from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from dotenv import load_dotenv

load_dotenv()


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _database_url() -> str:
    value = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or "sqlite:///./roleplay_chat.db"
    if value.startswith("postgres://"):
        value = "postgresql+psycopg://" + value.removeprefix("postgres://")
    elif value.startswith("postgresql://"):
        value = "postgresql+psycopg://" + value.removeprefix("postgresql://")

    if value.startswith("postgresql+psycopg://"):
        parsed = urlsplit(value)
        query = urlencode(
            [(key, item) for key, item in parse_qsl(parsed.query, keep_blank_values=True) if key not in {"supa", "workaround"}]
        )
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, parsed.fragment))
    return value


@dataclass(frozen=True)
class Settings:
    database_url: str = _database_url()
    database_pool_mode: str = os.getenv(
        "DATABASE_POOL_MODE", "transaction" if _bool_env("VERCEL", False) else "application"
    ).lower()
    app_secret: str = os.getenv("APP_SECRET", "local-development-secret-change-me")
    data_encryption_key: str = os.getenv("DATA_ENCRYPTION_KEY", "")
    invite_codes: str = os.getenv("INVITE_CODES", "student-001:demo001,student-002:demo002")
    admin_password: str = os.getenv("ADMIN_PASSWORD", "change-me")
    consent_version: str = os.getenv("CONSENT_VERSION", "2026-07-v1")
    cbt_course_agent_version: str = os.getenv("CBT_COURSE_AGENT_VERSION", "course-v1")
    daily_chat_agent_version: str = os.getenv("DAILY_CHAT_AGENT_VERSION", "daily-chat-v1")
    cookie_secure: bool = _bool_env("COOKIE_SECURE", False)
    session_hours: int = int(os.getenv("SESSION_HOURS", "12"))
    max_message_chars: int = int(os.getenv("MAX_MESSAGE_CHARS", "2000"))
    rate_limit_per_minute: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))
    voice_bridge_enabled: bool = _bool_env("VOICE_BRIDGE_ENABLED", False)
    voice_bridge_token: str = os.getenv("VOICE_BRIDGE_TOKEN", "")
    voice_device_id: str = os.getenv("VOICE_DEVICE_ID", "")
    voice_participant_label: str = os.getenv(
        "VOICE_PARTICIPANT_LABEL", "esds-voice-user"
    )
    voice_consent_acknowledged: bool = _bool_env(
        "VOICE_CONSENT_ACKNOWLEDGED", False
    )
    environment: str = os.getenv("APP_ENV", "development")
    is_vercel: bool = _bool_env("VERCEL", False)

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


settings = Settings()
