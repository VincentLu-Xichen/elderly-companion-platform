"""Dependency-injected single-call runtime; caller owns auth, encryption and audit IO."""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Callable, Protocol

from .contracts import DialogueError, checked_message, checked_state
from .engine import apply_turn, replay, safety_pause
from .models import Message, State, TurnResult
from .prompts import system_prompt
from .wire import WireContract


@dataclass(frozen=True)
class CallRequest:
    system_prompt: str
    context: dict
    output_schema: dict
    purpose: str = 'single_dialogue'


class Client(Protocol):
    def complete(self, request: CallRequest) -> dict | str: ...


def build_request(state: State, message: Message, *, contract=None) -> CallRequest:
    contract = contract or WireContract(state, message)
    return CallRequest(system_prompt(state.flow_mode), contract.context(), contract.schema())


class DialogueRuntime:
    def __init__(self, client: Client, *, safety_guard: Callable[[Message], bool],
                 max_input_chars: int = 200_000):
        self.client = client
        # Deliberately mandatory: a later service cannot silently skip its safety guard.
        self.safety_guard = safety_guard
        self.max_input_chars = max_input_chars
        self.binding_audit = None

    def turn(self, state: State | dict, message: Message | dict, request_id: str,
             *, on_reply_delta=None) -> TurnResult:
        cached = replay(state, message, request_id)
        if cached is not None:
            return cached
        before = checked_state(state)
        incoming = checked_message(before, message)
        if before.session_status != "active":
            raise DialogueError("session_closed")
        unsafe = self.safety_guard(incoming)
        if not isinstance(unsafe, bool):
            raise DialogueError("guard_contract")
        if unsafe:
            return safety_pause(before, incoming, request_id)
        contract = WireContract(before, incoming)
        self.binding_audit = contract.audit_view()
        request = build_request(before, incoming, contract=contract)
        # Explicit offline character budget, not a claim about any provider token limit.
        size = len(request.system_prompt) + len(json.dumps(request.context, ensure_ascii=False))
        size += len(json.dumps(request.output_schema, ensure_ascii=False))
        if size > self.max_input_chars:
            raise DialogueError("context_limit")
        stream=getattr(self.client,'complete_stream',None)
        output = stream(request,on_reply_delta) if on_reply_delta is not None and stream is not None else self.client.complete(request)
        try:
            bound = contract.bind(output)
        finally:
            self.binding_audit = contract.audit_view()
        return apply_turn(before, incoming, bound, request_id, model_calls=1)
