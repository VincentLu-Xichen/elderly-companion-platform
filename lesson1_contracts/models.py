"""Types for a small, pure contract slice, not a replacement course state.

The caller supplies an authenticated, owned projection. This module can reject
inconsistent identities but cannot authenticate the caller or infer user intent.
"""
from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel, ConfigDict, Field, StrictFloat, StrictInt, StringConstraints,
    TypeAdapter, model_validator,
)

CONTRACT_VERSION = "lesson1-contract-foundation/1"
Identifier = Annotated[str, StringConstraints(min_length=1, max_length=100, pattern=r"\S")]
Quote = Annotated[str, StringConstraints(min_length=1, max_length=500, pattern=r"\S")]
ReplyText = Annotated[str, StringConstraints(min_length=1, max_length=1200, pattern=r"\S")]
FieldName = Literal[
    "situation", "thought", "emotion", "behavior", "thought_belief", "emotion_intensity",
]
Stage = Literal[
    "check_in", "learn", "practice", "review", "assessment", "check_feedback",
    "learning_goal", "plan", "summary",
]
BoundaryKind = Literal[
    "defer_thought_belief", "defer_emotion_intensity",
    "allow_thought_belief", "allow_emotion_intensity",
    "stop_conversation_questions", "allow_conversation_questions",
    "stop_case_questions", "allow_case_questions", "pause_lesson",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, allow_inf_nan=False)


class SourceMessage(StrictModel):
    message_id: Identifier
    conversation_id: Identifier
    sequence: int = Field(ge=0)
    role: Literal["learner", "agent"]
    text: Annotated[str, StringConstraints(min_length=1, pattern=r"\S")]


class EvidenceRef(StrictModel):
    source_message_id: Identifier
    quote: Quote


class FieldTarget(StrictModel):
    """Program-owned destination and the facts its value depends on."""

    target_ref: Identifier
    case_id: Identifier
    field: FieldName
    previous: EvidenceRef | None = None
    subject: EvidenceRef | None = None

    @model_validator(mode="after")
    def rating_needs_subject(self) -> Self:
        rating = self.field in {"thought_belief", "emotion_intensity"}
        if rating != (self.subject is not None):
            raise ValueError("Only a rating target requires its existing thought/emotion subject")
        return self


class CallFrame(StrictModel):
    contract_version: Literal["lesson1-contract-foundation/1"] = CONTRACT_VERSION
    lesson_id: Literal["lesson-1"] = "lesson-1"
    call_id: Identifier
    conversation_id: Identifier
    case_id: Identifier
    revision: int = Field(ge=0)
    stage: Stage
    role: Literal["teaching", "conversation"]
    supervisor_used: bool
    latest_message_id: Identifier
    sources: list[SourceMessage] = Field(min_length=1)
    targets: list[FieldTarget] = Field(default_factory=list)

    @model_validator(mode="after")
    def identities_are_consistent(self) -> Self:
        ids = [item.message_id for item in self.sources]
        sequences = [item.sequence for item in self.sources]
        refs = [item.target_ref for item in self.targets]
        fields = [item.field for item in self.targets]
        if len(ids) != len(set(ids)) or sequences != sorted(set(sequences)):
            raise ValueError("Sources need unique identities and strictly increasing sequence")
        if any(item.conversation_id != self.conversation_id for item in self.sources):
            raise ValueError("Every source must belong to this conversation")
        if (self.sources[-1].message_id != self.latest_message_id
                or self.sources[-1].role != "learner"):
            raise ValueError("The latest source must be the actual final learner message")
        if len(refs) != len(set(refs)) or len(fields) != len(set(fields)):
            raise ValueError("Targets need unique references and fields")
        if any(item.case_id != self.case_id for item in self.targets):
            raise ValueError("Targets must belong to the current case")
        return self


class FieldWrite(StrictModel):
    target_ref: Identifier
    source_message_id: Identifier
    value_quote: Quote


class BoundaryAction(EvidenceRef):
    kind: BoundaryKind


class TeachingProposal(StrictModel):
    mode: Literal["record_evidence"]
    observations: list[FieldWrite] = Field(min_length=1, max_length=8)


class WorkerReply(StrictModel):
    kind: Literal["reply"]
    reply: ReplyText
    pending_evidence: list[FieldWrite] = Field(default_factory=list, max_length=8)
    boundary_actions: list[BoundaryAction] = Field(default_factory=list, max_length=6)


class Escalation(StrictModel):
    reason: Annotated[str, StringConstraints(min_length=1, max_length=300, pattern=r"\S")]
    evidence_refs: list[EvidenceRef] = Field(min_length=1, max_length=6)


class WorkerHandoff(StrictModel):
    kind: Literal["handoff_request"]
    escalation: Escalation


Numeric = StrictInt | StrictFloat


class WeeklyScore(StrictModel):
    metric: Literal["weekly_mood"]
    value: Numeric = Field(ge=1, le=10)


class BeliefScore(StrictModel):
    metric: Literal["thought_belief"]
    value: Numeric = Field(ge=0, le=10)


class EmotionScore(StrictModel):
    metric: Literal["emotion_intensity"]
    value: Numeric = Field(ge=0, le=10)


Score = Annotated[WeeklyScore | BeliefScore | EmotionScore, Field(discriminator="metric")]
SCORE_ADAPTER = TypeAdapter(Score)


def validate_score(value):
    """Validate an already-extracted number; this does not parse or adopt a quote."""
    return SCORE_ADAPTER.validate_json(value) if isinstance(value, str) else SCORE_ADAPTER.validate_python(value)
