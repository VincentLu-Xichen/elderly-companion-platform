from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool

from webapp.config import settings


class Base(DeclarativeBase):
    pass


def engine_options_for(database_url: str, pool_mode: str) -> dict:
    if database_url.startswith("sqlite"):
        return {"pool_pre_ping": True, "connect_args": {"check_same_thread": False}}
    if pool_mode == "transaction":
        return {
            "pool_pre_ping": True,
            "poolclass": NullPool,
            "connect_args": {"prepare_threshold": None},
        }
    return {"pool_pre_ping": True}


engine = create_engine(
    settings.database_url,
    **engine_options_for(settings.database_url, settings.database_pool_mode),
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_database() -> None:
    from webapp import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
