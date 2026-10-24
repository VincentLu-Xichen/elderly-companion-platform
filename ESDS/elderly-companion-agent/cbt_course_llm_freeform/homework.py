"""Explicit learner-entered diaries, separate from classroom answers and plans."""

import uuid

from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from sqlalchemy.exc import IntegrityError

from cbt_course_llm_freeform.catalog import lesson_version
from webapp.models import CourseHomeworkEntry, TurnEvent, utcnow
from webapp.security import decrypt_json, encrypt_json


class DiaryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    idempotency_key: str = Field(min_length=8, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    source_kind: Literal["personal", "fictional"]
    situation: str = Field(min_length=1, max_length=500)
    thought: str = Field(default="", max_length=500)
    emotion: str = Field(default="", max_length=500)
    behavior: str = Field(default="", max_length=500)


def entries(conversation):
    return [
        {
            "id": row.id,
            "created_at": row.created_at.isoformat(),
            **decrypt_json(row.payload_encrypted),
        }
        for row in sorted(conversation.homework_entries, key=lambda row: row.created_at)
    ]


def save(db, conversation, payload):
    if conversation.lesson_id not in {
        "lesson-1",
        "lesson-2",
    } or conversation.lesson_version != lesson_version(conversation.lesson_id):
        raise ValueError("历史版本只读，请从课程目录进入新版。")
    state = decrypt_json(conversation.agent_state_encrypted)
    if not state.get("completed") or state.get("safety_paused"):
        raise ValueError("请先完成本课，再填写课后练习。")
    fields = {
        key: value.strip()
        for key, value in payload.model_dump().items()
        if key in {"situation", "thought", "emotion", "behavior"}
    }
    if not fields["situation"]:
        raise ValueError("请填写一件具体事情；其他暂时想不到的部分可以留空。")
    if conversation.lesson_id == "lesson-2" and fields["behavior"]:
        raise ValueError("第二课使用情境、想法、情绪三栏。")
    if conversation.lesson_id == "lesson-2":
        fields.pop("behavior")
    data = dict(
        schema_version="course-diary/1",
        lesson_version=conversation.lesson_version,
        source_kind=payload.source_kind,
        fields=fields,
        application_status="learner_report_not_verified",
    )
    entry_id = str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"{conversation.id}:diary:{payload.idempotency_key}")
    )
    existing = db.get(CourseHomeworkEntry, entry_id)
    if existing:
        if (
            existing.participant_id != conversation.participant_id
            or decrypt_json(existing.payload_encrypted) != data
        ):
            raise ValueError("这次保存标识已用于另一份内容，请刷新后另存。")
        return existing
    row = CourseHomeworkEntry(
        id=entry_id,
        conversation_id=conversation.id,
        participant_id=conversation.participant_id,
        lesson_id=conversation.lesson_id,
        payload_encrypted=encrypt_json(data),
    )
    db.add(row)
    db.add(
        TurnEvent(
            conversation_id=conversation.id,
            idempotency_key="diary:" + payload.idempotency_key,
            status="success",
            agent_version=conversation.agent_version,
            completed_at=utcnow(),
            total_tokens=0,
            latency_ms=0,
            trace_encrypted=encrypt_json(
                dict(kind="course_diary_saved", entry_id=entry_id, model_called=False)
            ),
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.get(CourseHomeworkEntry, entry_id)
        if (
            not existing
            or existing.participant_id != conversation.participant_id
            or decrypt_json(existing.payload_encrypted) != data
        ):
            raise ValueError("记录保存冲突，请刷新后重试。")
        return existing
    return row
