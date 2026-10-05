from __future__ import annotations

import hashlib
from dataclasses import dataclass

from daily_agent.prompt import DAILY_CHAT_SYSTEM_PROMPT
from webapp.config import settings


@dataclass(frozen=True)
class AgentVersion:
    label: str
    prompt_sha256: str


def _prompt_sha256(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def agent_version_for_mode(mode: str) -> AgentVersion:
    if mode == "daily_chat":
        return AgentVersion(
            label=settings.daily_chat_agent_version,
            prompt_sha256=_prompt_sha256(DAILY_CHAT_SYSTEM_PROMPT),
        )
    raise ValueError(f"Unsupported conversation mode: {mode}")
