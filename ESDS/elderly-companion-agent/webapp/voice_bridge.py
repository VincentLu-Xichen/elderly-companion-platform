"""Loopback-only API used by the Raspberry Pi voice gateway."""

from __future__ import annotations

import hmac
import json
import logging
from collections.abc import Generator
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from daily_agent.emotion_context import EmotionLabel, VoiceEmotionContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from webapp.config import settings
from webapp.database import SessionLocal
from webapp.models import Conversation, Participant
from webapp.rate_limit import enforce_rate_limit
from webapp.security import hash_secret
from webapp.services import (
    create_conversation,
    get_owned_conversation,
    has_current_consent,
    process_turn,
    record_consent,
    stream_process_turn,
)
from cbt_course_llm_freeform.catalog import LESSON_1_ID, require_available_course
from cbt_course_llm_freeform.services import (
    course_conversation_payload,
    create_or_resume_course,
    get_owned_course,
    process_course_turn,
)

logger = logging.getLogger("roleplay-chat.voice-bridge")


class VoiceSessionOpen(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(min_length=3, max_length=120)
    preferred_mode: str = Field(default="daily_chat", pattern="^daily_chat$")


class CbtVoiceSessionOpen(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(min_length=3, max_length=120)
    lesson_id: str = Field(default=LESSON_1_ID, pattern="^lesson-1$")


class CbtVoiceTurnCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transcript: str = Field(min_length=1, max_length=2000)
    idempotency_key: str = Field(min_length=8, max_length=80)


class VoiceEmotion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: EmotionLabel = "neutral"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, allow_inf_nan=False)
    evidence: list[Annotated[str, Field(max_length=64)]] = Field(default_factory=list, max_length=8)

    def context(self) -> VoiceEmotionContext:
        return VoiceEmotionContext(self.label, self.confidence, tuple(self.evidence))


class VoiceTurnCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transcript: str = Field(min_length=1, max_length=2000)
    idempotency_key: str = Field(min_length=8, max_length=80)
    emotion: VoiceEmotion | None = None


def get_voice_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_voice_bridge(
    authorization: str | None = Header(default=None),
) -> None:
    if not settings.voice_bridge_enabled or not settings.voice_bridge_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Voice bridge is disabled.",
        )
    scheme, _, supplied = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(
        supplied.encode(), settings.voice_bridge_token.encode()
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid voice bridge token.",
        )


def _voice_participant(db: Session) -> Participant:
    participant = db.scalar(
        select(Participant).where(
            Participant.label == settings.voice_participant_label
        )
    )
    if participant is None:
        participant = Participant(
            label=settings.voice_participant_label,
            invite_hash=hash_secret(
                f"voice:{settings.voice_device_id}:{settings.voice_bridge_token}"
            ),
        )
        db.add(participant)
        db.commit()
        db.refresh(participant)
    if not participant.is_active:
        raise HTTPException(status_code=403, detail="Voice participant is disabled.")
    if not has_current_consent(db, participant.id):
        if not settings.voice_consent_acknowledged:
            raise HTTPException(
                status_code=412,
                detail="Voice participant consent has not been acknowledged.",
            )
        record_consent(db, participant.id)
    return participant


router = APIRouter(
    prefix="/internal/voice/v1",
    dependencies=[Depends(require_voice_bridge)],
)


@router.get("/healthz")
def voice_healthz() -> dict[str, str]:
    return {"status": "ok", "mode": "daily_chat"}


@router.post("/sessions/open")
def open_voice_session(
    payload: VoiceSessionOpen,
    db: Session = Depends(get_voice_db),
) -> dict[str, object]:
    if not settings.voice_device_id or payload.device_id != settings.voice_device_id:
        raise HTTPException(status_code=403, detail="Voice device is not enrolled.")
    participant = _voice_participant(db)
    conversation = db.scalar(
        select(Conversation)
        .where(
            Conversation.participant_id == participant.id,
            Conversation.mode == "daily_chat",
            Conversation.status == "active",
            Conversation.lesson_id.is_(None),
        )
        .order_by(Conversation.started_at.desc())
    )
    resumed = conversation is not None
    if conversation is None:
        conversation = create_conversation(db, participant.id, "daily_chat")
    logger.info(
        "voice_session_opened participant=%s conversation=%s resumed=%s",
        participant.id,
        conversation.id,
        resumed,
    )
    return {
        "voice_session_id": conversation.id,
        "conversation_id": conversation.id,
        "participant_id": participant.id,
        "mode": "daily_chat",
        "resumed": resumed,
    }


@router.post("/sessions/{conversation_id}/turns")
def create_voice_turn(
    conversation_id: str,
    payload: VoiceTurnCreate,
    db: Session = Depends(get_voice_db),
) -> dict[str, object]:
    participant = _voice_participant(db)
    conversation = get_owned_conversation(
        db, conversation_id, participant.id
    )
    if conversation is None or conversation.mode != "daily_chat":
        raise HTTPException(status_code=404, detail="Voice session not found.")
    transcript = payload.transcript.strip()
    if not transcript:
        raise HTTPException(status_code=422, detail="Transcript is empty.")
    if len(transcript) > settings.max_message_chars:
        raise HTTPException(status_code=413, detail="Transcript is too long.")
    enforce_rate_limit(db, f"voice-message:{participant.id}")
    try:
        result = process_turn(
            db,
            conversation,
            content=transcript,
            idempotency_key=payload.idempotency_key,
            **({"voice_emotion": payload.emotion.context()} if payload.emotion is not None else {}),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.warning(
            "voice_turn_failed participant=%s conversation=%s type=%s",
            participant.id,
            conversation.id,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=502,
            detail="Daily Chat reply is temporarily unavailable.",
        ) from exc
    logger.info(
        "voice_turn_complete participant=%s conversation=%s status=%s",
        participant.id,
        conversation.id,
        result["status"],
    )
    return {
        **result,
        "conversation_id": conversation.id,
        "mode": "daily_chat",
    }


@router.post("/sessions/{conversation_id}/turns/stream")
def create_voice_turn_stream(
    conversation_id: str,
    payload: VoiceTurnCreate,
    db: Session = Depends(get_voice_db),
) -> StreamingResponse:
    participant = _voice_participant(db)
    conversation = get_owned_conversation(db, conversation_id, participant.id)
    if conversation is None or conversation.mode != "daily_chat":
        raise HTTPException(status_code=404, detail="Voice session not found.")
    transcript = payload.transcript.strip()
    if not transcript:
        raise HTTPException(status_code=422, detail="Transcript is empty.")
    if len(transcript) > settings.max_message_chars:
        raise HTTPException(status_code=413, detail="Transcript is too long.")
    enforce_rate_limit(db, f"voice-message:{participant.id}")

    def events():
        turn_stream = stream_process_turn(
            db,
            conversation,
            content=transcript,
            idempotency_key=payload.idempotency_key,
            **({"voice_emotion": payload.emotion.context()} if payload.emotion is not None else {}),
        )
        try:
            for item in turn_stream:
                yield "data: " + json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n\n"
        finally:
            turn_stream.close()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/cbt/sessions/open")
def open_cbt_voice_session(
    payload: CbtVoiceSessionOpen,
    db: Session = Depends(get_voice_db),
) -> dict[str, object]:
    if not settings.voice_device_id or payload.device_id != settings.voice_device_id:
        raise HTTPException(status_code=403, detail="Voice device is not enrolled.")
    try:
        require_available_course(payload.lesson_id)
        participant = _voice_participant(db)
        conversation, resumed = create_or_resume_course(
            db, participant_id=participant.id, lesson_id=payload.lesson_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info(
        "cbt_voice_session_opened participant=%s conversation=%s lesson=%s resumed=%s",
        participant.id, conversation.id, payload.lesson_id, resumed,
    )
    return {
        "voice_session_id": conversation.id,
        "conversation_id": conversation.id,
        "participant_id": participant.id,
        "mode": "cbt",
        "lesson_id": payload.lesson_id,
        "resumed": resumed,
        "course": course_conversation_payload(conversation)["course"],
    }


@router.post("/cbt/sessions/{conversation_id}/turns")
def create_cbt_voice_turn(
    conversation_id: str,
    payload: CbtVoiceTurnCreate,
    db: Session = Depends(get_voice_db),
) -> dict[str, object]:
    participant = _voice_participant(db)
    conversation = get_owned_course(
        db, conversation_id=conversation_id, participant_id=participant.id
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="CBT voice session not found.")
    if conversation.status != "active":
        raise HTTPException(status_code=409, detail="This CBT lesson is completed.")
    try:
        result = process_course_turn(
            db,
            conversation,
            content=payload.transcript.strip(),
            idempotency_key=payload.idempotency_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.warning(
            "cbt_voice_turn_failed participant=%s conversation=%s type=%s",
            participant.id, conversation.id, type(exc).__name__,
        )
        raise HTTPException(status_code=502, detail="CBT reply is temporarily unavailable.") from exc
    return {
        **result,
        "conversation_id": conversation.id,
        "mode": "cbt",
        "lesson_id": conversation.lesson_id,
        "completed": result["course"]["completed"],
    }
