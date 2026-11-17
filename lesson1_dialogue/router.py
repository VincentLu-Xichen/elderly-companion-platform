"""Authenticated, consented, version-isolated first-lesson routes."""
import os
import logging
import json
from threading import Event
import anyio
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from . import services
from .public_errors import NOTICES, public_notice
from webapp.models import Conversation
from webapp.services import has_current_consent
from webapp.rate_limit import enforce_rate_limit
from webapp.config import settings


class PublicDialogueRoute(APIRoute):
    """Wrap dependencies, request parsing and endpoints, only for this module."""
    def get_route_handler(self):
        handler=super().get_route_handler()
        async def safe_handler(request):
            try:
                return await handler(request)
            except Exception as exc:
                notice=public_notice(exc,is_turn=request.url.path.endswith(('/messages','/messages/stream')))
                status,message,recovery,outcome=NOTICES[notice]
                logging.getLogger(__name__).warning("dialogue_request_failed notice=%s conversation_id=%s",
                    notice,request.path_params.get('conversation_id','none'))
                if request.url.path.startswith('/api/'):
                    return JSONResponse(status_code=status,content={"detail":message,"notice":notice,
                        "recovery":recovery,"outcome":outcome})
                destination,label=('/', '前往登录') if status==401 else ('/cbt-course/dialogue','返回课程入口')
                return HTMLResponse(status_code=status,content=f'<!doctype html><html lang="zh-CN">'
                    f'<meta charset="utf-8"><title>课程记录</title><p>{message}</p>'
                    f'<a href="{destination}">{label}</a></html>')
        return safe_handler


class TurnInput(BaseModel):
    model_config=ConfigDict(extra="forbid",strict=True)
    content:str=Field(default="",max_length=2000)
    action:str=Field(default="chat",max_length=50)
    idempotency_key:str=Field(min_length=1,max_length=80)
    expected_revision:int=Field(ge=0)


def register_dialogue_routes(app,*,get_db,current_participant,require_csrf,templates):
    routes=APIRouter(route_class=PublicDialogueRoute)
    def get_owned(db,cid,pid):
        conversation=services.owned(db,cid,pid)
        if conversation is None:raise HTTPException(404)
        return conversation

    @routes.get("/cbt-course/dialogue",response_class=HTMLResponse)
    def page(request:Request,participant=Depends(current_participant),db=Depends(get_db)):
        history=db.scalars(select(Conversation).where(Conversation.participant_id==participant.id,
            Conversation.agent_version==services.AGENT_VERSION).order_by(Conversation.started_at.desc())).all()
        return templates.TemplateResponse(request=request,name="cbt_course/dialogue.html",context={
            "conversation":None,"consented":has_current_consent(db,participant.id),"history":history,
            "lesson_version":services.LESSON_VERSION,"preview_kind":os.getenv('CBT_SINGLE_DIALOGUE_PREVIEW'),
            "offline_demo":os.getenv("CBT_DIALOGUE_DEMO")=="true" and settings.environment=="development"})

    @routes.post("/api/cbt-dialogue/start",dependencies=[Depends(require_csrf)])
    def start(participant=Depends(current_participant),db=Depends(get_db)):
        conversation,resumed=services.create_or_resume(db,participant.id)
        return {"id":conversation.id,"resumed":resumed,"url":f"/cbt-course/dialogue/{conversation.id}"}

    @routes.get("/cbt-course/dialogue/{conversation_id}",response_class=HTMLResponse)
    def conversation_page(conversation_id:str,request:Request,participant=Depends(current_participant),db=Depends(get_db)):
        conversation=get_owned(db,conversation_id,participant.id)
        return templates.TemplateResponse(request=request,name="cbt_course/dialogue.html",context={
            "conversation":services.payload(db,conversation),"consented":has_current_consent(db,participant.id),
            "lesson_version":services.LESSON_VERSION,"preview_kind":os.getenv('CBT_SINGLE_DIALOGUE_PREVIEW'),
            "history":[],"offline_demo":os.getenv("CBT_DIALOGUE_DEMO")=="true" and settings.environment=="development"})

    @routes.get("/api/cbt-dialogue/{conversation_id}")
    def get(conversation_id:str,request_key:str|None=Query(default=None,min_length=1,max_length=80),
            participant=Depends(current_participant),db=Depends(get_db)):
        return services.payload(db,get_owned(db,conversation_id,participant.id),request_key=request_key)

    @routes.post("/api/cbt-dialogue/{conversation_id}/messages",dependencies=[Depends(require_csrf)])
    def turn(conversation_id:str,payload:TurnInput,participant=Depends(current_participant),db=Depends(get_db)):
        get_owned(db,conversation_id,participant.id)
        if not has_current_consent(db,participant.id):raise HTTPException(403,"请先确认数据记录告知。")
        if len(payload.content)>settings.max_message_chars:raise HTTPException(413,"单条消息过长。")
        enforce_rate_limit(db,f"dialogue-message:{participant.id}")
        return services.process(db,participant_id=participant.id,conversation_id=conversation_id,**payload.model_dump())

    @routes.post("/api/cbt-dialogue/{conversation_id}/messages/stream",dependencies=[Depends(require_csrf)])
    def turn_stream(conversation_id:str,payload:TurnInput,participant=Depends(current_participant),db=Depends(get_db)):
        get_owned(db,conversation_id,participant.id)
        if not has_current_consent(db,participant.id):raise HTTPException(403)
        if len(payload.content)>settings.max_message_chars:raise HTTPException(413)
        enforce_rate_limit(db,f"dialogue-message:{participant.id}")
        from .streaming import stream_turn
        bind=db.get_bind();participant_id=participant.id
        async def events():
            disconnected=Event()
            iterator=stream_turn(session_factory=lambda:Session(bind=bind),participant_id=participant_id,
                    conversation_id=conversation_id,disconnect_event=disconnected,**payload.model_dump())
            try:
                while True:
                    item=await anyio.to_thread.run_sync(lambda:next(iterator,None),abandon_on_cancel=True)
                    if item is None:break
                    yield 'data: '+json.dumps(item,ensure_ascii=False)+'\n\n'
            finally:
                # Release backpressure immediately even if the browser disappears mid-frame.
                disconnected.set()
        return StreamingResponse(events(),media_type='text/event-stream',
            headers={'Cache-Control':'no-cache, no-transform','X-Accel-Buffering':'no'})

    app.include_router(routes)
