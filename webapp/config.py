"""Values are set by run.py; never search parent directories for an .env file."""
import os
from dataclasses import dataclass

@dataclass(frozen=True)
class Settings:
    database_url:str=os.getenv('DATABASE_URL','sqlite://')
    database_pool_mode:str='application'
    app_secret:str=os.getenv('APP_SECRET','test-only-not-for-running-server')
    data_encryption_key:str=os.getenv('DATA_ENCRYPTION_KEY','')
    invite_codes:str=os.getenv('INVITE_CODES','tester-1:course-pilot,tester-2:course-eval,tester-3:course-003')
    consent_version:str=os.getenv('CONSENT_VERSION','lesson1-package-2026-11-v1')
    cookie_secure:bool=False
    session_hours:int=12
    max_message_chars:int=2000
    rate_limit_per_minute:int=30
    environment:str=os.getenv('APP_ENV','development')

settings=Settings()
