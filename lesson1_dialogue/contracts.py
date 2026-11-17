"""Call-specific schema and parsing share one adapter; provenance is checked too."""
from __future__ import annotations

import copy
from typing import Annotated, Union

from pydantic import Field, TypeAdapter, ValidationError, create_model

from .models import (
    AdoptAction, BoundaryAction, InviteAction, Message, Output, RecordAction,
    ReleaseAction, ScoreAction, StageAction, State, StepAction, CaseChangeAction,
    CancelChoiceAction, RemoveAction,
)

RECORD_PHASES = {"learn", "practice", "review"}


class DialogueError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def checked_state(value: State | dict) -> State:
    try:
        return State.model_validate(value.model_dump() if isinstance(value, State)
                                    else copy.deepcopy(value))
    except ValidationError as exc:
        raise DialogueError("state_contract") from exc


def checked_message(state: State, value: Message | dict) -> Message:
    try:
        message = Message.model_validate(value.model_dump() if isinstance(value, Message)
                                         else copy.deepcopy(value))
    except ValidationError as exc:
        raise DialogueError("input_contract") from exc
    if message.conversation_id != state.conversation_id or message.role != "learner":
        raise DialogueError("input_owner_or_role")
    if any(m.message_id == message.message_id for m in state.conversation_history):
        raise DialogueError("duplicate_message")
    if state.conversation_history and message.sequence <= state.conversation_history[-1].sequence:
        raise DialogueError("input_sequence")
    return message


class DialogueContract:
    def __init__(self, state: State | dict, message: Message | dict):
        self._state = checked_state(state)
        self._message = checked_message(self._state, message)
        variants = [BoundaryAction]
        if self.state.lesson_progress.phase in RECORD_PHASES:
            variants.extend((CancelChoiceAction,RemoveAction))
        if self.state.flow_mode != "paused":
            variants.append(ReleaseAction)
        if self.state.flow_mode == "communicating":
            variants.extend((StageAction, InviteAction))
        elif self.state.flow_mode == "teaching" and self.state.lesson_progress.phase in RECORD_PHASES:
            variants.extend((RecordAction, ScoreAction, StageAction, AdoptAction, StepAction))
        if self.state.flow_mode!='paused' and self.state.lesson_progress.phase in RECORD_PHASES:
            variants.append(CaseChangeAction)
        if self.state.course.enabled and self.state.flow_mode == "teaching":
            from .course import action_for_phase
            variants.append(action_for_phase(self.state.lesson_progress.phase, include_staging=True))
        elif self.state.course.enabled and self.state.flow_mode == "communicating":
            from .course import staging_action_for_phase
            staged=staging_action_for_phase(self.state.lesson_progress.phase)
            if staged is not None:variants.append(staged)
        action_type = (Annotated[Union[tuple(variants)], Field(discriminator="type")]
                       if len(variants) > 1 else variants[0])
        self._adapter = TypeAdapter(create_model(
            "OutputForTurn", __base__=Output,
            actions=(list[action_type], Field(default_factory=list, max_length=8))))
        self.allowed_actions = tuple(v.model_fields["type"].annotation.__args__[0] for v in variants)

    @property
    def state(self) -> State:
        return self._state.model_copy(deep=True)

    @property
    def message(self) -> Message:
        return self._message.model_copy(deep=True)

    def schema(self) -> dict:
        return copy.deepcopy(self._adapter.json_schema())

    def parse(self, raw: dict | str | Output) -> Output:
        if isinstance(raw, Output):
            raw = raw.model_dump()
        try:
            output = (self._adapter.validate_json(raw) if isinstance(raw, str)
                      else self._adapter.validate_python(copy.deepcopy(raw)))
        except ValidationError as exc:
            raise DialogueError("output_contract") from exc
        if output.based_on_revision != self.state.revision:
            raise DialogueError("revision_conflict")
        refs = {ref.id: ref for ref in output.evidence_refs}
        if len(refs) != len(output.evidence_refs):
            raise DialogueError("duplicate_reference")
        messages = {m.message_id: m for m in [*self.state.conversation_history, self.message]}
        for ref in refs.values():
            source = messages.get(ref.source_message_id)
            if source is None or ref.quote not in source.text:
                raise DialogueError("source_quote_or_missing")

        def validate(ids, *, current, learner=True):
            for ref_id in ids:
                ref = refs.get(ref_id)
                if ref is None:
                    raise DialogueError("reference_missing")
                source = messages[ref.source_message_id]
                if learner and (source.role != "learner" or source.material_id is not None):
                    raise DialogueError("source_role_or_material")
                if current and source.message_id != self.message.message_id:
                    raise DialogueError("current_source_required")

        validate(output.signal_ref_ids, current=True)
        for action in output.actions:
            adopting_response=action.type=="course_action" and action.payload.operation in {"adopt_check_answer","adopt_goal"}
            adopting_case=action.type=='case_change' and action.payload.operation=='adopt'
            validate(action.source_ref_ids,current=action.type not in {"stage_evidence","adopt_pending"} and not adopting_response and not adopting_case,
                     learner=True)
        for tag in output.context_tags:
            if (tag.source_message_id!=self.message.message_id or tag.quote not in self.message.text
                    or self.message.material_id is not None):raise DialogueError('context_tag_source')
        if output.reflection_request is not None:
            validate(output.reflection_request.source_ref_ids, current=False, learner=False)
        return output
