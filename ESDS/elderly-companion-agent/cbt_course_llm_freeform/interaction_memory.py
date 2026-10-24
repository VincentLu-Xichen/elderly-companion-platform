"""Owned interaction guidance, separate from confirmed learning artifacts."""

from sqlalchemy import or_, select

from cbt_course_llm_freeform.interaction import VERSION
from cbt_course_llm_freeform import boundaries
from webapp.models import Conversation, InteractionReflectionMemory, Message
from webapp.security import decrypt_json, decrypt_text, encrypt_json


def _query(conversation):
    # Join to live sources every turn: deletion cannot leave an active cached preference.
    return (
        select(InteractionReflectionMemory)
        .join(Conversation, InteractionReflectionMemory.conversation_id == Conversation.id)
        .join(Message, InteractionReflectionMemory.source_message_id == Message.id)
        .where(
            InteractionReflectionMemory.participant_id == conversation.participant_id,
            Conversation.participant_id == conversation.participant_id,
            Message.conversation_id == Conversation.id,
            Message.role == "learner",
            or_(
                InteractionReflectionMemory.conversation_id == conversation.id,
                InteractionReflectionMemory.scope == "cross_course",
            ),
        )
        .order_by(
            InteractionReflectionMemory.created_at.desc(), InteractionReflectionMemory.id.desc()
        )
    )


def load_memories(db, conversation):
    rows = db.scalars(
        _query(conversation)
        .where(
            InteractionReflectionMemory.memory_kind == "interaction_style",
            InteractionReflectionMemory.status == "active",
        )
        .limit(3)
    ).all()
    notes = []
    for row in rows:
        note = decrypt_json(row.payload_encrypted)
        if note.get("schema_version") == VERSION and note.get("verdict") == "feedback":
            notes.append({key: note[key] for key in ("id", "scope", "reply_length", "follow_up")})
            notes[-1].update(
                tone=note.get("tone", "standard"),
                response_type=note.get("response_type", "neutral"),
            )
    return notes


def load_boundary(db, conversation):
    rows = db.scalars(
        _query(conversation).where(
            InteractionReflectionMemory.memory_kind == "personal_disclosure",
            InteractionReflectionMemory.status == "active",
        )
    )
    for row in rows:
        note = decrypt_json(row.payload_encrypted)
        if note.get("schema_version") != boundaries.VERSION or note.get("behavior") not in {
            "do_not_solicit",
            "allow_invitation",
        }:
            continue
        valid = True
        for evidence in note.get("evidence", []):
            source = db.get(Message, evidence["message_id"])
            owner = db.get(Conversation, source.conversation_id) if source else None
            if (
                not owner
                or owner.participant_id != conversation.participant_id
                or source.role != "learner"
                or evidence["quote"] not in decrypt_text(source.content_encrypted)
            ):
                valid = False
                break
        if valid and note.get("evidence"):
            return {key: note[key] for key in ("id", "scope", "behavior")}
    return None


def save_memory(db, conversation, event, trace):
    decision = trace.get("boundary_event") or trace.get("interaction_event") or {}
    if decision.get("status") != "accepted":
        return
    note = decision["memory"]
    source = db.get(Message, note["source_message_id"])
    if (
        source is None
        or source.conversation_id != conversation.id
        or source.role != "learner"
        or source.id != event.user_message_id
    ):
        raise ValueError("Interaction memory source ownership mismatch")
    for evidence in note.get("evidence", []):
        original = db.get(Message, evidence["message_id"])
        if (
            original is None
            or original.conversation_id != conversation.id
            or original.role != "learner"
            or evidence["quote"] not in decrypt_text(original.content_encrypted)
        ):
            raise ValueError("Boundary confirmation source ownership mismatch")
    db.add(
        InteractionReflectionMemory(
            id=note["id"],
            participant_id=conversation.participant_id,
            conversation_id=conversation.id,
            turn_event_id=event.id,
            source_message_id=source.id,
            lesson_id=conversation.lesson_id,
            scope=note["scope"],
            memory_kind=(
                "personal_disclosure"
                if note.get("kind") == "personal_disclosure"
                else "interaction_style"
            ),
            status=note.get("status", "active"),
            payload_encrypted=encrypt_json(note),
        )
    )
