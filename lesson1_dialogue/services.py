"""Version-isolated encrypted service using the application's existing tables."""
import hashlib
import json
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError

from webapp.models import Conversation, Message as StoredMessage, TurnEvent, utcnow
from webapp.security import decrypt_json, decrypt_text, encrypt_json, encrypt_text
from webapp.services import has_current_consent
from .contracts import DialogueError
from .controls import LABELS, apply_control, available_controls
from .course import LABELS as PHASE_LABELS, context as course_context
from .engine import context_facts
from .models import Message, State, new_course_state
from .prompts import system_prompt
from .provider import runtime_factory as default_runtime_factory
from .public_errors import SavedTurnUnavailable

AGENT_VERSION="course-single-dialogue-v1"
LESSON_VERSION="9.16-supportive-dialogue"
INITIAL="欢迎来到第一课。我们会学习区分事情、想法、情绪和行为，再用一个例子练习。先说说上周整体状态：1分最不好，10分最好；也可以先跳过。"


def prompt_hash():
    from . import stage_cards
    from .examples import EXAMPLES, RUBRIC
    from .reflection import REFLECTION_PROMPT, REFLECTION_VERSION
    from .wire import WIRE_VERSION
    content = {'wire': WIRE_VERSION, 'prompts': [system_prompt(m) for m in ('teaching','communicating','paused')],
               'goals': stage_cards.GOALS, 'do_not': stage_cards.DO_NOT, 'targets': stage_cards.TARGETS,
               'preconditions': stage_cards.PRECONDITIONS, 'effect_flags': stage_cards.EFFECT_FLAGS,
               'library_story': stage_cards.LIBRARY_STORY, 'examples':EXAMPLES, 'rubric':RUBRIC,
               'reflection_version':REFLECTION_VERSION, 'reflection_prompt':REFLECTION_PROMPT,
               'context_metadata':'case-context/2-task-material-scope'}
    return hashlib.sha256(json.dumps(content,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def is_dialogue(conversation):
    return conversation.agent_version==AGENT_VERSION


def _key(participant_id):
    return f"{participant_id}:lesson-1:{LESSON_VERSION}"


def owned(db, conversation_id, participant_id):
    return db.scalar(select(Conversation).where(Conversation.id==conversation_id,
        Conversation.participant_id==participant_id,Conversation.agent_version==AGENT_VERSION,
        Conversation.lesson_id=="lesson-1"))


def _authorize(db, conversation_id, participant_id):
    conversation=owned(db,conversation_id,participant_id)
    if conversation is None:raise PermissionError("课程不存在或不属于本人。")
    if not has_current_consent(db,participant_id):raise PermissionError("请先确认数据记录告知。")
    if conversation.lesson_version!=LESSON_VERSION:raise DialogueError("historical_version_read_only")
    return conversation


def _history(db, conversation):
    omitted=set(db.scalars(select(TurnEvent.user_message_id).where(TurnEvent.conversation_id==conversation.id,
        TurnEvent.status.not_in(("success","safety")),TurnEvent.user_message_id.is_not(None))).all())
    rows=db.scalars(select(StoredMessage).where(StoredMessage.conversation_id==conversation.id)
                    .order_by(StoredMessage.sequence)).all()
    return [Message(message_id=m.id,conversation_id=conversation.id,sequence=m.sequence,
                    role=m.role,text=decrypt_text(m.content_encrypted)) for m in rows if m.id not in omitted]


def load_state(db, conversation):
    data=decrypt_json(conversation.agent_state_encrypted)
    from .context import restore_message_context
    history=restore_message_context(data,_history(db,conversation))
    data["conversation_history"]=[m.model_dump() for m in history]
    state=State.model_validate(data)
    if state.conversation_id!=conversation.id or state.participant_id!=conversation.participant_id:
        raise DialogueError("stored_owner_mismatch")
    return state


def create_or_resume(db,participant_id):
    if not has_current_consent(db,participant_id):raise PermissionError("请先确认数据记录告知。")
    existing=db.scalar(select(Conversation).where(Conversation.active_course_key==_key(participant_id)))
    if existing is not None:
        if not is_dialogue(existing) or existing.lesson_version!=LESSON_VERSION:
            raise DialogueError("active_version_conflict")
        return existing,True
    conversation=Conversation(participant_id=participant_id,mode="cbt",agent_version=AGENT_VERSION,
        agent_prompt_hash=prompt_hash(),lesson_id="lesson-1",lesson_version=LESSON_VERSION,
        active_course_key=_key(participant_id))
    try:
        db.add(conversation);db.flush()
        state=new_course_state(conversation.id,participant_id,str(uuid.uuid4()))
        conversation.agent_state_encrypted=encrypt_json(state.model_dump(exclude={"conversation_history"}))
        db.add(StoredMessage(conversation_id=conversation.id,sequence=1,role="agent",content_encrypted=encrypt_text(INITIAL)))
        db.commit()
    except IntegrityError:
        db.rollback()
        existing=db.scalar(select(Conversation).where(Conversation.active_course_key==_key(participant_id)))
        if existing is None:raise
        return existing,True
    db.refresh(conversation)
    return conversation,False


def payload(db,conversation,*,request_key=None):
    state=load_state(db,conversation)
    data=state.model_dump(mode="json")
    facts=context_facts(state)
    rows=db.scalars(select(StoredMessage).where(StoredMessage.conversation_id==conversation.id)
                   .order_by(StoredMessage.sequence)).all()
    messages=[{"id":m.id,"role":m.role,"sequence":m.sequence,"content":decrypt_text(m.content_encrypted)} for m in rows]
    read_only=conversation.lesson_version!=LESSON_VERSION or state.session_status=="completed"
    events=db.scalars(select(TurnEvent).where(TurnEvent.conversation_id==conversation.id)
                      .order_by(TurnEvent.created_at,TurnEvent.id)).all()
    def public_status(event):
        if event is None:return "missing"
        if event.status in {"success","safety"}:return "saved"
        if event.status=="pending":
            started=conversation.processing_started_at
            live=bool(conversation.active_request_id and started and
                started.replace(tzinfo=timezone.utc)>datetime.now(timezone.utc)-timedelta(minutes=2))
            return "pending" if live else "interrupted"
        return "failed"
    request_event=next((e for e in events if e.idempotency_key==request_key),None) if request_key else None
    request_status=public_status(request_event)
    later=bool(request_event and any(m.role=="learner" and m.sequence>
        next((u.sequence for u in rows if u.id==request_event.user_message_id),0) for m in rows))
    recovery={"turn_status":public_status(events[-1]) if events else "ready"}
    if request_key is not None:
        recovery.update(request_status=request_status,request_retryable=(not read_only and
            state.session_status=="active" and not later and request_status in {"failed","missing","interrupted"}))
    return {"id":conversation.id,"lesson_id":"lesson-1","lesson_version":conversation.lesson_version,
        "status":state.session_status,"revision":state.revision,
        **recovery,
        "read_only":read_only,
        "messages":messages,"course":{"phase":state.lesson_progress.phase,
          "phase_label":PHASE_LABELS[state.lesson_progress.phase],"phases":PHASE_LABELS,
          "phase_order":list(PHASE_LABELS),
          "flow_mode":state.flow_mode,"paused_reason":state.paused_reason,
          "case_kind":state.case_kind,"records":data["records"],"ratings":data["ratings"],
          "fields":facts["fields"],"details":course_context(data),
          "confirmation":data["course"]["confirmation"],
          "controls":[] if read_only else [{"id":c,"label":LABELS[c]} for c in available_controls(state)]}}


def _same_request(event,content,action,db):
    source=db.get(StoredMessage,event.user_message_id)
    trace=decrypt_json(event.trace_encrypted)
    if source is None or decrypt_text(source.content_encrypted)!=content or trace.get("request_action")!=action:
        raise DialogueError("idempotency_conflict")


def _replay(db,conversation,event):
    message=db.get(StoredMessage,event.assistant_message_id)
    if message is None:raise RuntimeError("saved_reply_missing")
    return {"reply":decrypt_text(message.content_encrypted),"deduplicated":True,
            "conversation":payload(db,conversation)}


def _audit_failure(db,event_id,lease,error,calls,elapsed,binding=None):
    """Append an attempt without overwriting a newer lease holder's successful event."""
    attempt_id=str(uuid.uuid4())
    for _ in range(3):
        persisted=db.scalar(select(TurnEvent).where(TurnEvent.id==event_id).execution_options(populate_existing=True))
        if persisted is None:return
        prior_trace,prior_status=persisted.trace_encrypted,persisted.status
        owner=db.scalar(select(Conversation.active_request_id).where(Conversation.id==persisted.conversation_id))
        trace=decrypt_json(prior_trace)
        trace.setdefault("attempts",[]).append({"attempt_id":attempt_id,"error_type":type(error).__name__,
            "error":str(error)[:1000],"model_calls":calls,"late":owner!=lease,"wire_binding":binding})
        values={"trace_encrypted":encrypt_json(trace)}
        statement=update(TurnEvent).where(TurnEvent.id==event_id,TurnEvent.trace_encrypted==prior_trace,
                                          TurnEvent.status==prior_status)
        if owner==lease and prior_status not in {"success","safety"}:
            statement=statement.where(select(Conversation.id).where(Conversation.id==persisted.conversation_id,
                                      Conversation.active_request_id==lease).exists())
            values.update(status="error",error_type=type(error).__name__,error_encrypted=encrypt_text(str(error)[:1000]),
                          completed_at=utcnow(),latency_ms=elapsed)
        saved=db.execute(statement.values(**values).execution_options(synchronize_session=False)).rowcount
        db.commit()
        if saved==1:return
    raise RuntimeError("failure_audit_conflict")


def _reflection_audit(db, event_id, audit, client):
    """Append to the committed turn without replacing its success/failure decision."""
    for _ in range(3):
        event=db.scalar(select(TurnEvent).where(TurnEvent.id==event_id).execution_options(populate_existing=True))
        if event is None:return
        previous=event.trace_encrypted;trace=decrypt_json(previous)
        trace['reflection']=audit
        calls=getattr(client,'model_calls',[])
        if calls:trace['model_calls']=calls
        values={'trace_encrypted':encrypt_json(trace)}
        for field in ('prompt_tokens','completion_tokens','total_tokens'):
            amounts=[c.get('usage',{}).get(field) for c in calls if c.get('usage')]
            if amounts and all(type(n) is int for n in amounts):values[field]=sum(amounts)
        saved=db.execute(update(TurnEvent).where(TurnEvent.id==event_id,TurnEvent.trace_encrypted==previous)
            .values(**values).execution_options(synchronize_session=False)).rowcount
        db.commit()
        if saved==1:return


def _post_commit_reflection(db, conversation, event_id, lease, state, runtime):
    """One eligible R after durable main success; lease/CAS protect newer state."""
    from .reflection import finish_reflection
    pending=[j for j in state.reflection_jobs if j.origin_revision==state.revision
             and j.status=='pending' and not j.attempted]
    if not pending:return
    job=pending[-1];started=time.perf_counter()
    audit={'job_id':job.id,'status':'claiming','model_calls':0}
    client=runtime.client
    try:
        db.refresh(conversation);prior=conversation.agent_state_encrypted
        data=state.model_dump(mode='json')
        stored=next(j for j in data['reflection_jobs'] if j['id']==job.id)
        stored.update(status='running',attempted=True)
        running=State.model_validate(data)
        claimed=encrypt_json(running.model_dump(exclude={'conversation_history'}))
        saved=db.execute(update(Conversation).where(Conversation.id==conversation.id,
            Conversation.active_request_id==lease,Conversation.agent_state_encrypted==prior)
            .values(agent_state_encrypted=claimed).execution_options(synchronize_session=False)).rowcount
        db.commit()  # Claim is durable before the additional external request.
        if saved!=1:
            audit.update(status='skipped_stale');return
        reflected,audit=finish_reflection(running,job.id,client)
        saved=db.execute(update(Conversation).where(Conversation.id==conversation.id,
            Conversation.active_request_id==lease,Conversation.agent_state_encrypted==claimed)
            .values(agent_state_encrypted=encrypt_json(reflected.model_dump(exclude={'conversation_history'})))
            .execution_options(synchronize_session=False)).rowcount
        db.commit()
        if saved!=1:audit.update(status='discarded_stale')
    except Exception as error:
        db.rollback()
        audit.update(status='storage_error',error_code=type(error).__name__)
    finally:
        audit['latency_ms']=int((time.perf_counter()-started)*1000)
        try:_reflection_audit(db,event_id,audit,client)
        except Exception:db.rollback()  # The already committed main turn remains valid.


def process(db,*,participant_id,conversation_id,content,idempotency_key,expected_revision,
            action="chat",runtime_factory=None,on_reply_delta=None):
    conversation=_authorize(db,conversation_id,participant_id)
    if action!="chat" and content.strip():raise DialogueError("control_content_must_be_empty")
    content=content.strip() if action=="chat" else LABELS.get(action,"")
    if not content or len(content)>2000:raise DialogueError("invalid_input")
    existing=db.scalar(select(TurnEvent).where(TurnEvent.conversation_id==conversation_id,
                                              TurnEvent.idempotency_key==idempotency_key))
    if existing:
        _same_request(existing,content,action,db)
        if existing.status in {"success","safety"}:return _replay(db,conversation,existing)
    lease=str(uuid.uuid4())
    cutoff=datetime.now(timezone.utc)-timedelta(minutes=2)
    acquired=db.execute(update(Conversation).where(Conversation.id==conversation_id,
        or_(Conversation.active_request_id.is_(None),Conversation.processing_started_at<cutoff))
        .values(active_request_id=lease,processing_started_at=utcnow()).execution_options(synchronize_session=False)).rowcount
    db.commit()
    if acquired!=1:raise DialogueError("conversation_busy")
    event=None;runtime=None;main_committed=False;started=time.perf_counter()
    try:
        db.refresh(conversation)
        existing=db.scalar(select(TurnEvent).where(TurnEvent.conversation_id==conversation_id,
            TurnEvent.idempotency_key==idempotency_key).execution_options(populate_existing=True))
        if existing:
            _same_request(existing,content,action,db)
            if existing.status in {"success","safety"}:return _replay(db,conversation,existing)
        before=load_state(db,conversation)
        if before.revision!=expected_revision:raise DialogueError("revision_conflict")
        if before.session_status!="active" and action!="resume_session":raise DialogueError("session_closed")
        if action=="resume_session":
            other=db.scalar(select(Conversation.id).where(Conversation.active_course_key==_key(participant_id),
                                                         Conversation.id!=conversation_id))
            if other is not None:raise DialogueError("another_session_active")
        sequence=int(db.scalar(select(func.max(StoredMessage.sequence)).where(
            StoredMessage.conversation_id==conversation_id)) or 0)+1
        if existing:
            user=db.get(StoredMessage,existing.user_message_id)
            later=db.scalar(select(StoredMessage.id).where(StoredMessage.conversation_id==conversation_id,
                        StoredMessage.role=="learner",StoredMessage.sequence>user.sequence).limit(1))
            if later is not None:raise DialogueError("old_failed_turn")
            event=existing
            event.status="pending";event.completed_at=None
        else:
            user=StoredMessage(conversation_id=conversation_id,sequence=sequence,role="learner",
                               content_encrypted=encrypt_text(content))
            db.add(user);db.flush()
            event=TurnEvent(conversation_id=conversation_id,user_message_id=user.id,
                idempotency_key=idempotency_key,status="pending",agent_version=AGENT_VERSION,
                agent_prompt_hash=prompt_hash(),trace_encrypted=encrypt_json({"request_action":action,"attempts":[]}))
            db.add(event)
        db.commit()  # User input and pending audit exist before any model/provider call.
        incoming=Message(message_id=user.id,conversation_id=conversation_id,sequence=user.sequence,role="learner",text=content)
        if action=="chat":
            runtime=(runtime_factory or default_runtime_factory)()
            result=(runtime.turn(before,incoming,event.id) if on_reply_delta is None else
                    runtime.turn(before,incoming,event.id,on_reply_delta=on_reply_delta))
        else:result=apply_control(before,incoming,action,event.id)
        assistant=result.state.conversation_history[-1]
        db.add(StoredMessage(id=assistant.message_id,conversation_id=conversation_id,sequence=assistant.sequence,
                             role="agent",content_encrypted=encrypt_text(result.reply)))
        values={"agent_state_encrypted":encrypt_json(result.state.model_dump(exclude={"conversation_history"})),
                "status":result.state.session_status,
                "active_course_key":_key(participant_id) if result.state.session_status=="active" else None,
                "ended_at":None if result.state.session_status=="active" else utcnow()}
        saved=db.execute(update(Conversation).where(Conversation.id==conversation_id,Conversation.active_request_id==lease)
                          .values(**values).execution_options(synchronize_session=False)).rowcount
        if saved!=1:raise DialogueError("lease_expired")
        event=db.scalar(select(TurnEvent).where(TurnEvent.id==event.id).with_for_update()
                        .execution_options(populate_existing=True))
        trace=decrypt_json(event.trace_encrypted)
        client=getattr(runtime,"client",None)
        trace.update(turn=result.state.turn_events[-1].model_dump(),
                     model_calls=getattr(client,"model_calls",[]),
                     wire_binding=getattr(runtime,"binding_audit",None),
                     execution_kind=getattr(client,"execution_kind","provider" if client else "control"))
        event.status="safety" if result.state.paused_reason=="safety" else "success"
        event.safety_event="local_self_harm" if result.state.paused_reason=="safety" else None
        event.assistant_message_id=assistant.message_id
        event.trace_encrypted=encrypt_json(trace);event.error_type=None;event.error_encrypted=None
        event.latency_ms=int((time.perf_counter()-started)*1000);event.completed_at=utcnow()
        completion=getattr(client,"completion",None)
        if completion is not None:
            event.model=completion.model;event.provider_request_id=completion.request_id
            event.finish_reason=completion.finish_reason
            usage=completion.usage or {}
            for field in ("prompt_tokens","completion_tokens","total_tokens"):
                setattr(event,field,usage.get(field))
        db.commit()  # Main reply/state are durable before any conditional R call.
        main_committed=True
        if action=='chat' and runtime is not None and result.model_calls:
            _post_commit_reflection(db,conversation,event.id,lease,result.state,runtime)
        db.refresh(conversation)
        return {"reply":result.reply,"deduplicated":False,"conversation":payload(db,conversation)}
    except Exception as exc:
        db.rollback()
        if event is not None:
            try:
                _audit_failure(db,event.id,lease,exc,getattr(getattr(runtime,"client",None),"model_calls",[]),
                               int((time.perf_counter()-started)*1000),getattr(runtime,"binding_audit",None))
            except Exception:
                db.rollback()
                logging.getLogger(__name__).warning("dialogue_audit_unavailable conversation_id=%s",conversation_id)
        if main_committed:raise SavedTurnUnavailable() from exc
        raise
    finally:
        try:
            db.execute(update(Conversation).where(Conversation.id==conversation_id,Conversation.active_request_id==lease)
                       .values(active_request_id=None,processing_started_at=None).execution_options(synchronize_session=False))
            db.commit()
        except Exception:
            db.rollback()
            logging.getLogger(__name__).warning("dialogue_lease_release_unavailable conversation_id=%s",conversation_id)
