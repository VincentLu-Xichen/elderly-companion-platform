from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from cbt_course_llm_freeform.azure_chat_client import ChatCompletionResult
from cbt_course_llm_freeform.interaction import InteractionReflection
from cbt_course_llm_freeform.navigation import NavigationDecision


class CourseMessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(default="", max_length=2000)
    idempotency_key: str = Field(min_length=8, max_length=80)
    action: Literal["chat", "skip_checkin", "confirm_record", "edit_record", "accept_practice", "decline_practice", "finish", "pause", "resume", "accept_carryover", "decline_carryover", "reuse_case", "accept_pattern", "reject_pattern", "unsure_pattern", "no_pattern", "choose_activation", "choose_exposure", "choose_sleep", "choose_relaxation", "change_path", "request_check_hint", "skip_check_question", "continue_after_check", "start_check_retry", "finish_check_retry", "confirm_learning_goal", "skip_learning_goal", "defer_practice_field", "decline_practice_field", "request_less_probing", "show_brief_explanation", "continue_practice_dialogue"] = "chat"
    expected_revision: int | None = Field(default=None, ge=0)


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    field: Literal["mood", "learning_response", "situation", "thought", "emotion", "behavior", "awareness_note", "goal", "feedback",
        "action_fit", "alternative_action", "safety_note", "activity_goal", "first_step", "when_where", "barrier_plan", "feared_prediction", "graded_steps",
        "evidence_for", "evidence_against", "balanced_thought", "next_step", "sleep_pattern", "sleep_habit", "stress_cue", "relax_method",
        "early_signal", "helpful_skill", "response_plan", "support_plan", "review_plan"]
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


class PatternCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    category: Literal["mind_reading", "catastrophising", "overgeneralisation", "all_or_nothing"]
    basis_field: Literal["thought", "awareness_note"]
    basis_quote: str = Field(min_length=1, max_length=500)
    explanation: str = Field(min_length=1, max_length=180)


class TeachingDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    reply: str = Field(min_length=1, max_length=1200)
    observations: list[Evidence] = Field(default_factory=list, max_length=4)
    advance: bool = False
    assessment: TurnAssessment = Field(default_factory=TurnAssessment)
    domain_candidates: list[PatternCandidate] = Field(default_factory=list, max_length=1)
    interaction: InteractionReflection | None = None
    practice_origin: Literal["current_case", "personal_account", "different_case", "unclear"] = "current_case"


class GuidanceReflection(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    update: Literal["replace", "no_change", "insufficient_evidence"]
    brief: str = Field(max_length=250)
    strategy: Literal["continue_current", "clarify_missing_field", "rephrase_plainly", "ask_concrete_fact", "acknowledge_correction", "summarize_for_confirmation"]
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


class CheckAnswerDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    verdict: Literal["matches", "partial", "does_not_match", "unclear", "needs_help"]
    reason: str = Field(min_length=1, max_length=180)
    source_message_id: str = Field(min_length=1, max_length=80)


@dataclass(frozen=True)
class AgentResult:
    reply: str
    completion: ChatCompletionResult | None = None
    decision: TeachingDecision | None = None


@dataclass(frozen=True)
class StageResult:
    decision: GuidanceReflectionResult | ReplyDecision | CheckAnswerDecision | InteractionReflection | NavigationDecision
    completion: ChatCompletionResult


@dataclass(frozen=True)
class TurnResult:
    reply: str
    state: dict[str, Any]
    trace: dict[str, Any]
    attachment: dict[str, Any] = field(default_factory=dict)
    completion: ChatCompletionResult | None = None
    safety_event: str | None = None
