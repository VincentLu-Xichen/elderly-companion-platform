from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import case
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from webapp.config import settings
from webapp.models import RateLimitBucket


def _key_hash(key: str) -> str:
    return hmac.new(settings.app_secret.encode("utf-8"), key.encode("utf-8"), hashlib.sha256).hexdigest()


def _increment_bucket(db: Session, key_hash: str, now: datetime) -> int:
    expired_before = now - timedelta(minutes=1)
    dialect = db.get_bind().dialect.name
    insert_factory = postgresql_insert if dialect == "postgresql" else sqlite_insert if dialect == "sqlite" else None
    if insert_factory is None:
        bucket = db.get(RateLimitBucket, key_hash)
        if bucket is None:
            bucket = RateLimitBucket(key_hash=key_hash, window_started_at=now, request_count=1)
            db.add(bucket)
        elif bucket.window_started_at <= expired_before:
            bucket.window_started_at = now
            bucket.request_count = 1
        else:
            bucket.request_count += 1
        db.commit()
        return bucket.request_count

    statement = insert_factory(RateLimitBucket).values(
        key_hash=key_hash,
        window_started_at=now,
        request_count=1,
    )
    statement = statement.on_conflict_do_update(
        index_elements=[RateLimitBucket.key_hash],
        set_={
            "window_started_at": case(
                (RateLimitBucket.window_started_at <= expired_before, now),
                else_=RateLimitBucket.window_started_at,
            ),
            "request_count": case(
                (RateLimitBucket.window_started_at <= expired_before, 1),
                else_=RateLimitBucket.request_count + 1,
            ),
        },
    ).returning(RateLimitBucket.request_count)
    count = int(db.scalar(statement) or 0)
    db.commit()
    return count


def enforce_rate_limit(db: Session, key: str) -> None:
    if _increment_bucket(db, _key_hash(key), datetime.now(timezone.utc)) > settings.rate_limit_per_minute:
        raise HTTPException(status_code=429, detail="请求太频繁，请稍后再试。")
