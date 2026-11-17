"""Pure, atomic-on-copy execution; no IO, inference or database transaction claims."""
from __future__ import annotations

import hashlib
import json
import re

from lesson1_contracts.models import EvidenceRef, validate_score

from .contracts import DialogueContract, DialogueError, checked_message, checked_state
from .models import Message, Output, RECORD_FIELDS, SUBJECTS, State, TurnResult


def fingerprint(value) -> str:
    if isinstance(value,Message):
        value=value.model_dump(exclude={'origin_mode'})
    elif hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     allow_nan=False).encode()).hexdigest()


def _id(kind, request_id, action_id=""):
    return kind + "-" + fingerprint([request_id, action_id])[:24]


def replay(state: State | dict, message: Message | dict, request_id: str) -> TurnResult | None:
    state = checked_state(state)
    # Replay before rejecting a message already saved by this same request.
    message = Message.model_validate(message.model_dump() if isinstance(message, Message) else message)
    for event in state.turn_events:
        if event.request_id == request_id:
            if event.input_fingerprint != fingerprint(message):
                raise DialogueError("idempotency_conflict")
            return TurnResult(state=state, reply=event.reply, replayed=True, model_calls=0)
    return None


def _active(data, kind=None, target=None):
    for boundary in data["boundaries"]:
        content = boundary["content"]
        if not boundary["active"]:
            continue
        if content["scope"] != "current_lesson" and boundary["case_id"] != data["active_case_id"]:
            continue
        if (content["scope"] == "current_task"
                and boundary["task_revision"] != data["lesson_progress"]["task_revision"]):
            continue
        if kind is not None and content["kind"] != kind:
            continue
        if target is not None and content["target_ref"] != target:
            continue
        yield boundary


def _boundary_fingerprint(data, field):
    relevant = [b for b in _active(data) if b["content"]["kind"] in {"no_personal_case", "stop_case_questions"}
                or (b["content"]["kind"] == "defer_field" and b["content"]["target_ref"] == field)]
    return fingerprint(relevant)


def _release(data, kinds, sources, target=None):
    for b in _active(data, target=target):
        if b["content"]["kind"] in kinds:
            b.update(active=False, release_sources=sources)


def _ordered(actions):
    remaining = {a.id: a for a in actions}
    if len(remaining) != len(actions):
        raise DialogueError("duplicate_action")
    ids = set(remaining)
    if any(dep not in ids for action in actions for dep in action.depends_on):
        raise DialogueError("dependency_missing")
    if any(a.type in {"set_boundary", "release_boundary"} and any(
            remaining[d].type not in {"set_boundary", "release_boundary"} for d in a.depends_on)
            for a in actions):
        raise DialogueError("boundary_dependency")
    result, done = [], set()
    while remaining:
        ready = [a for a in remaining.values() if set(a.depends_on) <= done]
        if not ready:
            raise DialogueError("dependency_cycle")
        # Apply user constraints before field writes, independent of array order.
        action = min(ready, key=lambda a: 0 if a.type in {'set_boundary','release_boundary'}
                     else 1 if a.type=='case_change' else 2)
        result.append(action)
        done.add(action.id)
        del remaining[action.id]
    return result


def _sources(output, ids):
    refs = {ref.id: ref for ref in output.evidence_refs}
    return [EvidenceRef(source_message_id=refs[i].source_message_id,
                        quote=refs[i].quote).model_dump() for i in ids]


def _check_target(data, payload, sources, messages, expected_versions=None):
    from .context import enrolled_source, guard_course_source
    if payload.target_case_id != data["active_case_id"]:
        raise DialogueError("case_mismatch")
    versions = data["field_versions"] if expected_versions is None else expected_versions
    if payload.expected_field_revision != versions.get(payload.field, 0):
        raise DialogueError("field_revision_conflict")
    for source in sources:
        msg = messages.get(source["source_message_id"])
        if msg is None or msg.role != "learner" or msg.material_id is not None:
            raise DialogueError("source_role_or_missing")
        if source["quote"] not in msg.text:
            raise DialogueError("source_quote_or_missing")
        if msg.case_id is not None and msg.case_id != payload.target_case_id and not enrolled_source(data,source,payload.target_case_id):
            raise DialogueError("source_case_mismatch")
        guard_course_source(data,source,messages,payload.target_case_id)
    # Records may be faithful natural-language summaries. Exact original evidence
    # remains mandatory above; equivalence is logged for review, not asserted here.
    if payload.field in SUBJECTS and not any(payload.quote in source["quote"] for source in sources):
        raise DialogueError("value_not_in_evidence")


def _subject(data, payload, completed, action=None):
    subject_field = SUBJECTS[payload.field]
    subject = data["records"].get(subject_field)
    if subject is None:
        raise DialogueError("subject_missing")
    expected = payload.subject_revision
    if payload.subject_action_id is not None:
        origin = completed.get(payload.subject_action_id)
        if (action is None or payload.subject_action_id not in action.depends_on
                or origin != (subject_field, subject["revision"])):
            raise DialogueError("subject_dependency")
        expected = origin[1]
    if expected != subject["revision"]:
        raise DialogueError("subject_revision_conflict")
    return subject_field, subject["revision"]


def _write(data, payload, sources, messages, completed, request_id, action,
           pending_id=None, expected_versions=None):
    _check_target(data, payload, sources, messages, expected_versions)
    if data["case_kind"] == "personal" and any(_active(data, "no_personal_case")):
        raise DialogueError("personal_case_blocked")
    field = payload.field
    revision = data["field_versions"].get(field, 0) + 1
    if field in RECORD_FIELDS:
        data["records"][field] = {"value": payload.value, "revision": revision, "sources": sources}
        for rating, subject in SUBJECTS.items():
            if field == subject and rating in data["ratings"]:
                del data["ratings"][rating]
                data["field_versions"][rating] = data["field_versions"].get(rating, 0) + 1
    else:
        validate_score({"metric": field, "value": payload.value})
        numbers = re.findall(r"(?<![0-9.])[-+]?\d+(?:\.\d+)?(?![0-9.])", payload.quote)
        if len(numbers) != 1 or float(numbers[0]) != payload.value:
            raise DialogueError("score_quote_mismatch")
        subject, subject_revision = _subject(data, payload, completed, action)
        data["ratings"][field] = {"value": payload.value, "revision": revision,
            "subject_field": subject, "subject_revision": subject_revision,
            "scale_id": payload.scale_id, "sources": sources}
    data["field_versions"][field] = revision
    from .context import remember_course_use
    remember_course_use(data,sources,data['active_case_id'])
    data["course"]["confirmation"] = None
    _release(data, {"defer_field"}, sources, target=field)
    receipt_id = _id("receipt", request_id, action.id)
    data["adoption_receipts"].append({"id": receipt_id, "action_id": action.id,
        "field": field, "revision": revision, "sources": sources, "pending_id": pending_id})
    completed[action.id] = (field, revision)
    return receipt_id


def _apply_mode(data, before, output, signal_sources, message, rules):
    signal = output.signal
    brief = message.text.strip().strip("。.!！?？ ") in {"好", "好的", "嗯", "行", "可以"}
    if signal == "resume_request" and brief and output.resume_basis != "invitation_answer":
        raise DialogueError("ambiguous_resume")
    if signal == "resume_request" and output.resume_basis == "invitation_answer":
        invitation = data["return_invitation"]
        if (before.flow_mode != "communicating" or invitation is None
                or invitation["status"] != "pending"
                or invitation["task_revision"] != before.lesson_progress.task_revision
                or invitation["case_id"] != before.active_case_id
                or not before.conversation_history
                or before.conversation_history[-1].message_id != invitation["assistant_message_id"]):
            raise DialogueError("invitation_not_current")
    if signal == "close_request":
        data["session_status"] = "ended"
        rules.append("G2")
        return
    if signal == "pause_request":
        if before.flow_mode != "paused":
            data.update(flow_mode="paused", paused_reason="user_stop", suspended_mode=before.flow_mode)
        rules.append("G3")
        return
    if before.flow_mode == "paused":
        if signal == "resume_request" and before.paused_reason != "safety":
            target = before.suspended_mode if output.resume_target == "previous_mode" else "teaching"
            data.update(flow_mode=target, paused_reason=None, suspended_mode=None)
            _release(data, {"pause_lesson", "return_not_now"}, signal_sources)
            rules.append("P1" if output.resume_target == "previous_mode" else "P2")
        else:
            rules.append("P3" if before.paused_reason == "safety" else "P5")
        return
    if any(_active(data, "pause_lesson")):
        data.update(flow_mode="paused", paused_reason="boundary", suspended_mode=before.flow_mode)
        rules.append("G3")
        return
    if signal == "resume_request":
        if output.resume_target != "teaching":
            raise DialogueError("resume_target")
        invitation = data["return_invitation"]
        if output.resume_basis == "original_answer" and not any(
                a.type == "stage_evidence" or (a.type=="course_action" and
                a.payload.operation in {"stage_check_answer","stage_goal"}) for a in output.actions):
            raise DialogueError("original_answer_missing")
        if invitation is not None and invitation["status"] == "pending":
            invitation.update(status="accepted", answer_sources=signal_sources)
        _release(data, {"return_not_now"}, signal_sources)
        data["flow_mode"] = "teaching"
        rules.append("T3" if before.flow_mode == "teaching" else "C1")
    elif signal == "needs_switch":
        data["flow_mode"] = "communicating"
        rules.append("T1" if before.flow_mode == "teaching" else "C5")
    else:
        rules.append("T2" if before.flow_mode == "teaching" else
                     "C2" if output.bridge_ready or signal == "conversation_closed" else "C3")


def _remove_record(data,payload,sources,messages,request_id,action):
    if payload.target_case_id!=data['active_case_id']:raise DialogueError('case_mismatch')
    if payload.expected_field_revision!=data['field_versions'].get(payload.field,0):
        raise DialogueError('field_revision_conflict')
    collection='records' if payload.field in RECORD_FIELDS else 'ratings'
    if payload.field not in data[collection]:raise DialogueError('record_missing')
    # Removal expresses a correction/withdrawal, not a new event fact. Quoted
    # material and negation in the withdrawal must not prevent clearing bad data.
    for source in sources:
        message=messages.get(source['source_message_id'])
        if message is None or message.role!='learner' or message.material_id is not None or source['quote'] not in message.text:
            raise DialogueError('source_role_or_missing')
    removed={payload.field}
    del data[collection][payload.field]
    for rating,subject in SUBJECTS.items():
        if subject==payload.field:
            data['ratings'].pop(rating,None);removed.add(rating)
    for field in removed:
        data['field_versions'][field]=data['field_versions'].get(field,0)+1
    for pending in data['pending_evidence']:
        if pending['status']=='pending' and pending['content']['target_case_id']==data['active_case_id'] and pending['content']['field'] in removed:
            pending['status']='invalidated'
    data['course']['confirmation']=None
    data['adoption_receipts'].append({'id':_id('remove-receipt',request_id,action.id),
        'action_id':action.id,'field':payload.field,'revision':data['field_versions'][payload.field],
        'sources':sources,'pending_id':None})


def apply_turn(state: State | dict, message: Message | dict, raw: Output | dict | str,
               request_id: str, *, model_calls: int = 1) -> TurnResult:
    cached = replay(state, message, request_id)
    if cached is not None:
        return cached
    contract = DialogueContract(state, message)
    before, message = contract.state, contract.message
    if before.session_status != "active":
        raise DialogueError("session_closed")
    output = contract.parse(raw)
    from .presentation import check_public_reply, weekly_support_reply
    output=output.model_copy(update={'reply':weekly_support_reply(before,output)})
    check_public_reply(output.reply)
    actions = _ordered(output.actions)
    data = before.model_dump()
    messages = {m.message_id: m for m in [*before.conversation_history, message]}
    from .context import remember_incoming, apply_case_change, planned_case_id
    course_case_id=before.active_case_id
    for a in actions:
        if a.type=='case_change' and a.payload.operation=='select':course_case_id=a.payload.new_case_id
        elif a.type=='case_change' and a.payload.operation=='adopt':
            choice=next((p for p in before.case_choices if p.id==a.payload.pending_id),None)
            if choice:course_case_id=choice.case_id
    remember_incoming(data,before,message,output.context_tags,course_case_id)
    signal_sources = _sources(output, output.signal_ref_ids)
    rules, completed, writes = [], {}, set()
    has_pause = output.signal in {"pause_request", "close_request"} or any(
        a.type == "set_boundary" and a.payload.kind == "pause_lesson" for a in actions)
    has_formal = any(a.type in {"record_update", "score_update", "adopt_pending", "teaching_step"} or
                    (a.type=="course_action" and a.payload.operation not in {"stage_check_answer","stage_goal"}) or
                    (a.type=='case_change' and a.payload.operation!='stage')
                     for a in actions)
    if has_formal and (has_pause or output.signal == "needs_switch"):
        raise DialogueError("transition_with_teaching")
    if has_pause and (output.signal == "resume_request" or any(a.type == "invite_return" for a in actions)):
        raise DialogueError("conflicting_flow_intents")
    if (any(a.type == "set_boundary" and a.payload.kind == "return_not_now" for a in actions)
            and (output.signal == "resume_request" or any(a.type == "invite_return" for a in actions))):
        raise DialogueError("conflicting_return_intents")
    if before.flow_mode == "paused" and output.signal in {"needs_switch", "conversation_closed"}:
        raise DialogueError("paused_signal")
    course_actions = [a for a in actions if a.type == "course_action"]
    case_changes=[a for a in actions if a.type=='case_change']
    cancellations=[a for a in actions if a.type=='cancel_case_choice']
    if case_changes and any(a.type in {'cancel_case_choice','record_remove'} for a in actions):
        raise DialogueError('competing_case_controls')
    if len({a.payload.pending_id for a in cancellations})!=len(cancellations):
        raise DialogueError('competing_case_controls')
    if len(case_changes)>1 or (case_changes and course_actions):raise DialogueError('competing_case_controls')
    if case_changes and case_changes[0].payload.operation!='stage' and any(
            a.type in {'record_update','score_update'} and case_changes[0].id not in a.depends_on for a in actions):
        raise DialogueError('case_change_dependency_required')
    if len(course_actions)>1:
        raise DialogueError("multiple_course_actions")
    if course_actions and course_actions[0].payload.operation in {"confirm_record","choose_personal","choose_fictional"} and any(
            a.type in {"record_update","score_update","adopt_pending","record_remove"} for a in actions):
        raise DialogueError("course_control_with_edit")
    for action in actions:
        sources = _sources(output, action.source_ref_ids)
        if action.type in {"record_update", "score_update", "stage_evidence", "record_remove"}:
            field = action.payload.field
        elif action.type == "adopt_pending":
            pending = next((p for p in data["pending_evidence"] if p["id"] == action.payload.pending_id), None)
            if pending is None or pending["status"] != "pending":
                raise DialogueError("pending_unavailable")
            field = pending["content"]["field"]
        else:
            field = None
        if field is not None:
            if field in writes:
                raise DialogueError("competing_writes")
            writes.add(field)
            if action.type!='record_remove' and any(a.type == "set_boundary" and a.payload.kind == "defer_field"
                   and a.payload.target_ref == field for a in actions):
                raise DialogueError("write_and_defer_conflict")
        if action.type in {"record_update", "score_update"}:
            _write(data, action.payload, sources, messages, completed, request_id, action,
                   expected_versions=before.field_versions if data['active_case_id']==before.active_case_id else {})
        elif action.type=='record_remove':
            _remove_record(data,action.payload,sources,messages,request_id,action)
        elif action.type=='cancel_case_choice':
            choice=next((p for p in data['case_choices'] if p['id']==action.payload.pending_id),None)
            if choice is None or choice['status']!='pending' or choice['origin_case_id']!=before.active_case_id:
                raise DialogueError('case_choice_stale')
            choice.update(status='cancelled',cancellation_sources=sources)
        elif action.type == "stage_evidence":
            _check_target(data, action.payload, sources, messages)
            if before.flow_mode == "teaching" and output.signal != "needs_switch":
                raise DialogueError("teaching_pending_requires_detour")
            if field in SUBJECTS:
                _subject(data, action.payload, {}, None)
            for older in data["pending_evidence"]:
                if (older["status"] == "pending" and older["content"]["target_case_id"] == action.payload.target_case_id
                        and older["content"]["field"] == field):
                    older["status"] = "superseded"
            data["pending_evidence"].append({"id": _id("pending", request_id, action.id),
                "content": action.payload.model_dump(), "sources": sources,
                "origin_revision": before.revision,
                "boundary_fingerprint": _boundary_fingerprint(data, field), "status": "pending",
                "receipt_id": None})
            from .context import remember_course_use
            remember_course_use(data,sources,data['active_case_id'])
        elif action.type == "adopt_pending":
            from .models import RecordPayload, ScorePayload
            payload = (RecordPayload if field in RECORD_FIELDS else ScorePayload).model_validate(pending["content"])
            if sources != pending["sources"]:
                raise DialogueError("pending_source_mismatch")
            if pending["boundary_fingerprint"] != _boundary_fingerprint(data, field):
                raise DialogueError("pending_boundary_changed")
            receipt_id = _write(data, payload, sources, messages, completed, request_id,
                                action, pending["id"], expected_versions=before.field_versions)
            pending.update(status="adopted", receipt_id=receipt_id)
        elif action.type == "set_boundary":
            if (action.payload.kind == "stop_case_questions"
                    and (action.payload.target_ref != course_case_id
                         or action.payload.scope != "current_case")):
                raise DialogueError("boundary_target_mismatch")
            content = action.payload.model_dump()
            if not any(b["content"] == content for b in _active(data)):
                data["boundaries"].append({"id": _id("boundary", request_id, action.id),
                    "content": content, "case_id": course_case_id,
                    "task_revision": before.lesson_progress.task_revision+int(course_case_id!=before.active_case_id),
                    "sources": sources, "active": True, "release_sources": []})
            if action.payload.kind == "return_not_now" and data["return_invitation"] is not None:
                data["return_invitation"].update(status="declined", answer_sources=sources)
        elif action.type == "release_boundary":
            boundary = next((b for b in _active(data) if b["id"] == action.payload.boundary_id), None)
            if boundary is None:
                raise DialogueError("boundary_unavailable")
            if boundary["content"]["kind"] == "pause_lesson":
                raise DialogueError("pause_requires_resume_signal")
            if action.payload.basis == "provided_score":
                # A supplied score clears defer only when _write actually adopts it.
                raise DialogueError("score_release_requires_adoption")
            boundary.update(active=False, release_sources=sources)
        elif action.type == "invite_return":
            invitation = data["return_invitation"]
            if (any(_active(data, "return_not_now")) or (invitation is not None
                    and invitation["status"] == "pending")):
                raise DialogueError("invitation_blocked")
            if not (output.bridge_ready or output.signal == "conversation_closed"):
                raise DialogueError("bridge_basis_missing")
            if action.payload.expected_task_revision != before.lesson_progress.task_revision:
                raise DialogueError("task_revision_conflict")
            if output.reply.count("？") + output.reply.count("?") != 1:
                raise DialogueError("invitation_requires_one_question")
            data["return_invitation"] = {"id": _id("invitation", request_id, action.id),
                "assistant_message_id": _id("assistant", request_id),
                "task_revision": before.lesson_progress.task_revision, "case_id": before.active_case_id,
                "sources": sources, "status": "pending", "answer_sources": []}
        elif action.type == "teaching_step":
            if action.payload.expected_task_revision != before.lesson_progress.task_revision:
                raise DialogueError("task_revision_conflict")
            if action.payload.operation == "select_field":
                field = action.payload.next_field
                if (any(_active(data, "stop_case_questions")) or any(_active(data, "defer_field", field))
                        or (data["case_kind"] == "personal" and any(_active(data, "no_personal_case")))):
                    raise DialogueError("question_blocked")
                if field in data["records"] or field in data["ratings"]:
                    raise DialogueError("field_already_obtained")
                data["lesson_progress"].update(field=field,
                    task_revision=before.lesson_progress.task_revision + 1)
        elif action.type == "course_action":
            from .course import apply_course_action
            staging=action.payload.operation in {"stage_check_answer","stage_goal"}
            if staging and not (before.flow_mode == "communicating" or
                    (before.flow_mode == "teaching" and output.signal == "needs_switch")):
                raise DialogueError("response_staging_mode")
            rules.append(apply_course_action(data, action, sources, request_id))
        elif action.type=='case_change':
            staging=action.payload.operation=='stage'
            if staging and not (before.flow_mode=='communicating' or output.signal=='needs_switch'):
                raise DialogueError('case_staging_mode')
            if not staging and (before.flow_mode!='teaching' or output.signal not in {'none','resume_request'}):
                raise DialogueError('case_adoption_mode')
            if action.payload.operation in {'stage','select'} and action.payload.new_case_id!=planned_case_id(before,message):
                raise DialogueError('case_id_not_program_bound')
            apply_case_change(data,before,action,sources,messages,request_id)
            rules.append('case:'+action.payload.operation)
    _apply_mode(data, before, output, signal_sources, message, rules)
    if before.flow_mode=='teaching' and output.signal=='none' and data['flow_mode']=='teaching' and data['session_status']=='active':
        from .course import sync_practice_progress
        sync_practice_progress(data)
    reflection_sources = []
    if output.reflection_request is not None:
        reflection_sources = _sources(output, output.reflection_request.source_ref_ids)
    elif model_calls and any(a.type == 'set_boundary' for a in actions):
        reflection_sources = [s for a in actions if a.type == 'set_boundary'
                              for s in _sources(output, a.source_ref_ids)]
    if reflection_sources:
        data["reflection_jobs"].append({"id": _id("reflection", request_id),
            "question": output.reflection_request.question if output.reflection_request else
                '核对本轮用户要求与已保存边界是否完整，回复承诺与实际记录是否一致；提出下一轮的局部改进。',
            "scope": output.reflection_request.scope if output.reflection_request else 'current_lesson',
            "case_id": data['active_case_id'], "task_revision": data['lesson_progress']['task_revision'],
            "origin_revision": before.revision + 1, "sources": reflection_sources})
    assistant=Message(
        message_id=_id("assistant", request_id), conversation_id=before.conversation_id,
        sequence=message.sequence + 1, role="agent", text=output.reply,origin_mode=before.flow_mode)
    from .context import remember_outgoing
    refocused=any((a.type=='teaching_step' and a.payload.operation=='select_field') or
                  (a.type=='course_action' and a.payload.operation in {'start_practice','show_review','choose_personal','choose_fictional'}) or
                  (a.type=='case_change' and a.payload.operation!='stage') for a in actions)
    assistant=remember_outgoing(data,before,assistant,refocused=refocused or output.signal=='resume_request')
    entry=data['message_context'][message.message_id]
    incoming=message.model_copy(update={k:entry[k] for k in ('origin_mode','case_id','material_id')})
    data["conversation_history"].extend([incoming.model_dump(),assistant.model_dump()])
    data["revision"] += 1
    receipt_ids = [r["id"] for r in data["adoption_receipts"][len(before.adoption_receipts):]]
    data["turn_events"].append({"request_id": request_id, "input_fingerprint": fingerprint(message),
        "reply": output.reply, "mode_from": before.flow_mode, "mode_to": data["flow_mode"],
        "rules": rules, "receipt_ids": receipt_ids, "model_calls": model_calls})
    return TurnResult(state=checked_state(data), reply=output.reply, model_calls=model_calls)


def context_facts(state: State | dict) -> dict:
    """Derived views; no second writable deferred list or stale candidate authority."""
    before = checked_state(state)
    data = before.model_dump(mode="json")
    fields = {}
    for field in (*RECORD_FIELDS, *SUBJECTS):
        obtained = field in data["records"] or field in data["ratings"]
        deferred = bool(list(_active(data, "defer_field", field)))
        not_applicable = data["case_kind"] == "fictional" and field in SUBJECTS and not obtained
        blocked = deferred or any(_active(data, "stop_case_questions")) or (
            data["case_kind"] == "personal" and any(_active(data, "no_personal_case")))
        fields[field] = {"status": "obtained" if obtained else "not_applicable" if not_applicable else "deferred" if deferred else "missing",
                         "deferred": deferred, "ask_allowed": not obtained and not blocked and not not_applicable}
    pending = []
    messages = {m.message_id: m for m in before.conversation_history}
    for item in before.pending_evidence:
        current = item.status == "pending"
        try:
            _check_target(data, item.content, [s.model_dump() for s in item.sources], messages)
            if item.content.field in SUBJECTS:
                _subject(data, item.content, {}, None)
            current &= item.boundary_fingerprint == _boundary_fingerprint(data, item.content.field)
        except DialogueError:
            current = False
        pending.append({**item.model_dump(mode="json"), "is_current": current})
    return {"fields": fields, "boundaries": list(_active(data)), "pending_evidence": pending}


def safety_pause(state, message, request_id):
    """Trusted guard event; no inferred or user-supplied safety-release action."""
    cached = replay(state, message, request_id)
    if cached is not None:
        return cached
    before = checked_state(state)
    msg = checked_message(before, message)
    if before.session_status != "active":
        raise DialogueError("session_closed")
    data = before.model_dump()
    data.update(flow_mode="paused", paused_reason="safety",
                suspended_mode=before.suspended_mode or before.flow_mode)
    paused = checked_state(data)
    # A guard event is not a learner resume and has no formal actions.
    result = apply_turn(paused, msg, {"based_on_revision": before.revision,
        "reply": "课程已安全暂停，已有学习记录保留。"}, request_id, model_calls=0)
    updated = result.state.model_dump()
    updated["turn_events"][-1].update(mode_from=before.flow_mode, rules=["G1"])
    for item in updated['conversation_history'][-2:]:
        item['origin_mode']=before.flow_mode
        updated['message_context'][item['message_id']]['origin_mode']=before.flow_mode
    return result.model_copy(update={"state": checked_state(updated)})
