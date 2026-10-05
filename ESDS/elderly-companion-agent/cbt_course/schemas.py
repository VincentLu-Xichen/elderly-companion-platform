from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from cbt_course.azure_chat_client import ChatCompletionResult


SafetyCategory = Literal["none", "self_harm", "medical_emergency", "fraud"]


class CourseMessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=2000)
    idempotency_key: str = Field(min_length=8, max_length=80)


class CourseExtractedValues(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(default="", max_length=2000)


class CourseTurnDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: str = Field(min_length=1, max_length=40)
    extracted_values: CourseExtractedValues = Field(default_factory=CourseExtractedValues)
    acknowledgement: str = Field(default="", max_length=240)
    safety_category: SafetyCategory = "none"


@dataclass(frozen=True)
class CourseAgentResult:
    decision: CourseTurnDecision
    completion: ChatCompletionResult


@dataclass(frozen=True)
class CourseTurnResult:
    reply: str
    state: dict[str, Any]
    trace: dict[str, Any]
    attachment: dict[str, Any] = field(default_factory=dict)
    homework_entry: dict[str, str] | None = None
    completion: ChatCompletionResult | None = None
    safety_event: str | None = None
