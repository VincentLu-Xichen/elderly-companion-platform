"""The package exposes login, consent and current lesson-one routes only."""
from datetime import datetime,timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import Depends,FastAPI,Header,HTTPException,Request
from fastapi.responses import HTMLResponse,JSONResponse,RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy.orm import Session

from lesson1_dialogue.router import register_dialogue_routes
from lesson1_dialogue.services import LESSON_VERSION
from webapp.config import settings
from webapp.database import SessionLocal,init_database
from webapp.models import Participant
from webapp.rate_limit import enforce_rate_limit
from webapp.security import csrf_matches,new_csrf_token,sign_session,verify_session
from webapp.services import authenticate_invite,bootstrap_invites,has_current_consent,record_consent

BASE=Path(__file__).resolve().parent
app=FastAPI(title='第一课独立测试',docs_url=None,redoc_url=None)
app.mount('/static',StaticFiles(directory=BASE/'static'),name='static')
templates=Jinja2Templates(directory=BASE/'templates')

def utc8(value):
    if value is None:return ''
    v=datetime.fromisoformat(value) if isinstance(value,str) else value
    if v.tzinfo is None:v=v.replace(tzinfo=timezone.utc)
    return v.astimezone(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M')
templates.env.filters['utc8']=utc8

@app.on_event('startup')
def startup():
    if settings.app_secret=='test-only-not-for-running-server':
        raise RuntimeError('请通过python run.py启动，避免缺少持久化密钥。')
    init_database()
    with SessionLocal() as db:bootstrap_invites(db)

def get_db():
    with SessionLocal() as db:yield db

def current_participant(request:Request,db:Session=Depends(get_db)):
    pid=verify_session(request.cookies.get('participant_session'),'participant')
    p=db.get(Participant,pid) if pid else None
    if p is None or not p.is_active:raise HTTPException(401,'请先使用邀请码登录。')
    return p

def require_csrf(request:Request,x_csrf_token:Optional[str]=Header(default=None)):
    if not csrf_matches(request.cookies.get('csrf_token'),x_csrf_token):raise HTTPException(403,'安全校验失败，请刷新后重试。')

@app.get('/healthz')
def health():return {'ok':True,'lesson_version':LESSON_VERSION}

@app.get('/',response_class=HTMLResponse)
def login_page(request:Request):return templates.TemplateResponse(request=request,name='entry.html',context={'participant':None,'consented':False,'version':LESSON_VERSION})

@app.get('/app',response_class=HTMLResponse)
def home(request:Request,db:Session=Depends(get_db)):
    pid=verify_session(request.cookies.get('participant_session'),'participant');p=db.get(Participant,pid) if pid else None
    if p is None or not p.is_active:return RedirectResponse('/',status_code=303)
    return templates.TemplateResponse(request=request,name='entry.html',context={'participant':p,'consented':has_current_consent(db,p.id),'version':LESSON_VERSION})

@app.get('/cbt-course')
def first_lesson():return RedirectResponse('/cbt-course/dialogue',status_code=303)

class Login(BaseModel):
    model_config=ConfigDict(extra='forbid')
    code:str=Field(min_length=1,max_length=100)

class ConsentBody(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    agreed:bool

@app.post('/api/session/invite')
def login(body:Login,request:Request,db:Session=Depends(get_db)):
    enforce_rate_limit(db,'invite:'+(request.client.host if request.client else 'local'))
    p=authenticate_invite(db,body.code)
    if p is None:raise HTTPException(401,'邀请码无效或已停用。')
    response=JSONResponse({'ok':True})
    response.set_cookie('participant_session',sign_session('participant',p.id),httponly=True,secure=False,samesite='strict',max_age=settings.session_hours*3600)
    response.set_cookie('csrf_token',new_csrf_token(),httponly=False,secure=False,samesite='strict',max_age=settings.session_hours*3600)
    return response

@app.post('/api/session/logout',dependencies=[Depends(require_csrf)])
def logout(p=Depends(current_participant)):
    response=JSONResponse({'ok':True});response.delete_cookie('participant_session');response.delete_cookie('csrf_token');return response

@app.post('/api/consents',dependencies=[Depends(require_csrf)])
def consent(body:ConsentBody,p=Depends(current_participant),db:Session=Depends(get_db)):
    if not body.agreed:raise HTTPException(400,'请先确认数据记录告知。')
    record_consent(db,p.id);return {'ok':True}

register_dialogue_routes(app,get_db=get_db,current_participant=current_participant,require_csrf=require_csrf,templates=templates)
