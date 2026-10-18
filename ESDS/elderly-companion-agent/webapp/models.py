from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from webapp.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


class Participant(Base):
    __tablename__ = "participants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    label: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    invite_hash: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    conversations = relationship("Conversation", back_populates="participant", cascade="all, delete-orphan")
    consents = relationship("Consent", back_populates="participant", cascade="all, delete-orphan")


class Consent(Base):
    __tablename__ = "consents"
    __table_args__ = (UniqueConstraint("participant_id", "version", name="uq_consent_participant_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    participant_id: Mapped[str] = mapped_column(ForeignKey("participants.id", ondelete="CASCADE"), index=True)
    version: Mapped[str] = mapped_column(String(40))
    agreed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    participant = relationship("Participant", back_populates="consents")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    participant_id: Mapped[str] = mapped_column(ForeignKey("participants.id", ondelete="CASCADE"), index=True)
    mode: Mapped[str] = mapped_column(String(20), index=True)
    agent_version: Mapped[str] = mapped_column(String(80), index=True)
    agent_prompt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lesson_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    lesson_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    active_course_key: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    scenario_id: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    scenario_version: Mapped[str | None] = mapped_column(String(30), nullable=True)
    scenario_snapshot_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    scenario_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    agent_state_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    active_request_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    participant = relationship("Participant", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan", order_by="Message.sequence")
    turn_events = relationship("TurnEvent", back_populates="conversation", cascade="all, delete-orphan")
    interaction_reflections = relationship("InteractionReflectionMemory", back_populates="conversation", cascade="all, delete-orphan")
    homework_entries = relationship(
        "CourseHomeworkEntry",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (UniqueConstraint("conversation_id", "sequence", name="uq_message_conversation_sequence"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(20))
    content_encrypted: Mapped[str] = mapped_column(Text)
    attachment_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    conversation = relationship("Conversation", back_populates="messages")


class CourseHomeworkEntry(Base):
    __tablename__ = "course_homework_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        index=True,
    )
    participant_id: Mapped[str] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"),
        index=True,
    )
    lesson_id: Mapped[str] = mapped_column(String(40), index=True)
    payload_encrypted: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    conversation = relationship("Conversation", back_populates="homework_entries")


class TurnEvent(Base):
    __tablename__ = "turn_events"
    __table_args__ = (UniqueConstraint("conversation_id", "idempotency_key", name="uq_turn_idempotency"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    user_message_id: Mapped[str | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    assistant_message_id: Mapped[str | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), index=True)
    agent_version: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    agent_prompt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    deployment: Mapped[str | None] = mapped_column(String(120), nullable=True)
    api_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    provider_request_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    finish_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    trace_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    safety_event: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    conversation = relationship("Conversation", back_populates="turn_events")


class InteractionReflectionMemory(Base):
    __tablename__ = "interaction_reflections"
    __table_args__ = (UniqueConstraint("turn_event_id", name="uq_interaction_reflection_event"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    participant_id: Mapped[str] = mapped_column(ForeignKey("participants.id", ondelete="CASCADE"), index=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    turn_event_id: Mapped[str] = mapped_column(ForeignKey("turn_events.id", ondelete="CASCADE"))
    source_message_id: Mapped[str] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"))
    lesson_id: Mapped[str] = mapped_column(String(40))
    scope: Mapped[str] = mapped_column(String(20))
    memory_kind: Mapped[str] = mapped_column(String(30), default="interaction_style", server_default="interaction_style", index=True)
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active")
    payload_encrypted: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    conversation = relationship("Conversation", back_populates="interaction_reflections")


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    action: Mapped[str] = mapped_column(String(80), index=True)
    target_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RateLimitBucket(Base):
    __tablename__ = "rate_limit_buckets"

    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
