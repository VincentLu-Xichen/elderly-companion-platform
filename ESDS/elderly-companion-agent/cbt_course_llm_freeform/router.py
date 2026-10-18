from __future__ import annotations

import logging
import json
import os
from typing import Any, Callable

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from cbt_course_llm_freeform.catalog import COURSE_CATALOG
from cbt_course_llm_freeform.schemas import CourseMessageCreate
from cbt_course_llm_freeform.services import (
    AGENT_VERSION,
    course_conversation_payload,
    create_or_resume_course,
    get_owned_course,
    process_course_turn,
)
from cbt_course_llm_freeform.catalog import lesson_version
from cbt_course_llm_freeform.reflection import generate_course_reflection
from cbt_course_llm_freeform.streaming import stream_course_turn
from webapp.config import settings
from webapp.models import Conversation, Participant
from webapp.rate_limit import enforce_rate_limit
from webapp.services import has_current_consent


logger = logging.getLogger("roleplay-chat.cbt-course-llm-freeform")


def register_course_routes(
    app: FastAPI,
    *,
    get_db: Callable[..., Any],
    current_participant: Callable[..., Any],
    require_csrf: Callable[..., Any],
    templates: Jinja2Templates,
) -> None:
    @app.get("/cbt-course", response_class=HTMLResponse)
    def course_catalog_page(
        request: Request,
        participant: Participant = Depends(current_participant),
        db: Session = Depends(get_db),
    ):
        conversations = db.scalars(
            select(Conversation)
            .where(Conversation.participant_id == participant.id, Conversation.lesson_id.is_not(None))
            .order_by(Conversation.started_at.desc())
        ).all()
        active_by_lesson: dict[str, Conversation] = {}
        latest_by_lesson: dict[str, Conversation] = {}
        for item in conversations:
            if item.lesson_id:
                latest_by_lesson.setdefault(item.lesson_id, item)
                if item.status == "active" and item.agent_version == AGENT_VERSION and item.lesson_version == lesson_version(item.lesson_id):
                    active_by_lesson.setdefault(item.lesson_id, item)
        return templates.TemplateResponse(
            request=request,
            name="cbt_course/catalog.html",
            context={
                "participant": participant,
                "consented": has_current_consent(db, participant.id),
                "courses": COURSE_CATALOG,
                "active_by_lesson": active_by_lesson,
                "latest_by_lesson": latest_by_lesson,
                "conversations": conversations,
                "preview_mode": os.getenv("CBT_PREVIEW_MODE") == "true" and settings.environment == "development",
                "demo_provider": {"deepseek": "DeepSeek", "dashscope": "百炼", "azure": "Azure OpenAI"}.get(os.getenv("CBT_DEMO_PROVIDER", ""), "") if settings.environment == "development" else "",
            },
        )

    @app.post("/api/cbt-course/lessons/{lesson_id}/start", dependencies=[Depends(require_csrf)])
    def course_start(
        lesson_id: str,
        participant: Participant = Depends(current_participant),
        db: Session = Depends(get_db),
    ):
        if not has_current_consent(db, participant.id):
            raise HTTPException(403, "请先确认数据记录告知。")
        try:
            conversation, resumed = create_or_resume_course(db, participant_id=participant.id, lesson_id=lesson_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {
            "id": conversation.id,
            "lesson_id": conversation.lesson_id,
            "resumed": resumed,
            "url": f"/cbt-course/conversations/{conversation.id}",
        }

    @app.get("/cbt-course/conversations/{conversation_id}", response_class=HTMLResponse)
    def course_conversation_page(
        conversation_id: str,
        request: Request,
        participant: Participant = Depends(current_participant),
        db: Session = Depends(get_db),
    ):
        conversation = get_owned_course(db, conversation_id=conversation_id, participant_id=participant.id)
        if not conversation:
            raise HTTPException(404)
        return templates.TemplateResponse(
            request=request,
            name="cbt_course/conversation.html",
            context={"participant": participant, "conversation": course_conversation_payload(conversation), "preview_mode": os.getenv("CBT_PREVIEW_MODE") == "true" and settings.environment == "development",
                     "demo_provider": {"deepseek": "DeepSeek", "dashscope": "百炼", "azure": "Azure OpenAI"}.get(os.getenv("CBT_DEMO_PROVIDER", ""), "") if settings.environment == "development" else ""},
        )

    @app.get("/api/cbt-course/conversations/{conversation_id}")
    def course_conversation_get(
        conversation_id: str,
        participant: Participant = Depends(current_participant),
        db: Session = Depends(get_db),
    ):
        conversation = get_owned_course(db, conversation_id=conversation_id, participant_id=participant.id)
        if not conversation:
            raise HTTPException(404)
        return course_conversation_payload(conversation)

    @app.post(
        "/api/cbt-course/conversations/{conversation_id}/messages",
        dependencies=[Depends(require_csrf)],
    )
    def course_message_create(
        conversation_id: str,
        payload: CourseMessageCreate,
        background_tasks: BackgroundTasks,
        participant: Participant = Depends(current_participant),
        db: Session = Depends(get_db),
    ):
        conversation = get_owned_course(db, conversation_id=conversation_id, participant_id=participant.id)
        if not conversation:
            raise HTTPException(404)
        content = payload.content.strip()
        if not has_current_consent(db, participant.id):
            raise HTTPException(403, "请先确认数据记录告知。")
        if not content and payload.action == "chat":
            raise HTTPException(422, "消息不能为空。")
        if len(content) > settings.max_message_chars:
            raise HTTPException(413, f"单条消息不能超过 {settings.max_message_chars} 个字符。")
        enforce_rate_limit(db, f"course-message:{participant.id}")
        try:
            result = process_course_turn(
                db,
                conversation,
                content=content,
                idempotency_key=payload.idempotency_key,
                action=payload.action,
                expected_revision=payload.expected_revision,
            )
            if result["course"]["completed"] and result["course"]["reflection"].get("status") == "pending":
                background_tasks.add_task(generate_course_reflection, conversation.id)
            return result
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except RuntimeError as exc:
            logger.warning(
                "course_turn_failed participant=%s conversation=%s type=%s",
                participant.id,
                conversation.id,
                type(exc).__name__,
            )
            raise HTTPException(502, "课程回复暂时不可用，本轮进度没有改变，请稍后重试。") from exc

    @app.post("/api/cbt-course/conversations/{conversation_id}/reflection", dependencies=[Depends(require_csrf)])
    def retry_course_reflection(
        conversation_id: str,
        background_tasks: BackgroundTasks,
        participant: Participant = Depends(current_participant),
        db: Session = Depends(get_db),
    ):
        conversation = get_owned_course(db, conversation_id=conversation_id, participant_id=participant.id)
        if conversation is None:
            raise HTTPException(404)
        if not has_current_consent(db, participant.id):
            raise HTTPException(403, "请先确认数据记录告知。")
        if conversation.status != "completed" or conversation.agent_version != AGENT_VERSION:
            raise HTTPException(400, "本课尚未完成或使用历史版本。")
        enforce_rate_limit(db, f"course-reflection:{participant.id}")
        background_tasks.add_task(generate_course_reflection, conversation.id)
        return {"ok": True}

    @app.post("/api/cbt-course/conversations/{conversation_id}/messages/stream", dependencies=[Depends(require_csrf)])
    def course_message_stream(
        conversation_id: str,
        payload: CourseMessageCreate,
        participant: Participant = Depends(current_participant),
        db: Session = Depends(get_db),
    ):
        conversation = get_owned_course(db, conversation_id=conversation_id, participant_id=participant.id)
        if conversation is None:
            raise HTTPException(404)
        if not has_current_consent(db, participant.id):
            raise HTTPException(403, "请先确认数据记录告知。")
        content = payload.content.strip()
        if not content and payload.action == "chat":
            raise HTTPException(422, "消息不能为空。")
        if len(content) > settings.max_message_chars:
            raise HTTPException(413, f"单条消息不能超过 {settings.max_message_chars} 个字符。")
        enforce_rate_limit(db, f"course-message:{participant.id}")
        participant_id = participant.id

        def events():
            stream = stream_course_turn(conversation_id=conversation_id, participant_id=participant_id,
                content=content, idempotency_key=payload.idempotency_key, action=payload.action, expected_revision=payload.expected_revision)
            try:
                for item in stream:
                    yield "data: " + json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n\n"
            finally:
                stream.close()

        return StreamingResponse(events(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})
