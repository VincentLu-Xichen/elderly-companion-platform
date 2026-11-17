"""038: strict domain types for the isolated single-dialogue execution slice.

Inputs are trusted, authenticated program projections, not public request bodies.
No environment, provider, application service or database is loaded here.
"""
from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from lesson1_contracts.models import (
    EvidenceRef, Identifier, Numeric, Quote, ReplyText, SourceMessage as BaseMessage,
    StrictModel,
)
from .course_types import CourseData, CoursePayload

CONTRACT_VERSION = "lesson1-dialogue/1.2"
STATE_VERSION = "lesson1-dialogue-state/2"
# Model reply remains capped at 1200; final display reserves room for the
# deterministic weekly-care sentence without truncating a valid model reply.
PresentedReply = Annotated[str, StringConstraints(min_length=1, max_length=1400, pattern=r"\S")]
Mode = Literal["teaching", "communicating", "paused"]
Phase = Literal["check_in", "learn", "practice", "review", "check", "check_feedback",
                "learning_goal", "plan", "summary"]
RecordField = Literal["situation", "thought", "emotion", "behavior"]
ScoreField = Literal["thought_belief", "emotion_intensity"]
CourseField = RecordField | ScoreField
RECORD_FIELDS = ("situation", "thought", "emotion", "behavior")
SUBJECTS = {"thought_belief": "thought", "emotion_intensity": "emotion"}


class Message(BaseMessage):
    # Known program metadata only; null does not prove semantic case membership.
    case_id: Identifier | None = None
    material_id: Identifier | None = None
    origin_mode: Mode | None = None


class ContextTag(EvidenceRef):
    relation: Literal['course_case', 'conversation_event', 'uncertain', 'quoted_example']
    case_id: Identifier | None = None


class MessageContext(StrictModel):
    origin_mode: Mode
    case_at_start: Identifier
    case_id: Identifier | None = None
    material_id: Identifier | None = None
    tags: list[ContextTag] = Field(default_factory=list, max_length=64)


class CaseStory(StrictModel):
    case_id: Identifier
    sources: list[EvidenceRef] = Field(min_length=1, max_length=6)
    permission_sources: list[EvidenceRef] = Field(min_length=1, max_length=6)


class CaseChoice(CaseStory):
    id: Identifier
    origin_case_id: Identifier
    status: Literal['pending', 'adopted', 'superseded', 'cancelled'] = 'pending'
    cancellation_sources: list[EvidenceRef] = Field(default_factory=list,max_length=6)


class Reference(EvidenceRef):
    id: Identifier


class Progress(StrictModel):
    phase: Phase = "practice"
    activity_id: Identifier = "personal-practice"
    field: CourseField | None = "situation"
    task_revision: int = Field(default=0, ge=0)
    attempts: int = Field(default=0, ge=0)


class Record(StrictModel):
    value: Quote
    revision: int = Field(ge=1)
    sources: list[EvidenceRef] = Field(min_length=1)


class Rating(StrictModel):
    value: Numeric = Field(ge=0, le=10)
    revision: int = Field(ge=1)
    subject_field: RecordField
    subject_revision: int = Field(ge=1)
    scale_id: Literal["course-0-10"] = "course-0-10"
    sources: list[EvidenceRef] = Field(min_length=1)


class RecordPayload(StrictModel):
    target_case_id: Identifier
    field: RecordField
    expected_field_revision: int = Field(ge=0)
    value: Quote


class ScorePayload(StrictModel):
    target_case_id: Identifier
    field: ScoreField
    expected_field_revision: int = Field(ge=0)
    value: Numeric = Field(ge=0, le=10)
    quote: Quote
    subject_revision: int | None = Field(default=None, ge=1)
    subject_action_id: Identifier | None = None
    scale_id: Literal["course-0-10"]

    @model_validator(mode="after")
    def one_subject(self) -> Self:
        if (self.subject_revision is None) == (self.subject_action_id is None):
            raise ValueError("A rating needs one existing subject revision or subject action")
        return self


WritePayload = Annotated[RecordPayload | ScorePayload, Field(discriminator="field")]
BoundaryKind = Literal["defer_field", "stop_topic_questions", "stop_case_questions",
                       "no_personal_case", "return_not_now", "pause_lesson"]


class BoundaryPayload(StrictModel):
    kind: BoundaryKind
    target_ref: Identifier
    scope: Literal["current_task", "current_case", "current_lesson"]

    @model_validator(mode="after")
    def scope_matches_kind(self) -> Self:
        if self.kind == "defer_field" and (self.target_ref not in (*RECORD_FIELDS, *SUBJECTS)
                                           or self.scope != "current_case"):
            raise ValueError("A deferred field needs a current-case field target")
        if self.kind in {"pause_lesson", "return_not_now", "no_personal_case"}:
            if self.scope != "current_lesson" or self.target_ref != "lesson":
                raise ValueError("Lesson boundaries need an explicit lesson scope")
        return self


class Boundary(StrictModel):
    id: Identifier
    content: BoundaryPayload
    case_id: Identifier
    task_revision: int
    sources: list[EvidenceRef]
    active: bool = True
    release_sources: list[EvidenceRef] = Field(default_factory=list)


class Pending(StrictModel):
    id: Identifier
    content: WritePayload
    sources: list[EvidenceRef]
    origin_revision: int = Field(ge=0)
    boundary_fingerprint: str
    status: Literal["pending", "adopted", "invalidated", "superseded"] = "pending"
    receipt_id: Identifier | None = None


class Invitation(StrictModel):
    id: Identifier
    assistant_message_id: Identifier
    task_revision: int
    case_id: Identifier
    sources: list[EvidenceRef]
    status: Literal["pending", "accepted", "declined", "superseded"] = "pending"
    answer_sources: list[EvidenceRef] = Field(default_factory=list)


class ActionBase(StrictModel):
    id: Identifier
    source_ref_ids: list[Identifier] = Field(min_length=1, max_length=6)
    depends_on: list[Identifier] = Field(default_factory=list, max_length=8)


class RecordAction(ActionBase):
    type: Literal["record_update"]
    payload: RecordPayload


class ScoreAction(ActionBase):
    type: Literal["score_update"]
    payload: ScorePayload


class StageAction(ActionBase):
    type: Literal["stage_evidence"]
    payload: WritePayload


class AdoptPayload(StrictModel):
    pending_id: Identifier


class AdoptAction(ActionBase):
    type: Literal["adopt_pending"]
    payload: AdoptPayload


class BoundaryAction(ActionBase):
    type: Literal["set_boundary"]
    payload: BoundaryPayload


class ReleasePayload(StrictModel):
    boundary_id: Identifier
    basis: Literal["explicit_permission", "provided_score"] = "explicit_permission"


class ReleaseAction(ActionBase):
    type: Literal["release_boundary"]
    payload: ReleasePayload


class InvitePayload(StrictModel):
    expected_task_revision: int = Field(ge=0)


class InviteAction(ActionBase):
    type: Literal["invite_return"]
    payload: InvitePayload


class StepPayload(StrictModel):
    expected_task_revision: int = Field(ge=0)
    operation: Literal["stay", "help", "select_field"]
    next_field: CourseField | None = None

    @model_validator(mode="after")
    def field_only_for_selection(self) -> Self:
        if (self.operation == "select_field") != (self.next_field is not None):
            raise ValueError("Only select_field has a next_field")
        return self


class StepAction(ActionBase):
    type: Literal["teaching_step"]
    payload: StepPayload


class CourseAction(ActionBase):
    type: Literal["course_action"]
    payload: CoursePayload


class SelectCasePayload(StrictModel):
    operation: Literal['stage', 'select']
    new_case_id: Identifier
    story_sources: list[EvidenceRef] = Field(min_length=1, max_length=6)


class AdoptCasePayload(StrictModel):
    operation: Literal['adopt']
    pending_id: Identifier


class CaseChangeAction(ActionBase):
    type: Literal['case_change']
    payload: Annotated[SelectCasePayload | AdoptCasePayload, Field(discriminator='operation')]


class CancelChoicePayload(StrictModel):
    pending_id: Identifier


class CancelChoiceAction(ActionBase):
    type: Literal['cancel_case_choice']
    payload: CancelChoicePayload


class RemovePayload(StrictModel):
    target_case_id: Identifier
    field: CourseField
    expected_field_revision: int = Field(ge=1)


class RemoveAction(ActionBase):
    type: Literal['record_remove']
    payload: RemovePayload


Action = Annotated[RecordAction | ScoreAction | StageAction | AdoptAction | BoundaryAction
                   | ReleaseAction | InviteAction | StepAction | CourseAction | CaseChangeAction
                   | CancelChoiceAction | RemoveAction, Field(discriminator="type")]


class ReflectionRequest(StrictModel):
    question: Quote
    scope: Literal["current_task", "current_case", "current_lesson"]
    source_ref_ids: list[Identifier] = Field(min_length=1, max_length=6)


class Output(StrictModel):
    contract_version: Literal["lesson1-dialogue/1.2"] = CONTRACT_VERSION
    based_on_revision: int = Field(ge=0)
    reply: ReplyText
    signal: Literal["none", "needs_switch", "resume_request", "conversation_closed",
                    "pause_request", "close_request"] = "none"
    signal_ref_ids: list[Identifier] = Field(default_factory=list, max_length=6)
    resume_target: Literal["previous_mode", "teaching"] | None = None
    resume_basis: Literal["explicit_request", "invitation_answer", "original_answer"] | None = None
    bridge_ready: bool = False
    actions: list[Action] = Field(default_factory=list, max_length=8)
    evidence_refs: list[Reference] = Field(default_factory=list, max_length=24)
    reflection_request: ReflectionRequest | None = None
    context_tags: list[ContextTag] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def signal_contract(self) -> Self:
        if (self.signal == "resume_request") != (self.resume_target is not None
                                                  and self.resume_basis is not None):
            raise ValueError("Resume needs a target and basis; other signals cannot carry them")
        if self.signal != "resume_request" and (self.resume_target is not None or self.resume_basis is not None):
            raise ValueError("Unexpected resume metadata")
        if self.signal != "none" and not self.signal_ref_ids:
            raise ValueError("A nonempty signal needs current learner evidence")
        return self


class Receipt(StrictModel):
    id: Identifier
    action_id: Identifier
    field: CourseField
    revision: int
    sources: list[EvidenceRef]
    pending_id: Identifier | None = None


class TurnEvent(StrictModel):
    request_id: Identifier
    input_fingerprint: str
    reply: PresentedReply
    mode_from: Mode
    mode_to: Mode
    rules: list[str]
    receipt_ids: list[Identifier]
    model_calls: int = Field(ge=0, le=1)


class ReflectionJob(StrictModel):
    id: Identifier
    question: Quote
    scope: Literal["current_task", "current_case", "current_lesson"]
    case_id: Identifier
    task_revision: int
    sources: list[EvidenceRef]
    origin_revision: int = Field(default=0, ge=0)
    status: Literal['pending', 'running', 'completed', 'failed'] = 'pending'
    attempted: bool = False
    findings: list['ReflectionFinding'] = Field(default_factory=list)
    error_code: str | None = None


class ReflectionFinding(StrictModel):
    text: Quote
    sources: list[EvidenceRef] = Field(min_length=1, max_length=6)


class StrategyCandidate(StrictModel):
    id: Identifier
    job_id: Identifier
    guidance: Quote
    scope: Literal['current_task', 'current_case', 'current_lesson']
    case_id: Identifier
    task_revision: int
    origin_revision: int = Field(ge=0)
    context_fingerprint: str
    sources: list[EvidenceRef] = Field(min_length=1, max_length=6)


class State(StrictModel):
    state_schema_version: Literal["lesson1-dialogue-state/2"] = STATE_VERSION
    contract_version: Literal["lesson1-dialogue/1.2"] = CONTRACT_VERSION
    conversation_id: Identifier
    participant_id: Identifier
    active_case_id: Identifier
    case_kind: Literal["personal", "fictional"] = "personal"
    archived_cases: list["ArchivedCase"] = Field(default_factory=list)
    course: CourseData = Field(default_factory=CourseData)
    revision: int = Field(default=0, ge=0)
    session_status: Literal["active", "ended", "completed"] = "active"
    flow_mode: Mode = "teaching"
    paused_reason: Literal["user_stop", "boundary", "safety"] | None = None
    suspended_mode: Literal["teaching", "communicating"] | None = None
    lesson_progress: Progress = Field(default_factory=Progress)
    records: dict[RecordField, Record] = Field(default_factory=dict)
    ratings: dict[ScoreField, Rating] = Field(default_factory=dict)
    field_versions: dict[CourseField, Annotated[int, Field(ge=0)]] = Field(default_factory=dict)
    boundaries: list[Boundary] = Field(default_factory=list)
    pending_evidence: list[Pending] = Field(default_factory=list)
    return_invitation: Invitation | None = None
    conversation_history: list[Message] = Field(default_factory=list)
    adoption_receipts: list[Receipt] = Field(default_factory=list)
    turn_events: list[TurnEvent] = Field(default_factory=list)
    reflection_jobs: list[ReflectionJob] = Field(default_factory=list)
    strategy_candidates: list[StrategyCandidate] = Field(default_factory=list)
    message_context: dict[Identifier, MessageContext] = Field(default_factory=dict)
    case_story: CaseStory | None = None
    case_choices: list[CaseChoice] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent(self) -> Self:
        paused = self.flow_mode == "paused"
        if paused != (self.paused_reason is not None and self.suspended_mode is not None):
            raise ValueError("Paused state requires its reason and preceding mode")
        if not paused and (self.paused_reason is not None or self.suspended_mode is not None):
            raise ValueError("Active mode cannot retain pause metadata")
        ids = [m.message_id for m in self.conversation_history]
        sequences = [m.sequence for m in self.conversation_history]
        if len(ids) != len(set(ids)) or sequences != sorted(set(sequences)):
            raise ValueError("History identities and sequence must be unique and ordered")
        if any(m.conversation_id != self.conversation_id for m in self.conversation_history):
            raise ValueError("History is owned by one conversation")
        messages = {m.message_id: m for m in self.conversation_history}
        for message_id, metadata in self.message_context.items():
            if message_id not in messages:
                raise ValueError('Message metadata needs its source message')
            message = messages[message_id]
            if message.origin_mode is not None and message.origin_mode != metadata.origin_mode:
                raise ValueError('Message origin mode must match stored metadata')
            if any(t.source_message_id != message_id or t.quote not in message.text for t in metadata.tags):
                raise ValueError('Message tags need exact local source spans')
        stories = [*self.case_choices, *([self.case_story] if self.case_story else [])]
        for story in stories:
            for source in [*story.sources, *story.permission_sources, *getattr(story,'cancellation_sources',[])]:
                msg = messages.get(source.source_message_id)
                if msg is None or msg.role != 'learner' or msg.material_id is not None or source.quote not in msg.text:
                    raise ValueError('Case selection needs learner story and permission sources')
            if isinstance(story,CaseChoice) and ((story.status=='cancelled') != bool(story.cancellation_sources)):
                raise ValueError('Cancelled case choice needs its withdrawal sources')
        if self.case_story and self.case_story.case_id != self.active_case_id:
            raise ValueError('Enrolled story belongs to the active case')
        for stored in [*self.records.values(), *self.ratings.values(), *self.boundaries]:
            for source in stored.sources:
                message = messages.get(source.source_message_id)
                if (message is None or message.role != "learner" or message.material_id is not None
                        or source.quote not in message.text):
                    raise ValueError("Stored learner facts/constraints need live learner sources")
        if any(p.origin_revision > self.revision for p in self.pending_evidence):
            raise ValueError("Pending evidence cannot originate in a future revision")
        for field, record in self.records.items():
            if self.field_versions.get(field) != record.revision:
                raise ValueError("Record revision mismatch")
        for field, rating in self.ratings.items():
            subject = self.records.get(SUBJECTS[field])
            if (rating.subject_field != SUBJECTS[field] or subject is None
                    or rating.subject_revision != subject.revision
                    or self.field_versions.get(field) != rating.revision):
                raise ValueError("Rating must reference its current subject")
        for collection in (self.boundaries, self.pending_evidence, self.adoption_receipts,
                           self.reflection_jobs, self.strategy_candidates, self.case_choices):
            if len({item.id for item in collection}) != len(collection):
                raise ValueError("Stored item identities must be unique")
        if len({e.request_id for e in self.turn_events}) != len(self.turn_events):
            raise ValueError("Request identities must be unique")
        jobs = {job.id: job for job in self.reflection_jobs}
        for item in self.strategy_candidates:
            if item.job_id not in jobs or jobs[item.job_id].status != 'completed':
                raise ValueError('A strategy needs a completed reflection job')
            for source in item.sources:
                if source.source_message_id not in messages or source.quote not in messages[source.source_message_id].text:
                    raise ValueError('Strategy evidence must remain verifiable in this conversation')
        return self

    @property
    def teaching_cursor(self) -> dict:
        return {**self.lesson_progress.model_dump(), "case_id": self.active_case_id}


class TurnResult(StrictModel):
    state: State
    reply: PresentedReply
    replayed: bool = False
    model_calls: int = Field(ge=0, le=1)


def new_state(conversation_id: str, participant_id: str, case_id: str) -> State:
    return State(conversation_id=conversation_id, participant_id=participant_id,
                 active_case_id=case_id)


class ArchivedCase(StrictModel):
    case_id: Identifier
    case_kind: Literal["personal", "fictional"]
    records: dict[RecordField, Record]
    ratings: dict[ScoreField, Rating]
    story: CaseStory | None = None


State.model_rebuild()


def new_course_state(conversation_id: str, participant_id: str, case_id: str) -> State:
    return State(conversation_id=conversation_id, participant_id=participant_id,
                 active_case_id=case_id, course=CourseData(enabled=True),
                 lesson_progress=Progress(phase="check_in", activity_id="weekly-mood", field=None))
