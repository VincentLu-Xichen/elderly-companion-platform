from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any, AsyncIterator
from urllib.parse import quote

from ..resampling import Pcm24kTo16k
from .base import ProviderEvent

logger = logging.getLogger(__name__)

_REGION_DOMAINS = {
    "beijing": "cn-beijing.maas.aliyuncs.com",
    "singapore": "ap-southeast-1.maas.aliyuncs.com",
}
_LEGACY_ENDPOINTS = {
    "beijing": "wss://dashscope.aliyuncs.com/api-ws/v1/realtime",
    "singapore": "wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime",
}


class QwenRealtimeProvider:
    """Adapter for Alibaba Cloud Model Studio Qwen-Omni Realtime WebSocket."""

    manual_audio_commit = True

    def __init__(
        self,
        *,
        api_key: str,
        workspace_id: str,
        region: str,
        model: str,
        voice: str,
        instructions: str,
    ) -> None:
        if region not in _REGION_DOMAINS:
            raise ValueError(f"unsupported Qwen region: {region}")
        self.api_key = api_key
        self.workspace_id = workspace_id
        self.region = region
        self.model = model
        self.voice = voice
        self.instructions = instructions
        self._socket: Any = None
        self._send_lock = asyncio.Lock()
        self._resampler = Pcm24kTo16k()

    async def connect(self) -> None:
        try:
            from websockets.asyncio.client import connect
            from websockets.exceptions import InvalidStatus
        except ImportError as exc:  # pragma: no cover - deployment setup
            raise RuntimeError("Install project dependencies before using Qwen Realtime") from exc

        dedicated_url, legacy_url = self._endpoint_urls()
        try:
            self._socket = await self._open_socket(connect, dedicated_url)
        except InvalidStatus as exc:
            if not self._is_invalid_workspace_response(exc.response):
                raise
            logger.warning(
                "Qwen workspace endpoint is invalid; using the official "
                "regional compatibility endpoint"
            )
            self._socket = await self._open_socket(connect, legacy_url)
        await self._send_json(self._session_update(self.instructions, full=True))

    def _endpoint_urls(self) -> tuple[str, str]:
        domain = _REGION_DOMAINS[self.region]
        query = f"?model={quote(self.model)}"
        dedicated = (
            f"wss://{self.workspace_id}.{domain}/api-ws/v1/realtime"
            f"{query}"
        )
        return dedicated, f"{_LEGACY_ENDPOINTS[self.region]}{query}"

    async def _open_socket(self, connect: Any, url: str) -> Any:
        return await connect(
            url,
            additional_headers=self._connection_headers(),
            open_timeout=10,
            close_timeout=3,
            ping_interval=20,
            ping_timeout=20,
            max_size=8 * 1024 * 1024,
            compression=None,
        )

    @staticmethod
    def _is_invalid_workspace_response(response: Any) -> bool:
        body = getattr(response, "body", b"") or b""
        if isinstance(body, str):
            body = body.encode()
        return (
            getattr(response, "status_code", None) == 400
            and b"BadRequest.IllegalEndpoint" in body
        )

    def _connection_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1",
        }

    async def send_audio(self, pcm: bytes) -> None:
        converted = self._resampler.process(pcm)
        if converted:
            await self._append_audio(converted)

    async def finish_audio_turn(self) -> None:
        tail = self._resampler.process(b"", final=True)
        if tail:
            await self._append_audio(tail)
        await self._send_json({"type": "input_audio_buffer.commit"})

    async def cancel(
        self, *, item_id: str | None, played_ms: int, cancel_response: bool = True
    ) -> None:
        # Qwen currently supports response.cancel but not audio-item truncation.
        if cancel_response:
            await self._send_json({"type": "response.cancel"})

    async def update_instructions(self, instructions: str) -> None:
        if instructions == self.instructions:
            return
        self.instructions = instructions
        await self._send_json(self._session_update(instructions, full=False))

    async def create_response(self, instructions: str) -> None:
        # Per-response instructions are not part of Qwen's response.create
        # shape; update_instructions is intentionally called first by Session.
        await self._send_json({"type": "response.create"})

    async def events(self) -> AsyncIterator[ProviderEvent]:
        if self._socket is None:
            raise RuntimeError("provider is not connected")
        async for raw in self._socket:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            try:
                event = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError):
                logger.warning("Ignoring malformed Qwen Realtime event")
                continue
            mapped = self._map_event(event)
            if mapped is not None:
                yield mapped

    async def close(self) -> None:
        self._resampler.reset()
        if self._socket is not None:
            await self._socket.close()
            self._socket = None

    def _session_update(self, instructions: str, *, full: bool) -> dict[str, Any]:
        session: dict[str, Any] = {"instructions": instructions}
        if full:
            session.update(
                {
                    "modalities": ["text", "audio"],
                    "voice": self.voice,
                    "input_audio_format": "pcm",
                    "output_audio_format": "pcm",
                    # Local VAD must commit the turn so local emotion2vec can
                    # shape the current response before generation begins.
                    "turn_detection": None,
                    "max_tokens": 900,
                    "temperature": 0.7,
                }
            )
        return {"type": "session.update", "session": session}

    async def _append_audio(self, pcm16_16k: bytes) -> None:
        await self._send_json(
            {
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(pcm16_16k).decode("ascii"),
            }
        )

    async def _send_json(self, event: dict[str, Any]) -> None:
        if self._socket is None:
            raise RuntimeError("provider is not connected")
        payload = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        async with self._send_lock:
            await self._socket.send(payload)

    @staticmethod
    def _map_event(event: dict[str, Any]) -> ProviderEvent | None:
        event_type = event.get("type", "")
        if event_type == "response.audio.delta":
            try:
                audio = base64.b64decode(event.get("delta", ""), validate=True)
            except (ValueError, TypeError):
                return ProviderEvent("error", text="invalid audio delta", data=event)
            return ProviderEvent(
                "audio.delta",
                audio=audio,
                item_id=event.get("item_id"),
                data={"response_id": event.get("response_id")},
            )
        if event_type == "conversation.item.input_audio_transcription.delta":
            text = f'{event.get("text", "")}{event.get("stash", "")}'
            return ProviderEvent(
                "user.transcript",
                text=text,
                item_id=event.get("item_id"),
                data={
                    "final": False,
                    "provider_emotion": event.get("emotion"),
                    "language": event.get("language"),
                },
            )
        if event_type == "conversation.item.input_audio_transcription.completed":
            return ProviderEvent(
                "user.transcript",
                text=event.get("transcript", ""),
                item_id=event.get("item_id"),
                data={
                    "final": True,
                    "provider_emotion": event.get("emotion"),
                    "language": event.get("language"),
                },
            )
        if event_type == "response.audio_transcript.delta":
            return ProviderEvent(
                "assistant.transcript.delta",
                text=event.get("delta", ""),
                item_id=event.get("item_id"),
            )
        if event_type == "response.audio_transcript.done":
            return ProviderEvent(
                "assistant.transcript.done",
                text=event.get("transcript", ""),
                item_id=event.get("item_id"),
            )
        if event_type == "input_audio_buffer.speech_started":
            return ProviderEvent("speech.started", item_id=event.get("item_id"), data=event)
        if event_type == "input_audio_buffer.speech_stopped":
            return ProviderEvent("speech.stopped", item_id=event.get("item_id"), data=event)
        if event_type == "response.created":
            response = event.get("response") or {}
            return ProviderEvent(
                "response.started",
                data={"response_id": response.get("id"), "raw": event},
            )
        if event_type in {"response.done", "response.cancelled"}:
            response = event.get("response") or {}
            return ProviderEvent(
                "response.done",
                data={
                    "status": response.get("status", "done"),
                    "response_id": response.get("id") or event.get("response_id"),
                    "usage": response.get("usage"),
                    "raw": event,
                },
            )
        if event_type == "error":
            error = event.get("error") or {}
            return ProviderEvent(
                "error",
                text=error.get("message", "Qwen Realtime provider error"),
                data={"code": error.get("code"), "raw": event},
            )
        if event_type in {"session.created", "session.updated"}:
            return ProviderEvent(event_type, data=event)
        return None
