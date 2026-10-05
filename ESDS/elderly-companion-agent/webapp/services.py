from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterator, List, Optional

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from daily_agent import DailyChatAgent
from daily_agent.agent_runtime import AgentTurnResult
from daily_agent.emotion_context import VoiceEmotionContext
from webapp.agent_versions import agent_version_for_mode
from webapp.config import settings
from webapp.models import AdminAuditLog, Consent, Conversation, Message, Participant, TurnEvent, utcnow
from webapp.security import decrypt_json, decrypt_text, encrypt_json, encrypt_text, hash_secret, verify_secret


def bootstrap_invites(db: Session) -> None:
    for item in settings.invite_codes.split(","):
        if ":" not in item:
            continue
        label, code = (part.strip() for part in item.split(":", 1))
        if not label or not code:
            continue
        participant = db.scalar(select(Participant).where(Participant.label == label))
        if participant is None:
            db.add(Participant(label=label, invite_hash=hash_secret(code)))
        elif not verify_secret(participant.invite_hash, code):
            participant.invite_hash = hash_secret(code)
            participant.is_active = True
    db.commit()


def authenticate_invite(db: Session, code: str) -> Optional[Participant]:
    participants = db.scalars(select(Participant).where(Participant.is_active.is_(True))).all()
    for participant in participants:
        if verify_secret(participant.invite_hash, code):
            return participant
    return None


def has_current_consent(db: Session, participant_id: str) -> bool:
    return db.scalar(
        select(Consent.id).where(
            Consent.participant_id == participant_id,
            Consent.version == settings.consent_version,
        )
    ) is not None


def record_consent(db: Session, participant_id: str) -> Consent:
    existing = db.scalar(
        select(Consent).where(
            Consent.participant_id == participant_id,
            Consent.version == settings.consent_version,
        )
    )
    if existing:
        return existing
    consent = Consent(participant_id=participant_id, version=settings.consent_version)
    db.add(consent)
    db.commit()
    db.refresh(consent)
    return consent


def create_conversation(db: Session, participant_id: str, mode: str) -> Conversation:
    if mode != "daily_chat":
        raise ValueError(f"Unsupported conversation mode: {mode}")
    agent_version = agent_version_for_mode(mode)
    conversation = Conversation(
        participant_id=participant_id,
        mode=mode,
        agent_version=agent_version.label,
        agent_prompt_hash=agent_version.prompt_sha256,
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def get_owned_conversation(db: Session, conversation_id: str, participant_id: str) -> Optional[Conversation]:
    return db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.participant_id == participant_id,
        )
    )


def conversation_payload(conversation: Conversation, *, include_scenario: bool = True) -> Dict[str, Any]:
    messages = [
        {
            "id": message.id,
            "sequence": message.sequence,
            "role": message.role,
            "content": decrypt_text(message.content_encrypted),
            "attachment": decrypt_json(message.attachment_encrypted),
            "created_at": message.created_at.isoformat(),
        }
        for message in conversation.messages
    ]
    payload: Dict[str, Any] = {
        "id": conversation.id,
        "participant_id": conversation.participant_id,
        "participant_label": conversation.participant.label if conversation.participant else "",
        "mode": conversation.mode,
        "agent_version": conversation.agent_version,
        "agent_prompt_hash": conversation.agent_prompt_hash,
        "status": conversation.status,
        "lesson_id": conversation.lesson_id,
        "lesson_version": conversation.lesson_version,
        "scenario_id": conversation.scenario_id,
        "scenario_version": conversation.scenario_version,
        "scenario_confirmed": conversation.scenario_confirmed_at is not None,
        "started_at": conversation.started_at.isoformat(),
        "ended_at": conversation.ended_at.isoformat() if conversation.ended_at else None,
        "messages": messages,
    }
    if include_scenario:
        payload["scenario"] = decrypt_json(conversation.scenario_snapshot_encrypted)
    return payload


def _completion_payload(result: AgentTurnResult) -> Dict[str, Any]:
    completion = result.completion
    if not completion:
        return {}
    return {
        "model": completion.model,
        "deployment": completion.deployment,
        "api_version": completion.api_version,
        "provider_request_id": completion.request_id,
        "finish_reason": completion.finish_reason,
        "prompt_tokens": completion.usage.get("prompt_tokens"),
        "completion_tokens": completion.usage.get("completion_tokens"),
        "total_tokens": completion.usage.get("total_tokens"),
    }


def _event_response(db: Session, event: TurnEvent) -> Dict[str, Any]:
    if event.status in {"success", "safety"} and event.assistant_message_id:
        message = db.get(Message, event.assistant_message_id)
        return {
            "reply": decrypt_text(message.content_encrypted) if message else "",
            "status": event.status,
            "trace": decrypt_json(event.trace_encrypted),
            "safety_event": event.safety_event,
            "deduplicated": True,
        }
    raise RuntimeError("该请求已经处理失败，请修改内容后重试。")


def _recent_chat_history(db: Session, conversation_id: str) -> List[Dict[str, str]]:
    recent = db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.sequence.desc())
        .limit(12)
    ).all()
    return [
        {"role": message.role, "content": decrypt_text(message.content_encrypted)}
        for message in reversed(recent)
    ]


def process_turn(
    db: Session,
    conversation: Conversation,
    *,
    content: str,
    idempotency_key: str,
    daily_factory=DailyChatAgent,
    voice_emotion: Optional[VoiceEmotionContext] = None,
) -> Dict[str, Any]:
    if conversation.mode != "daily_chat":
        raise ValueError("旧 CBT 角色会话已归档，只能查看或导出。")
    existing = db.scalar(
        select(TurnEvent).where(
            TurnEvent.conversation_id == conversation.id,
            TurnEvent.idempotency_key == idempotency_key,
        )
    )
    if existing:
        return _event_response(db, existing)

    if conversation.status != "active":
        raise ValueError("会话已经结束。")
    request_token = str(uuid.uuid4())
    stale_before = datetime.now(timezone.utc) - timedelta(minutes=2)
    acquired = db.execute(
        update(Conversation)
        .where(
            Conversation.id == conversation.id,
            or_(
                Conversation.active_request_id.is_(None),
                Conversation.processing_started_at < stale_before,
            ),
        )
        .values(active_request_id=request_token, processing_started_at=utcnow())
        .execution_options(synchronize_session=False)
    ).rowcount
    db.commit()
    if acquired != 1:
        raise RuntimeError("上一条消息仍在处理中，请稍后再试。")

    event: Optional[TurnEvent] = None
    start = time.perf_counter()
    try:
        next_sequence = int(
            db.scalar(select(func.max(Message.sequence)).where(Message.conversation_id == conversation.id)) or 0
        ) + 1
        user_message = Message(
            conversation_id=conversation.id,
            sequence=next_sequence,
            role="elderly",
            content_encrypted=encrypt_text(content),
        )
        db.add(user_message)
        db.flush()
        runtime_agent_version = agent_version_for_mode(conversation.mode)
        event = TurnEvent(
            conversation_id=conversation.id,
            user_message_id=user_message.id,
            idempotency_key=idempotency_key,
            status="pending",
            agent_version=runtime_agent_version.label,
            agent_prompt_hash=runtime_agent_version.prompt_sha256,
            trace_encrypted=encrypt_json({"voice_emotion": voice_emotion.to_dict()}) if voice_emotion is not None else None,
        )
        db.add(event)
        db.commit()

        conversation = db.get(Conversation, conversation.id)
        history = _recent_chat_history(db, conversation.id)

        agent = daily_factory()
        if voice_emotion is None:
            result = agent.reply_turn(history)
        else:
            result = agent.reply_turn(history, voice_emotion=voice_emotion)
            result.trace = {**result.trace, "voice_emotion": voice_emotion.to_dict()}

        assistant_message = Message(
            conversation_id=conversation.id,
            sequence=next_sequence + 1,
            role="agent",
            content_encrypted=encrypt_text(result.reply),
        )
        db.add(assistant_message)
        db.flush()
        metadata = _completion_payload(result)
        event.assistant_message_id = assistant_message.id
        event.status = "safety" if result.safety_event else "success"
        event.trace_encrypted = encrypt_json(result.trace) if result.trace else None
        event.safety_event = result.safety_event
        event.latency_ms = int((time.perf_counter() - start) * 1000)
        event.completed_at = utcnow()
        for key, value in metadata.items():
            setattr(event, key, value)
        db.commit()
        return {
            "reply": result.reply,
            "status": event.status,
            "trace": result.trace,
            "safety_event": result.safety_event,
            "deduplicated": False,
        }
    except Exception as exc:
        db.rollback()
        if event and event.id:
            persisted = db.get(TurnEvent, event.id)
            if persisted:
                persisted.status = "error"
                persisted.error_type = type(exc).__name__
                persisted.error_encrypted = encrypt_text(str(exc)[:1000])
                persisted.latency_ms = int((time.perf_counter() - start) * 1000)
                persisted.completed_at = utcnow()
                db.commit()
        raise
    finally:
        db.execute(
            update(Conversation)
            .where(Conversation.id == conversation.id, Conversation.active_request_id == request_token)
            .values(active_request_id=None, processing_started_at=None)
        )
        db.commit()


def stream_process_turn(
    db: Session,
    conversation: Conversation,
    *,
    content: str,
    idempotency_key: str,
    daily_factory=DailyChatAgent,
    voice_emotion: Optional[VoiceEmotionContext] = None,
) -> Iterator[Dict[str, Any]]:
    """Stream reply deltas while retaining the normal turn persistence rules."""

    if conversation.mode != "daily_chat":
        yield {"type": "error", "detail": "This voice session is unavailable."}
        return
    existing = db.scalar(
        select(TurnEvent).where(
            TurnEvent.conversation_id == conversation.id,
            TurnEvent.idempotency_key == idempotency_key,
        )
    )
    if existing:
        try:
            cached = _event_response(db, existing)
        except RuntimeError:
            yield {"type": "error", "detail": "This reply could not be resumed."}
            return
        if cached["reply"]:
            yield {"type": "delta", "text": cached["reply"]}
        yield {"type": "done", "status": cached["status"], "deduplicated": True}
        return
    if conversation.status != "active":
        yield {"type": "error", "detail": "This conversation has ended."}
        return

    request_token = str(uuid.uuid4())
    acquired = db.execute(
        update(Conversation)
        .where(
            Conversation.id == conversation.id,
            or_(
                Conversation.active_request_id.is_(None),
                Conversation.processing_started_at
                < datetime.now(timezone.utc) - timedelta(minutes=2),
            ),
        )
        .values(active_request_id=request_token, processing_started_at=utcnow())
        .execution_options(synchronize_session=False)
    ).rowcount == 1
    db.commit()
    if not acquired:
        yield {"type": "error", "detail": "The previous message is still processing."}
        return

    event: Optional[TurnEvent] = None
    started = time.perf_counter()
    try:
        next_sequence = int(
            db.scalar(
                select(func.max(Message.sequence)).where(
                    Message.conversation_id == conversation.id
                )
            )
            or 0
        ) + 1
        user_message = Message(
            conversation_id=conversation.id,
            sequence=next_sequence,
            role="elderly",
            content_encrypted=encrypt_text(content),
        )
        db.add(user_message)
        db.flush()
        runtime_agent_version = agent_version_for_mode(conversation.mode)
        event = TurnEvent(
            conversation_id=conversation.id,
            user_message_id=user_message.id,
            idempotency_key=idempotency_key,
            status="pending",
            agent_version=runtime_agent_version.label,
            agent_prompt_hash=runtime_agent_version.prompt_sha256,
            trace_encrypted=(
                encrypt_json({"voice_emotion": voice_emotion.to_dict()})
                if voice_emotion is not None
                else None
            ),
        )
        db.add(event)
        db.commit()

        history = _recent_chat_history(db, conversation.id)
        agent = daily_factory()
        for delta in agent.stream_reply(history, voice_emotion=voice_emotion):
            if delta:
                yield {"type": "delta", "text": delta}
        result = agent.streamed_turn_result()
        assistant_message = Message(
            conversation_id=conversation.id,
            sequence=next_sequence + 1,
            role="agent",
            content_encrypted=encrypt_text(result.reply),
        )
        db.add(assistant_message)
        db.flush()
        metadata = _completion_payload(result)
        event.assistant_message_id = assistant_message.id
        event.status = "safety" if result.safety_event else "success"
        event.trace_encrypted = encrypt_json(result.trace) if result.trace else None
        event.safety_event = result.safety_event
        event.latency_ms = int((time.perf_counter() - started) * 1000)
        event.completed_at = utcnow()
        for key, value in metadata.items():
            setattr(event, key, value)
        db.commit()
        yield {"type": "done", "status": event.status, "deduplicated": False}
    except GeneratorExit:
        db.rollback()
        if event is not None and event.id:
            persisted = db.get(TurnEvent, event.id)
            if persisted is not None and persisted.status == "pending":
                persisted.status = "error"
                persisted.error_type = "StreamCancelled"
                persisted.error_encrypted = encrypt_text("Voice client disconnected.")
                persisted.latency_ms = int((time.perf_counter() - started) * 1000)
                persisted.completed_at = utcnow()
                db.commit()
        raise
    except Exception as exc:
        db.rollback()
        if event is not None and event.id:
            persisted = db.get(TurnEvent, event.id)
            if persisted is not None:
                persisted.status = "error"
                persisted.error_type = type(exc).__name__
                persisted.error_encrypted = encrypt_text(str(exc)[:1000])
                persisted.latency_ms = int((time.perf_counter() - started) * 1000)
                persisted.completed_at = utcnow()
                db.commit()
        yield {"type": "error", "detail": "Daily Chat reply is temporarily unavailable."}
    finally:
        db.execute(
            update(Conversation)
            .where(
                Conversation.id == conversation.id,
                Conversation.active_request_id == request_token,
            )
            .values(active_request_id=None, processing_started_at=None)
        )
        db.commit()


def turn_event_payload(event: TurnEvent) -> Dict[str, Any]:
    return {
        "id": event.id,
        "user_message_id": event.user_message_id,
        "assistant_message_id": event.assistant_message_id,
        "status": event.status,
        "agent_version": event.agent_version,
        "agent_prompt_hash": event.agent_prompt_hash,
        "model": event.model,
        "deployment": event.deployment,
        "api_version": event.api_version,
        "provider_request_id": event.provider_request_id,
        "finish_reason": event.finish_reason,
        "usage": {
            "prompt_tokens": event.prompt_tokens,
            "completion_tokens": event.completion_tokens,
            "total_tokens": event.total_tokens,
        },
        "latency_ms": event.latency_ms,
        "error_type": event.error_type,
        "error": decrypt_text(event.error_encrypted),
        "trace": decrypt_json(event.trace_encrypted),
        "safety_event": event.safety_event,
        "created_at": event.created_at.isoformat(),
        "completed_at": event.completed_at.isoformat() if event.completed_at else None,
    }


def dialogue_history_payload(conversation: Conversation) -> List[Dict[str, str]]:
    """Return the full transcript in the public Agent history format."""
    return [
        {
            "role": message.role,
            "content": decrypt_text(message.content_encrypted),
        }
        for message in conversation.messages
    ]


def full_export_payload(conversation: Conversation) -> Dict[str, Any]:
    payload = conversation_payload(conversation, include_scenario=True)
    payload["turn_events"] = [turn_event_payload(event) for event in conversation.turn_events]
    payload["course_homework_entries"] = [
        {
            "id": entry.id,
            "lesson_id": entry.lesson_id,
            "payload": decrypt_json(entry.payload_encrypted),
            "created_at": entry.created_at.isoformat(),
        }
        for entry in conversation.homework_entries
    ]
    return payload


def audit_admin(db: Session, action: str, target_id: Optional[str] = None, detail: Optional[str] = None) -> None:
    db.add(AdminAuditLog(action=action, target_id=target_id, detail=detail))
    db.commit()
