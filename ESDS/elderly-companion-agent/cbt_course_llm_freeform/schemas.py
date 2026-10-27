from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from cbt_course_llm_freeform.azure_chat_client import ChatCompletionResult
from cbt_course_llm_freeform.interaction import InteractionReflection
from cbt_course_llm_freeform.learning_request import TeachingRequest
from cbt_course_llm_freeform.navigation import NavigationDecision
from cbt_course_llm_freeform.dialogue import TeachingTurn


class CourseMessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(default="", max_length=2000)
    idempotency_key: str = Field(min_length=8, max_length=80)
    action: Literal[
        "start_mood_check",
        "chat",
        "continue_lesson2",
        "skip_lesson2_step",
        "stop_lesson2_quiz",
        "edit_learning_goal",
        "skip_checkin",
        "confirm_record",
        "edit_record",
        "accept_practice",
        "decline_practice",
        "finish",
        "pause",
        "resume",
        "accept_carryover",
        "decline_carryover",
        "reuse_case",
        "request_check_hint",
        "skip_check_question",
        "continue_after_check",
        "start_check_retry",
        "finish_check_retry",
        "confirm_learning_goal",
        "skip_learning_goal",
        "defer_practice_field",
        "decline_practice_field",
        "request_less_probing",
        "show_brief_explanation",
        "continue_practice_dialogue",
    ] = "chat"
    expected_revision: int | None = Field(default=None, ge=0)


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    field: Literal[
        "thought_belief",
        "emotion_intensity",
        "relationship_note",
        "mood",
        "learning_response",
        "situation",
        "thought",
        "emotion",
        "behavior",
        "goal",
        "feedback",
    ]
    value: str = Field(min_length=1, max_length=500)
    source_message_id: str = Field(min_length=1, max_length=80)


class AssessmentSignal(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: Literal["confusion", "correction", "potential_conflict", "new_evidence"]
    quote: str = Field(min_length=1, max_length=200)
    source_message_id: str = Field(min_length=1, max_length=80)
    target_field: str | None = Field(default=None, max_length=40)
    reference_message_id: str | None = Field(default=None, max_length=80)
    comparable_context: bool = False


class TurnAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    signals: list[AssessmentSignal] = Field(default_factory=list, max_length=2)


class TeachingDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    reply: str = Field(min_length=1, max_length=1200)
    observations: list[Evidence] = Field(default_factory=list, max_length=8)
    advance: bool = False
    assessment: TurnAssessment = Field(default_factory=TurnAssessment)
    # Accept the former empty field for offline-client compatibility; no classification is active.
    domain_candidates: list[dict] = Field(default_factory=list, max_length=0)
    interaction: InteractionReflection | None = None
    learning_request: TeachingRequest | None = None
    turn_intent: TeachingTurn | None = None
    practice_origin: Literal["current_case", "personal_account", "different_case", "unclear"] = (
        "current_case"
    )
    next_practice_field: (
        Literal[
            "situation", "thought", "thought_belief", "emotion", "emotion_intensity", "behavior"
        ]
        | None
    ) = None
    case_options: list[str] = Field(default_factory=list, max_length=5)


class GuidanceReflection(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    update: Literal["replace", "no_change", "insufficient_evidence"]
    brief: str = Field(max_length=250)
    strategy: Literal[
        "continue_current",
        "clarify_missing_field",
        "rephrase_plainly",
        "ask_concrete_fact",
        "acknowledge_correction",
        "summarize_for_confirmation",
    ]
    focus_field: str | None = Field(default=None, max_length=40)
    source_message_ids: list[str] = Field(min_length=1, max_length=6)
    open_items: list[str] = Field(default_factory=list, max_length=3)
    previous_strategy_result: Literal["helped", "not_helped", "unknown"] = "unknown"


class GuidanceReflectionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    reflection: GuidanceReflection


class ReplyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    reply: str = Field(min_length=1, max_length=1200)


class ReflectionNote(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=250)
    source_message_ids: list[str] = Field(min_length=1, max_length=4)


class ReflectionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    observations: list[ReflectionNote] = Field(default_factory=list, max_length=3)
    suggestions: list[ReflectionNote] = Field(default_factory=list, max_length=3)
    hypotheses: list["LearningHypothesis"] = Field(default_factory=list, max_length=2)


class LearningHypothesis(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    text: str = Field(min_length=1, max_length=250)
    source_message_ids: list[str] = Field(min_length=1, max_length=4)
    context: str = Field(min_length=1, max_length=160)
    alternative_explanation: str = Field(min_length=1, max_length=180)
    next_action: str = Field(min_length=1, max_length=180)
    verification: str = Field(min_length=1, max_length=180)


class LegacyCheckAnswerDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, title="CheckAnswerDecision")
    verdict: Literal["matches", "partial", "does_not_match", "unclear", "needs_help", "not_answer"]
    reason: str = Field(min_length=1, max_length=180)
    source_message_id: str = Field(min_length=1, max_length=80)
    interaction: InteractionReflection | None = None


class CheckAnswerDecision(LegacyCheckAnswerDecision):
    reply: str | None = Field(default=None, min_length=1, max_length=1200)
    turn_intent: TeachingTurn | None = None


class CaseReviewDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    summary: str = Field(min_length=1, max_length=300)
    source_message_ids: list[str] = Field(min_length=1, max_length=8)


@dataclass(frozen=True)
class AgentResult:
    reply: str
    completion: ChatCompletionResult | None = None
    decision: TeachingDecision | None = None


@dataclass(frozen=True)
class StageResult:
    decision: (
        GuidanceReflectionResult
        | ReplyDecision
        | CheckAnswerDecision
        | InteractionReflection
        | NavigationDecision
    )
    completion: ChatCompletionResult


@dataclass(frozen=True)
class TurnResult:
    reply: str
    state: dict[str, Any]
    trace: dict[str, Any]
    attachment: dict[str, Any] = field(default_factory=dict)
    completion: ChatCompletionResult | None = None
    safety_event: str | None = None
