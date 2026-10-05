"""Persistent Daily Chat bridge client for the local Agent service."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any
from ..contracts import EmotionSnapshot


class AgentBridgeChatClient:
    """Adapt the Agent's persistent turn API to the ESDS chat interface."""

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        device_id: str,
        timeout_seconds: float = 65.0,
        transport: Any = None,
    ) -> None:
        if not base_url.strip():
            raise ValueError("Agent bridge base URL is required")
        if not token.strip():
            raise ValueError("Agent bridge token is required")
        if not device_id.strip():
            raise ValueError("Agent bridge device ID is required")
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.device_id = device_id
        self.timeout_seconds = timeout_seconds
        self.transport = transport
        self._client: Any = None
        self._conversation_id = ""
        self._open_lock = asyncio.Lock()

    async def warmup(self) -> None:
        client = self._http_client()
        response = await client.get("/internal/voice/v1/healthz")
        self._raise_for_status(response, "health check")
        await self._open_session(force=True)

    async def stream_reply(
        self,
        messages: list[dict[str, str]],
    ) -> AsyncIterator[str]:
        async for part in self._stream_reply_json(messages, None):
            yield part

    async def stream_reply_with_emotion(
        self, messages: list[dict[str, str]], emotion: EmotionSnapshot | None,
    ) -> AsyncIterator[str]:
        user_text = self._user_text(messages)
        if not user_text:
            raise RuntimeError("Agent bridge received no user transcript")
        if not self._conversation_id:
            await self._open_session()
        idempotency_key = f"voice-{uuid.uuid4().hex}"
        path = f"/internal/voice/v1/sessions/{self._conversation_id}/turns/stream"
        body = self._turn_body(user_text, idempotency_key, emotion)
        client = self._http_client()
        for attempt in range(2):
            retry = False
            async with client.stream(
                "POST",
                path,
                json=body,
                headers={"Accept": "text/event-stream"},
            ) as response:
                if response.status_code == 404 and attempt == 0:
                    retry = True
                else:
                    self._raise_for_status(response, "stream turn")
                    saw_done = False
                    saw_text = False
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        try:
                            event = json.loads(line[5:].strip())
                        except (TypeError, json.JSONDecodeError):
                            continue
                        if not isinstance(event, dict):
                            continue
                        event_type = event.get("type")
                        if event_type == "delta":
                            text = event.get("text")
                            if isinstance(text, str) and text:
                                saw_text = True
                                yield text
                        elif event_type == "error":
                            raise RuntimeError(
                                str(event.get("detail") or "Agent bridge stream failed")
                            )
                        elif event_type == "done":
                            saw_done = True
                    if not saw_done or not saw_text:
                        raise RuntimeError("Agent bridge stream ended before a complete reply")
                    return
            if retry:
                await self._open_session(force=True)
                path = f"/internal/voice/v1/sessions/{self._conversation_id}/turns/stream"
        raise RuntimeError("Agent bridge stream could not be opened")

    async def _stream_reply_json(
        self, messages: list[dict[str, str]], emotion: EmotionSnapshot | None,
    ) -> AsyncIterator[str]:
        user_text = self._user_text(messages)
        if not user_text:
            raise RuntimeError("Agent bridge received no user transcript")
        if not self._conversation_id:
            await self._open_session()
        idempotency_key = f"voice-{uuid.uuid4().hex}"
        response = await self._post_turn(user_text, idempotency_key, emotion=emotion)
        if response.status_code == 404:
            await self._open_session(force=True)
            response = await self._post_turn(user_text, idempotency_key, emotion=emotion)
        self._raise_for_status(response, "turn")
        payload = response.json()
        reply = payload.get("reply") if isinstance(payload, dict) else None
        if not isinstance(reply, str) or not reply.strip():
            raise RuntimeError("Agent bridge returned an empty reply")
        yield reply.strip()

    @staticmethod
    def _user_text(messages: list[dict[str, str]]) -> str:
        user_text = next(
            (
                str(message.get("content") or "").strip()
                for message in reversed(messages)
                if message.get("role") == "user"
            ),
            "",
        )
        return user_text

    @staticmethod
    def _turn_body(
        transcript: str, idempotency_key: str, emotion: EmotionSnapshot | None,
    ) -> dict[str, Any]:
        return {
            "transcript": transcript,
            "idempotency_key": idempotency_key,
            **({"emotion": {
                "label": emotion.label, "confidence": emotion.confidence,
                "evidence": list(emotion.evidence[:8]),
            }} if emotion is not None else {}),
        }

    async def close(self) -> None:
        client = self._client
        self._client = None
        self._conversation_id = ""
        if client is not None:
            await client.aclose()

    async def _open_session(self, *, force: bool = False) -> None:
        async with self._open_lock:
            if self._conversation_id and not force:
                return
            response = await self._http_client().post(
                "/internal/voice/v1/sessions/open",
                json={
                    "device_id": self.device_id,
                    "preferred_mode": "daily_chat",
                },
            )
            self._raise_for_status(response, "session open")
            payload = response.json()
            conversation_id = (
                payload.get("conversation_id")
                if isinstance(payload, dict)
                else None
            )
            if not isinstance(conversation_id, str) or not conversation_id:
                raise RuntimeError(
                    "Agent bridge session response has no conversation ID"
                )
            self._conversation_id = conversation_id

    async def _post_turn(
        self, transcript: str, idempotency_key: str, *, emotion: EmotionSnapshot | None = None,
    ) -> Any:
        return await self._http_client().post(
            f"/internal/voice/v1/sessions/{self._conversation_id}/turns",
            json=self._turn_body(transcript, idempotency_key, emotion),
        )

    def _http_client(self) -> Any:
        if self._client is None:
            try:
                import httpx
            except ImportError as exc:  # pragma: no cover - base dependency
                raise RuntimeError("httpx is required for Agent bridge") from exc
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=httpx.Timeout(self.timeout_seconds, connect=5.0),
                transport=self.transport,
            )
        return self._client

    @staticmethod
    def _raise_for_status(response: Any, operation: str) -> None:
        if 200 <= response.status_code < 300:
            return
        raise RuntimeError(
            f"Agent bridge {operation} failed with HTTP {response.status_code}"
        )


class CbtAgentBridgeChatClient(AgentBridgeChatClient):
    """Persistent CBT lesson bridge using the existing voice HTTP auth."""

    def __init__(self, *, lesson_id: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.lesson_id = lesson_id

    async def stream_reply_with_emotion(
        self, messages: list[dict[str, str]], emotion: EmotionSnapshot | None,
    ) -> AsyncIterator[str]:
        # The CBT bridge keeps its existing non-streaming course contract.
        async for part in self._stream_reply_json(messages, None):
            yield part

    async def _open_session(self, *, force: bool = False) -> None:
        async with self._open_lock:
            if self._conversation_id and not force:
                return
            response = await self._http_client().post(
                "/internal/voice/v1/cbt/sessions/open",
                json={"device_id": self.device_id, "lesson_id": self.lesson_id},
            )
            self._raise_for_status(response, "CBT session open")
            payload = response.json()
            conversation_id = payload.get("conversation_id") if isinstance(payload, dict) else None
            if not isinstance(conversation_id, str) or not conversation_id:
                raise RuntimeError("CBT bridge session response has no conversation ID")
            self._conversation_id = conversation_id

    async def _post_turn(
        self, transcript: str, idempotency_key: str, *, emotion: EmotionSnapshot | None = None,
    ) -> Any:
        # CBT retains its separate, text-only course contract.
        return await self._http_client().post(
            f"/internal/voice/v1/cbt/sessions/{self._conversation_id}/turns",
            json={"transcript": transcript, "idempotency_key": idempotency_key},
        )
