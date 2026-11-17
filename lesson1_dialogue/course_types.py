"""Typed course operations. No provider, web or database imports."""
from typing import Annotated, Literal
from pydantic import Field
from lesson1_contracts.models import EvidenceRef, Identifier, Numeric, Quote, StrictModel


class Weekly(StrictModel):
    operation: Literal["weekly_score"]
    value: Numeric = Field(ge=1, le=10)
    quote: Quote


class Move(StrictModel):
    operation: Literal["skip_weekly", "start_learning", "start_practice", "show_review",
        "start_check", "check_hint", "skip_check", "start_retry", "finish_retry",
        "after_check", "skip_goal", "accept_plan", "decline_plan", "go_summary", "finish",
        "choose_fictional", "choose_personal"]


class ConfirmRecord(StrictModel):
    operation: Literal["confirm_record"]
    record_fingerprint: str = Field(min_length=64, max_length=64)


class CheckAnswer(StrictModel):
    operation: Literal["check_answer"]
    attempt_id: Literal["first", "retry"]
    question_index: int = Field(ge=0, le=3)
    verdict: Literal["matches", "partial", "does_not_match", "unclear"]
    reason: Quote


class SetGoal(StrictModel):
    operation: Literal["set_goal"]
    value: Quote


class ConfirmGoal(StrictModel):
    operation: Literal["confirm_goal"]
    expected_goal_revision: int = Field(ge=1)


class StageCheck(StrictModel):
    operation: Literal["stage_check_answer"]
    attempt_id: Literal["first","retry"]
    question_index: int = Field(ge=0,le=3)
    value: Quote


class AdoptCheck(StrictModel):
    operation: Literal["adopt_check_answer"]
    pending_id: Identifier
    verdict: Literal["matches","partial","does_not_match","unclear"]
    reason: Quote


class StageGoal(StrictModel):
    operation: Literal["stage_goal"]
    expected_goal_revision: int = Field(ge=0)
    value: Quote


class AdoptGoal(StrictModel):
    operation: Literal["adopt_goal"]
    pending_id: Identifier


ResponseContent=Annotated[StageCheck|StageGoal,Field(discriminator="operation")]


class PendingResponse(StrictModel):
    id: Identifier
    content: ResponseContent
    task_revision: int = Field(ge=0)
    sources: list[EvidenceRef] = Field(min_length=1)
    status: Literal["pending","adopted","superseded"]="pending"
    adopted_revision: int | None = None


CoursePayload = Annotated[Weekly | Move | ConfirmRecord | CheckAnswer | SetGoal | ConfirmGoal |
                          StageCheck | AdoptCheck | StageGoal | AdoptGoal,
                          Field(discriminator="operation")]


class Answer(StrictModel):
    question_index: int
    verdict: Literal["matches", "partial", "does_not_match", "unclear", "not_observed"]
    reason: Quote
    sources: list[EvidenceRef] = Field(min_length=1)
    assisted: bool = False
    prior_feedback: bool = False


class Attempt(StrictModel):
    status: Literal["not_started", "active", "completed", "stopped"] = "not_started"
    index: int = Field(default=0, ge=0, le=4)
    answers: list[Answer] = Field(default_factory=list)
    hints: list[int] = Field(default_factory=list)


class Confirmation(StrictModel):
    fingerprint: str
    sources: list[EvidenceRef] = Field(min_length=1)


class Goal(StrictModel):
    value: Quote
    revision: int = Field(ge=1)
    sources: list[EvidenceRef] = Field(min_length=1)


class CourseData(StrictModel):
    enabled: bool = False
    weekly_score: Numeric | None = Field(default=None, ge=1, le=10)
    weekly_skipped: bool = False
    weekly_sources: list[EvidenceRef] = Field(default_factory=list)
    confirmation: Confirmation | None = None
    first: Attempt = Field(default_factory=Attempt)
    retry: Attempt = Field(default_factory=Attempt)
    goal: Goal | None = None
    goal_revision: int = Field(default=0, ge=0)
    goal_confirmed_revision: int | None = None
    goal_confirmation_sources: list[EvidenceRef] = Field(default_factory=list)
    goal_skipped: bool = False
    plan_status: Literal["undecided", "accepted", "declined"] = "undecided"
    plan_sources: list[EvidenceRef] = Field(default_factory=list)
    pending_responses: list[PendingResponse] = Field(default_factory=list)
