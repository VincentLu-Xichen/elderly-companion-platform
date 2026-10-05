from __future__ import annotations

import hashlib
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cbt_course.catalog import LESSON_1_VERSION, require_available_course
from cbt_course.engine import CourseEngine, course_payload, new_course_state
from cbt_course.lesson_1 import INITIAL_MESSAGE, STATIC_ATTACHMENTS
from cbt_course.prompt import COURSE_TUTOR_SYSTEM_PROMPT
from cbt_course.schemas import CourseTurnResult
from webapp.config import settings
from webapp.models import Conversation, CourseHomeworkEntry, Message, TurnEvent, utcnow
from webapp.security import decrypt_json, decrypt_text, encrypt_json, encrypt_text


def course_prompt_hash() -> str:
    return hashlib.sha256(COURSE_TUTOR_SYSTEM_PROMPT.encode("utf-8")).hexdigest()


def course_agent_version() -> str:
    return settings.cbt_course_agent_version


def _active_key(participant_id: str, lesson_id: str) -> str:
    return f"{participant_id}:{lesson_id}"


def create_or_resume_course(
    db: Session,
    *,
    participant_id: str,
    lesson_id: str,
) -> tuple[Conversation, bool]:
    require_available_course(lesson_id)
    active_key = _active_key(participant_id, lesson_id)
    existing = db.scalar(select(Conversation).where(Conversation.active_course_key == active_key))
    if existing:
        return existing, True

    state = new_course_state(lesson_id)
    conversation = Conversation(
        participant_id=participant_id,
        mode="cbt",
        agent_version=course_agent_version(),
        agent_prompt_hash=course_prompt_hash(),
        lesson_id=lesson_id,
        lesson_version=LESSON_1_VERSION,
        active_course_key=active_key,
        agent_state_encrypted=encrypt_json(state),
    )
    db.add(conversation)
    db.flush()
    db.add(
        Message(
            conversation_id=conversation.id,
            sequence=1,
            role="agent",
            content_encrypted=encrypt_text(INITIAL_MESSAGE),
            attachment_encrypted=encrypt_json(STATIC_ATTACHMENTS["course_overview"]),
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(Conversation).where(Conversation.active_course_key == active_key))
        if existing:
            return existing, True
        raise
    db.refresh(conversation)
    return conversation, False


def get_owned_course(
    db: Session,
    *,
    conversation_id: str,
    participant_id: str,
) -> Conversation | None:
    return db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.participant_id == participant_id,
            Conversation.lesson_id.is_not(None),
        )
    )


def _message_payload(message: Message) -> dict[str, Any]:
    return {
        "id": message.id,
        "sequence": message.sequence,
        "role": message.role,
        "content": decrypt_text(message.content_encrypted),
        "attachment": decrypt_json(message.attachment_encrypted),
        "created_at": message.created_at.isoformat(),
    }


def course_conversation_payload(conversation: Conversation) -> dict[str, Any]:
    state = decrypt_json(conversation.agent_state_encrypted)
    return {
        "id": conversation.id,
        "participant_id": conversation.participant_id,
        "mode": conversation.mode,
        "lesson_id": conversation.lesson_id,
        "lesson_version": conversation.lesson_version,
        "status": conversation.status,
        "started_at": conversation.started_at.isoformat(),
        "ended_at": conversation.ended_at.isoformat() if conversation.ended_at else None,
        "messages": [_message_payload(message) for message in conversation.messages],
        "course": course_payload(state),
        "homework_count": len(conversation.homework_entries),
    }


def _completion_metadata(result: CourseTurnResult) -> dict[str, Any]:
    completion = result.completion
    if completion is None:
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


def _deduplicated_response(db: Session, conversation: Conversation, event: TurnEvent) -> dict[str, Any]:
    if event.status not in {"success", "safety"} or not event.assistant_message_id:
        raise RuntimeError("该请求已经处理失败，请修改内容后重试。")
    message = db.get(Message, event.assistant_message_id)
    return {
        "reply": decrypt_text(message.content_encrypted) if message else "",
        "attachment": decrypt_json(message.attachment_encrypted) if message else {},
        "status": event.status,
        "safety_event": event.safety_event,
        "deduplicated": True,
        "course": course_payload(decrypt_json(conversation.agent_state_encrypted)),
    }


def process_course_turn(
    db: Session,
    conversation: Conversation,
    *,
    content: str,
    idempotency_key: str,
    engine_factory: Callable[[], CourseEngine] = CourseEngine,
) -> dict[str, Any]:
    existing = db.scalar(
        select(TurnEvent).where(
            TurnEvent.conversation_id == conversation.id,
            TurnEvent.idempotency_key == idempotency_key,
        )
    )
    if existing:
        return _deduplicated_response(db, conversation, existing)
    if not conversation.lesson_id:
        raise ValueError("这不是课程会话。")
    if conversation.status not in {"active", "completed"}:
        raise ValueError("课程记录当前不可继续。")

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
    ).rowcount
    db.commit()
    if acquired != 1:
        raise RuntimeError("上一条消息仍在处理中，请稍后再试。")

    event: TurnEvent | None = None
    start = time.perf_counter()
    try:
        next_sequence = int(
            db.scalar(select(func.max(Message.sequence)).where(Message.conversation_id == conversation.id)) or 0
        ) + 1
        user_message = Message(
            conversation_id=conversation.id,
            sequence=next_sequence,
            role="learner",
            content_encrypted=encrypt_text(content),
        )
        db.add(user_message)
        db.flush()
        event = TurnEvent(
            conversation_id=conversation.id,
            user_message_id=user_message.id,
            idempotency_key=idempotency_key,
            status="pending",
            agent_version=course_agent_version(),
            agent_prompt_hash=course_prompt_hash(),
        )
        db.add(event)
        db.commit()

        conversation = db.get(Conversation, conversation.id)
        state = decrypt_json(conversation.agent_state_encrypted)
        result = engine_factory().process(state, content)

        assistant_message = Message(
            conversation_id=conversation.id,
            sequence=next_sequence + 1,
            role="agent",
            content_encrypted=encrypt_text(result.reply),
            attachment_encrypted=encrypt_json(result.attachment) if result.attachment else None,
        )
        db.add(assistant_message)
        db.flush()

        conversation.agent_state_encrypted = encrypt_json(result.state)
        if result.state.get("completed") and conversation.status == "active":
            conversation.status = "completed"
            conversation.ended_at = utcnow()
            conversation.active_course_key = None
        if result.homework_entry:
            db.add(
                CourseHomeworkEntry(
                    conversation_id=conversation.id,
                    participant_id=conversation.participant_id,
                    lesson_id=str(conversation.lesson_id),
                    payload_encrypted=encrypt_json(result.homework_entry),
                )
            )

        event.assistant_message_id = assistant_message.id
        event.status = "safety" if result.safety_event else "success"
        event.trace_encrypted = encrypt_json(result.trace) if result.trace else None
        event.safety_event = result.safety_event
        event.latency_ms = int((time.perf_counter() - start) * 1000)
        event.completed_at = utcnow()
        for key, value in _completion_metadata(result).items():
            setattr(event, key, value)
        db.commit()
        return {
            "reply": result.reply,
            "attachment": result.attachment,
            "status": event.status,
            "safety_event": result.safety_event,
            "deduplicated": False,
            "course": course_payload(result.state),
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
