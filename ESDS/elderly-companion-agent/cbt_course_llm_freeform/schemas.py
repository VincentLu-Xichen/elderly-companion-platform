from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from cbt_course_llm_freeform.azure_chat_client import ChatCompletionResult


class CourseMessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=2000)
    idempotency_key: str = Field(min_length=8, max_length=80)


@dataclass(frozen=True)
class AgentResult:
    reply: str
    completion: ChatCompletionResult


@dataclass(frozen=True)
class TurnResult:
    reply: str
    state: dict[str, Any]
    trace: dict[str, Any]
    attachment: dict[str, Any] = field(default_factory=dict)
    completion: ChatCompletionResult | None = None
    safety_event: str | None = None
