from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class InviteLogin(BaseModel):
    code: str = Field(min_length=3, max_length=200)


class ConsentInput(BaseModel):
    agreed: bool


class ConversationCreate(BaseModel):
    mode: Literal["daily_chat", "cbt"]


class MessageCreate(BaseModel):
    content: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=8, max_length=80)


class AdminLogin(BaseModel):
    password: str = Field(min_length=1, max_length=300)
