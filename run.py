"""Run the current first lesson locally with DeepSeek and persistent encrypted data."""
import argparse
import json
import os
from pathlib import Path
import secrets
import sys

ROOT=Path(__file__).resolve().parent


def prepare():
    from dotenv import dotenv_values
    values=dotenv_values(ROOT/'.env') if (ROOT/'.env').is_file() else {}
    key=(values.get('DEEPSEEK_API_KEY') or '').strip()
    if not key or key in {'replace-me','your-api-key-here'}:
        raise ValueError('请先复制.env.example为.env，并填写DEEPSEEK_API_KEY。')
    data=ROOT/'data';data.mkdir(exist_ok=True,mode=0o700)
    secret_file=data/'local-secrets.json'
    if secret_file.exists():
        private=json.loads(secret_file.read_text(encoding='utf-8'))
        if private.get('mode')!='live':raise ValueError('请使用本最小包自己的数据目录。')
    else:
        if (data/'lesson1.db').exists():raise ValueError('已有数据库缺少恢复密钥，请恢复原local-secrets.json。')
        private={'mode':'live','app_secret':secrets.token_urlsafe(32)}
        descriptor=os.open(secret_file,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(descriptor,'w',encoding='utf-8') as f:json.dump(private,f)
    if not private.get('app_secret'):raise ValueError('本地恢复密钥不完整。')
    for name in list(os.environ):
        if any(marker in name for marker in ('API_KEY','TOKEN','DATABASE_URL','POSTGRES','ENCRYPTION_KEY')) or name.startswith('CBT_'):
            os.environ.pop(name,None)
        elif name in {'HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy'}:
            os.environ.pop(name,None)
    os.environ.update(PYTHON_DOTENV_DISABLED='1',APP_ENV='development',APP_SECRET=private['app_secret'],
        DATA_ENCRYPTION_KEY='',DATABASE_URL='sqlite:///'+str(data/'lesson1.db'),
        INVITE_CODES=values.get('INVITE_CODES') or 'tester-1:course-pilot,tester-2:course-eval,tester-3:course-003',
        COOKIE_SECURE='false',CONSENT_VERSION='lesson1-package-2026-11-v1',
        CBT_COURSE_PROVIDER='deepseek',CBT_COURSE_MODEL=values.get('CBT_COURSE_MODEL') or 'deepseek-flash',
        DEEPSEEK_API_KEY=key,CBT_SINGLE_DIALOGUE_PREVIEW='live',CBT_PREVIEW_MODE='false',CBT_DIALOGUE_DEMO='false')
    return data


def main():
    p=argparse.ArgumentParser(description='第一课9.16最小运行入口（真实对话）')
    p.add_argument('--port',type=int,default=8080)
    p.add_argument('--check',action='store_true',help='只检查配置，不调用模型')
    args=p.parse_args()
    if not (3,11)<=sys.version_info[:2]<(3,14):p.error('请先运行python3 setup_env.py，再使用.venv中的Python启动。')
    if not 1<=args.port<=65535:p.error('端口须为1—65535。')
    os.chdir(ROOT)
    try:data=prepare()
    except (ValueError,OSError) as error:p.error(str(error))
    from lesson1_dialogue.services import LESSON_VERSION
    url=f'http://127.0.0.1:{args.port}/'
    if args.check:
        print(json.dumps({'configuration':'ready','version':LESSON_VERSION,'mode':'live','url':url,
                         'data_directory':str(data),'model_calls':0},ensure_ascii=False));return
    print(f'第一课 {LESSON_VERSION} | {url}\n邀请码：course-pilot；Ctrl+C停止，同目录重启保留记录。',flush=True)
    import uvicorn
    uvicorn.run('webapp.main:app',host='127.0.0.1',port=args.port,log_level='warning')


if __name__=='__main__':main()
