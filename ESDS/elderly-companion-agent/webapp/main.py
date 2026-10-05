from __future__ import annotations

import csv
import io
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, Optional
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from cbt_course_llm_freeform.router import register_course_routes
from webapp.config import settings
from webapp.database import SessionLocal, init_database
from webapp.models import Conversation, Participant
from webapp.rate_limit import enforce_rate_limit
from webapp.schemas import AdminLogin, ConsentInput, ConversationCreate, InviteLogin, MessageCreate
from webapp.security import csrf_matches, new_csrf_token, sign_session, verify_session
from webapp.services import (
    audit_admin,
    authenticate_invite,
    bootstrap_invites,
    conversation_payload,
    create_conversation,
    dialogue_history_payload,
    full_export_payload,
    get_owned_conversation,
    has_current_consent,
    process_turn,
    record_consent,
)
from webapp.voice_bridge import router as voice_bridge_router


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("roleplay-chat")

CSV_EXPORT_FIELDS = [
    "conversation_id",
    "participant",
    "mode",
    "agent_version",
    "agent_prompt_hash",
    "turn_agent_version",
    "turn_agent_prompt_hash",
    "scenario_id",
    "scenario_version",
    "lesson_id",
    "lesson_version",
    "conversation_status",
    "conversation_started_at",
    "conversation_ended_at",
    "sequence",
    "role",
    "content",
    "message_created_at",
]

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
app = FastAPI(title="老年人角色扮演对话测试", docs_url=None if settings.is_production else "/docs")
app.include_router(voice_bridge_router)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.mount(
    "/cbt-course-assets",
    StaticFiles(directory=PROJECT_DIR / "cbt_course" / "assets"),
    name="cbt-course-assets",
)
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def format_utc8(value: datetime | str | None) -> str:
    if value is None:
        return ""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M")


templates.env.filters["utc8"] = format_utc8


@app.on_event("startup")
def startup() -> None:
    if settings.is_production:
        missing = []
        if settings.admin_password == "change-me":
            missing.append("ADMIN_PASSWORD")
        if settings.app_secret == "local-development-secret-change-me":
            missing.append("APP_SECRET")
        if not settings.data_encryption_key:
            missing.append("DATA_ENCRYPTION_KEY")
        if settings.invite_codes == "student-001:demo001,student-002:demo002":
            missing.append("INVITE_CODES")
        if settings.voice_bridge_enabled:
            if not settings.voice_bridge_token:
                missing.append("VOICE_BRIDGE_TOKEN")
            if not settings.voice_device_id:
                missing.append("VOICE_DEVICE_ID")
        if missing:
            raise RuntimeError(f"Production secrets must be configured: {', '.join(missing)}")
    if not settings.is_vercel:
        init_database()
        with SessionLocal() as db:
            bootstrap_invites(db)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def current_participant(request: Request, db: Session = Depends(get_db)) -> Participant:
    participant_id = verify_session(request.cookies.get("participant_session"), "participant")
    participant = db.get(Participant, participant_id) if participant_id else None
    if participant is None or not participant.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先使用邀请码登录。")
    return participant


def current_admin(request: Request) -> str:
    admin = verify_session(request.cookies.get("admin_session"), "admin")
    if not admin:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录管理员后台。")
    return admin


def require_csrf(request: Request, x_csrf_token: Optional[str] = Header(default=None)) -> None:
    if not csrf_matches(request.cookies.get("csrf_token"), x_csrf_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="安全校验失败，请刷新页面后重试。")


def set_session_cookies(response: Response, *, kind: str, subject: str) -> None:
    cookie_name = "participant_session" if kind == "participant" else "admin_session"
    response.set_cookie(
        cookie_name,
        sign_session(kind, subject),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        max_age=settings.session_hours * 3600,
    )
    response.set_cookie(
        "csrf_token",
        new_csrf_token(),
        httponly=False,
        secure=settings.cookie_secure,
        samesite="strict",
        max_age=settings.session_hours * 3600,
    )


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; frame-ancestors 'none'"
    )
    return response


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def login_page(request: Request):
    if verify_session(request.cookies.get("participant_session"), "participant"):
        return RedirectResponse("/app", status_code=303)
    return templates.TemplateResponse(request=request, name="login.html", context={})


@app.get("/app", response_class=HTMLResponse)
def participant_home(request: Request, participant: Participant = Depends(current_participant), db: Session = Depends(get_db)):
    consented = has_current_consent(db, participant.id)
    conversations = db.scalars(
        select(Conversation)
        .where(Conversation.participant_id == participant.id)
        .order_by(Conversation.started_at.desc())
    ).all()
    return templates.TemplateResponse(
        request=request,
        name="app.html",
        context={"participant": participant, "consented": consented, "conversations": conversations},
    )


@app.get("/conversations/{conversation_id}", response_class=HTMLResponse)
def conversation_page(
    conversation_id: str,
    request: Request,
    participant: Participant = Depends(current_participant),
    db: Session = Depends(get_db),
):
    conversation = get_owned_conversation(db, conversation_id, participant.id)
    if not conversation:
        raise HTTPException(404)
    if conversation.lesson_id:
        return RedirectResponse(f"/cbt-course/conversations/{conversation.id}", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="chat.html",
        context={"conversation": conversation_payload(conversation)},
    )


@app.post("/api/session/invite")
def invite_login(payload: InviteLogin, request: Request, db: Session = Depends(get_db)):
    enforce_rate_limit(db, f"invite:{request.client.host if request.client else 'unknown'}")
    participant = authenticate_invite(db, payload.code)
    if not participant:
        raise HTTPException(401, "邀请码无效或已停用。")
    response = JSONResponse({"ok": True, "participant": participant.label})
    set_session_cookies(response, kind="participant", subject=participant.id)
    logger.info("participant_login participant=%s", participant.id)
    return response


@app.post("/api/session/logout", dependencies=[Depends(require_csrf)])
def participant_logout(participant: Participant = Depends(current_participant)):
    response = JSONResponse({"ok": True})
    response.delete_cookie(
        "participant_session",
        path="/",
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )
    response.delete_cookie(
        "csrf_token",
        path="/",
        httponly=False,
        secure=settings.cookie_secure,
        samesite="strict",
    )
    logger.info("participant_logout participant=%s", participant.id)
    return response


@app.post("/api/consents", dependencies=[Depends(require_csrf)])
def consent(payload: ConsentInput, participant: Participant = Depends(current_participant), db: Session = Depends(get_db)):
    if not payload.agreed:
        raise HTTPException(400, "必须确认测试数据记录告知后才能开始。")
    record = record_consent(db, participant.id)
    return {"ok": True, "version": record.version, "agreed_at": record.agreed_at.isoformat()}


@app.post("/api/conversations", dependencies=[Depends(require_csrf)])
def conversation_create(
    payload: ConversationCreate,
    participant: Participant = Depends(current_participant),
    db: Session = Depends(get_db),
):
    if not has_current_consent(db, participant.id):
        raise HTTPException(403, "请先确认测试数据记录告知。")
    if payload.mode == "cbt":
        raise HTTPException(400, "请从 CBT 课程目录选择课程。")
    conversation = create_conversation(db, participant.id, payload.mode)
    logger.info("conversation_created participant=%s conversation=%s mode=%s", participant.id, conversation.id, payload.mode)
    return conversation_payload(conversation)


@app.get("/api/conversations/{conversation_id}")
def conversation_get(
    conversation_id: str,
    participant: Participant = Depends(current_participant),
    db: Session = Depends(get_db),
):
    conversation = get_owned_conversation(db, conversation_id, participant.id)
    if not conversation:
        raise HTTPException(404)
    return conversation_payload(conversation)


@app.post("/api/conversations/{conversation_id}/messages", dependencies=[Depends(require_csrf)])
def message_create(
    conversation_id: str,
    payload: MessageCreate,
    participant: Participant = Depends(current_participant),
    db: Session = Depends(get_db),
):
    content = payload.content.strip()
    if not content:
        raise HTTPException(422, "消息不能为空。")
    if len(content) > settings.max_message_chars:
        raise HTTPException(413, f"单条消息不能超过 {settings.max_message_chars} 个字符。")
    enforce_rate_limit(db, f"message:{participant.id}")
    conversation = get_owned_conversation(db, conversation_id, participant.id)
    if not conversation:
        raise HTTPException(404)
    if conversation.lesson_id:
        raise HTTPException(400, "请使用课程消息接口继续学习。")
    if conversation.mode == "cbt":
        raise HTTPException(400, "旧 CBT 角色会话已归档，只能查看或导出。")
    try:
        result = process_turn(
            db,
            conversation,
            content=content,
            idempotency_key=payload.idempotency_key,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        logger.warning("turn_failed participant=%s conversation=%s type=%s", participant.id, conversation.id, type(exc).__name__)
        raise HTTPException(502, str(exc)) from exc
    logger.info("turn_complete participant=%s conversation=%s status=%s", participant.id, conversation.id, result["status"])
    return result


@app.delete("/api/conversations/{conversation_id}", dependencies=[Depends(require_csrf)])
def conversation_delete(
    conversation_id: str,
    participant: Participant = Depends(current_participant),
    db: Session = Depends(get_db),
):
    conversation = get_owned_conversation(db, conversation_id, participant.id)
    if not conversation:
        raise HTTPException(404)
    if conversation.lesson_id:
        raise HTTPException(400, "课程记录不能通过旧会话接口删除。")
    db.delete(conversation)
    db.commit()
    logger.info("conversation_deleted participant=%s conversation=%s", participant.id, conversation_id)
    return {"ok": True}


@app.post("/api/conversations/{conversation_id}/end", dependencies=[Depends(require_csrf)])
def conversation_end(
    conversation_id: str,
    participant: Participant = Depends(current_participant),
    db: Session = Depends(get_db),
):
    from webapp.models import utcnow

    conversation = get_owned_conversation(db, conversation_id, participant.id)
    if not conversation:
        raise HTTPException(404)
    if conversation.lesson_id:
        raise HTTPException(400, "课程进度会自动保存，无需手动结束。")
    if conversation.status == "active":
        conversation.status = "ended"
        conversation.ended_at = utcnow()
        db.commit()
    logger.info("conversation_ended participant=%s conversation=%s", participant.id, conversation_id)
    return {"ok": True}


@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request, db: Session = Depends(get_db)):
    if not verify_session(request.cookies.get("admin_session"), "admin"):
        return templates.TemplateResponse(request=request, name="admin_login.html", context={})
    conversations = db.scalars(
        select(Conversation).options(selectinload(Conversation.participant)).order_by(Conversation.started_at.desc()).limit(200)
    ).all()
    agent_versions = db.execute(
        select(Conversation.mode, Conversation.agent_version)
        .distinct()
        .order_by(Conversation.mode, Conversation.agent_version)
    ).all()
    return templates.TemplateResponse(
        request=request,
        name="admin_list.html",
        context={"conversations": conversations, "agent_versions": agent_versions},
    )


@app.post("/api/admin/login")
def admin_login(payload: AdminLogin, request: Request, db: Session = Depends(get_db)):
    enforce_rate_limit(db, f"admin-login:{request.client.host if request.client else 'unknown'}")
    import hmac

    if not hmac.compare_digest(payload.password, settings.admin_password):
        raise HTTPException(401, "管理员密码错误。")
    response = JSONResponse({"ok": True})
    set_session_cookies(response, kind="admin", subject="administrator")
    return response


def admin_conversation(db: Session, conversation_id: str) -> Conversation:
    conversation = db.scalar(
        select(Conversation)
        .options(
            selectinload(Conversation.participant),
            selectinload(Conversation.messages),
            selectinload(Conversation.turn_events),
            selectinload(Conversation.homework_entries),
        )
        .where(Conversation.id == conversation_id)
    )
    if not conversation:
        raise HTTPException(404)
    return conversation


def _write_conversation_csv_rows(writer: csv.DictWriter, conversation: Conversation) -> None:
    payload = full_export_payload(conversation)
    event_by_message_id = {
        message_id: event
        for event in payload["turn_events"]
        for message_id in (event["user_message_id"], event["assistant_message_id"])
        if message_id
    }
    messages = payload["messages"] or [None]
    for message in messages:
        turn_event = event_by_message_id.get(message["id"], {}) if message else {}
        writer.writerow(
            {
                "conversation_id": payload["id"],
                "participant": payload["participant_label"],
                "mode": payload["mode"],
                "agent_version": payload["agent_version"],
                "agent_prompt_hash": payload["agent_prompt_hash"],
                "turn_agent_version": turn_event.get("agent_version", ""),
                "turn_agent_prompt_hash": turn_event.get("agent_prompt_hash", ""),
                "scenario_id": payload["scenario_id"] or "",
                "scenario_version": payload["scenario_version"] or "",
                "lesson_id": payload["lesson_id"] or "",
                "lesson_version": payload["lesson_version"] or "",
                "conversation_status": payload["status"],
                "conversation_started_at": payload["started_at"],
                "conversation_ended_at": payload["ended_at"] or "",
                "sequence": message["sequence"] if message else "",
                "role": message["role"] if message else "",
                "content": message["content"] if message else "",
                "message_created_at": message["created_at"] if message else "",
            }
        )


def _safe_filename_fragment(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_", "."} else "-" for char in value)


def _history_dialogue_export_key(conversation: Conversation) -> str:
    topic = conversation.lesson_id or conversation.scenario_id or conversation.mode
    return f"history_dialogue_{topic}"


@app.get("/admin/conversations/{conversation_id}", response_class=HTMLResponse)
def admin_conversation_page(
    conversation_id: str,
    request: Request,
    admin: str = Depends(current_admin),
    db: Session = Depends(get_db),
):
    conversation = admin_conversation(db, conversation_id)
    payload = full_export_payload(conversation)
    audit_admin(db, "view_conversation", conversation_id)
    return templates.TemplateResponse(
        request=request,
        name="admin_detail.html",
        context={"conversation": payload},
    )


@app.get("/admin/exports/{conversation_id}.json")
def admin_export_json(
    conversation_id: str,
    admin: str = Depends(current_admin),
    db: Session = Depends(get_db),
):
    conversation = admin_conversation(db, conversation_id)
    payload = dialogue_history_payload(conversation)
    audit_admin(db, "export_json", conversation_id)
    return Response(
        json.dumps(payload, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="dialogue-history-{conversation_id}.json"'},
    )


@app.get("/admin/exports/{conversation_id}.csv")
def admin_export_csv(
    conversation_id: str,
    admin: str = Depends(current_admin),
    db: Session = Depends(get_db),
):
    conversation = admin_conversation(db, conversation_id)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_EXPORT_FIELDS)
    writer.writeheader()
    _write_conversation_csv_rows(writer, conversation)
    audit_admin(db, "export_csv", conversation_id)
    return Response(
        "\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="conversation-{conversation_id}.csv"'},
    )


@app.get("/admin/exports/bulk/ended-dialogues.json")
def admin_export_ended_dialogues_json(
    mode: str = Query(pattern="^(cbt|daily_chat)$"),
    agent_version: str = Query(min_length=1, max_length=80),
    admin: str = Depends(current_admin),
    db: Session = Depends(get_db),
):
    conversations = _ended_conversations(db, mode, agent_version)
    payload = [
        {_history_dialogue_export_key(conversation): dialogue_history_payload(conversation)}
        for conversation in conversations
    ]
    audit_admin(
        db,
        "export_ended_conversation_dialogues_json",
        detail=json.dumps(
            {"mode": mode, "agent_version": agent_version, "conversation_count": len(conversations)},
            ensure_ascii=False,
        ),
    )
    safe_version = _safe_filename_fragment(agent_version)
    return Response(
        json.dumps(payload, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="dialogues-{mode}-{safe_version}.json"'},
    )


def _ended_conversations(db: Session, mode: str, agent_version: str) -> list[Conversation]:
    return list(db.scalars(
        select(Conversation)
        .options(
            selectinload(Conversation.participant),
            selectinload(Conversation.messages),
            selectinload(Conversation.turn_events),
            selectinload(Conversation.homework_entries),
        )
        .where(
            Conversation.mode == mode,
            Conversation.agent_version == agent_version,
            Conversation.status.in_(("ended", "completed")),
        )
        .order_by(Conversation.started_at.asc())
    ).all())


@app.get("/admin/exports/bulk/ended.json")
def admin_export_ended_json(
    mode: str = Query(pattern="^(cbt|daily_chat)$"),
    agent_version: str = Query(min_length=1, max_length=80),
    admin: str = Depends(current_admin),
    db: Session = Depends(get_db),
):
    conversations = _ended_conversations(db, mode, agent_version)
    payload = [full_export_payload(conversation) for conversation in conversations]
    audit_admin(
        db,
        "export_ended_conversations_json",
        detail=json.dumps(
            {"mode": mode, "agent_version": agent_version, "conversation_count": len(conversations)},
            ensure_ascii=False,
        ),
    )
    safe_version = _safe_filename_fragment(agent_version)
    return Response(
        json.dumps(payload, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="ended-{mode}-{safe_version}.json"'},
    )


@app.get("/admin/exports/{conversation_id}/full.json")
def admin_export_full_json(
    conversation_id: str,
    admin: str = Depends(current_admin),
    db: Session = Depends(get_db),
):
    conversation = admin_conversation(db, conversation_id)
    payload = full_export_payload(conversation)
    audit_admin(db, "export_full_json", conversation_id)
    return Response(
        json.dumps(payload, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="conversation-{conversation_id}.full.json"'},
    )


@app.delete("/api/admin/conversations/{conversation_id}", dependencies=[Depends(require_csrf)])
def admin_delete_conversation(
    conversation_id: str,
    admin: str = Depends(current_admin),
    db: Session = Depends(get_db),
):
    conversation = admin_conversation(db, conversation_id)
    db.delete(conversation)
    db.commit()
    audit_admin(db, "delete_conversation", conversation_id)
    return {"ok": True}


register_course_routes(
    app,
    get_db=get_db,
    current_participant=current_participant,
    require_csrf=require_csrf,
    templates=templates,
)
