from __future__ import annotations

import asyncio
import base64
import json
import re
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote


_REGION_URLS = {
    "beijing": "wss://dashscope.aliyuncs.com/api-ws/v1/realtime",
    "singapore": "wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime",
}

_VOICE_IDENTITY = (
    "声音自然亲近、清楚可信，像熟悉的伙伴在近距离交流；"
    "短句自然停顿，不要播音腔、夹子音、过度幼态或夸张表演。"
)


@dataclass(frozen=True, slots=True)
class QwenTtsMetrics:
    connection_ms: float
    ttfa_ms: float
    total_ms: float
    audio_seconds: float
    characters: int | None


def voice_instruction_for(response_instructions: str) -> str:
    explicit = re.search(
        r"<TTS_DELIVERY>(.*?)</TTS_DELIVERY>",
        response_instructions,
        flags=re.DOTALL,
    )
    if explicit is not None:
        emotion = explicit.group(1).strip()
    elif "语速稍慢" in response_instructions:
        emotion = "此刻温暖轻柔，语速稍慢，音量柔和，停顿更充分，不要显得怜悯。"
    elif "降低信息密度" in response_instructions:
        emotion = "此刻贴近、安稳而确定，语速稍慢，每句话之间留出自然呼吸，不制造紧张感。"
    elif "不要争辩" in response_instructions:
        emotion = "此刻平稳克制、低刺激，不跟随对方提高音量，语气坚定但不冷淡。"
    elif "略带笑意" in response_instructions:
        emotion = "此刻明亮轻快，带自然笑意，语速略快，但不要尖锐或过分兴奋。"
    elif "积极情绪" in response_instructions:
        emotion = "此刻灵动开心，语调自然上扬，保持清楚，不要大喊或夸张表演。"
    elif "柔和稳定" in response_instructions:
        emotion = "此刻柔和稳定，像在用户身边轻声聊天，节奏舒展。"
    else:
        emotion = "此刻轻松自然，像熟悉的陪伴伙伴在近距离聊天。"
    return f"{_VOICE_IDENTITY}{emotion}"


class QwenRealtimeTtsSynthesizer:
    """Qwen3-TTS Realtime commit-mode client with per-turn connection reuse."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "qwen3-tts-instruct-flash-realtime",
        voice: str = "Cherry",
        region: str = "beijing",
        workspace_id: str | None = None,
        optimize_instructions: bool = False,
        connector: Callable[[str, dict[str, str]], Awaitable[Any]] | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("DashScope API key is required for Qwen TTS")
        if region not in _REGION_URLS:
            raise ValueError(f"unsupported Qwen TTS region: {region}")
        self.api_key = api_key
        self.model = model
        self.voice = voice
        self.region = region
        self.workspace_id = workspace_id
        self.optimize_instructions = optimize_instructions
        self._connector = connector
        self._socket: Any = None
        self._voice_instructions = ""
        self._connect_lock = asyncio.Lock()
        self._request_lock = asyncio.Lock()
        self._prepared_connection_ms = 0.0
        self.last_metrics: QwenTtsMetrics | None = None

    async def prepare(self, instructions: str) -> None:
        await self._ensure_session(voice_instruction_for(instructions))

    async def stream_pcm24k(
        self, text: str, *, instructions: str
    ) -> AsyncIterator[bytes]:
        if not text.strip():
            return
        voice_instructions = voice_instruction_for(instructions)
        async with self._request_lock:
            await self._ensure_session(voice_instructions)
            connection_ms = self._prepared_connection_ms
            self._prepared_connection_ms = 0.0
            started = time.perf_counter()
            first_audio_at: float | None = None
            audio_bytes = 0
            characters: int | None = None
            completed = False
            try:
                await self._send_event("input_text_buffer.append", text=text)
                await self._send_event("input_text_buffer.commit")
                while True:
                    event = await self._recv_json()
                    event_type = event.get("type")
                    if event_type == "response.audio.delta":
                        try:
                            pcm = base64.b64decode(event.get("delta", ""), validate=True)
                        except (ValueError, TypeError) as exc:
                            raise RuntimeError("Qwen TTS returned invalid base64 audio") from exc
                        if not pcm:
                            continue
                        if first_audio_at is None:
                            first_audio_at = time.perf_counter()
                        audio_bytes += len(pcm)
                        yield pcm
                    elif event_type == "response.done":
                        response = event.get("response") or {}
                        status = response.get("status")
                        if status != "completed":
                            raise RuntimeError(f"Qwen TTS response ended with status={status}")
                        usage = response.get("usage") or {}
                        raw_characters = usage.get("characters")
                        if isinstance(raw_characters, int):
                            characters = raw_characters
                        completed = True
                        break
                    elif event_type == "error":
                        self._raise_server_error(event)
            except asyncio.CancelledError:
                await self._drop_socket()
                raise
            except Exception:
                await self._drop_socket()
                raise
            finally:
                if completed:
                    finished = time.perf_counter()
                    self.last_metrics = QwenTtsMetrics(
                        connection_ms=round(connection_ms, 1),
                        ttfa_ms=round(
                            0.0
                            if first_audio_at is None
                            else (first_audio_at - started) * 1000,
                            1,
                        ),
                        total_ms=round((finished - started) * 1000, 1),
                        audio_seconds=round(audio_bytes / 48_000, 3),
                        characters=characters,
                    )

    async def close(self) -> None:
        socket = self._socket
        self._socket = None
        self._voice_instructions = ""
        if socket is None:
            return
        try:
            await self._send_json_to(socket, self._event("session.finish"))
            await asyncio.wait_for(socket.recv(), timeout=1)
        except Exception:
            pass
        finally:
            await socket.close()

    async def _ensure_session(self, voice_instructions: str) -> None:
        async with self._connect_lock:
            if self._socket is not None and voice_instructions == self._voice_instructions:
                return
            await self.close()
            started = time.perf_counter()
            try:
                self._socket = await self._open_socket()
                created = await self._recv_json()
                if created.get("type") == "error":
                    self._raise_server_error(created)
                if created.get("type") != "session.created":
                    raise RuntimeError(
                        f"Qwen TTS expected session.created, got {created.get('type')}"
                    )
                await self._send_event(
                    "session.update",
                    session={
                        "voice": self.voice,
                        "mode": "commit",
                        "language_type": "Chinese",
                        "response_format": "pcm",
                        "sample_rate": 24_000,
                        "instructions": voice_instructions,
                        "optimize_instructions": self.optimize_instructions,
                    },
                )
                updated = await self._recv_json()
                if updated.get("type") == "error":
                    self._raise_server_error(updated)
                if updated.get("type") != "session.updated":
                    raise RuntimeError(
                        f"Qwen TTS expected session.updated, got {updated.get('type')}"
                    )
            except BaseException:
                await self._drop_socket()
                raise
            self._voice_instructions = voice_instructions
            self._prepared_connection_ms = round(
                (time.perf_counter() - started) * 1000,
                1,
            )

    async def _open_socket(self) -> Any:
        base_url = _REGION_URLS[self.region]
        url = f"{base_url}?model={quote(self.model)}"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if self.workspace_id:
            headers["X-DashScope-WorkSpace"] = self.workspace_id
        if self._connector is not None:
            return await self._connector(url, headers)
        try:
            from websockets.asyncio.client import connect
        except ImportError as exc:  # pragma: no cover - base dependency
            raise RuntimeError("Install project dependencies before using Qwen TTS") from exc
        return await connect(
            url,
            additional_headers=headers,
            # DashScope's mainland endpoint is directly reachable.  Explicitly
            # bypass shell SOCKS/HTTP proxy variables to avoid an unnecessary
            # relay, optional python-socks dependency, and added TTS latency.
            proxy=None,
            open_timeout=20,
            close_timeout=3,
            ping_interval=20,
            ping_timeout=20,
            max_size=8 * 1024 * 1024,
            compression=None,
        )

    async def _send_event(self, event_type: str, **body: object) -> None:
        if self._socket is None:
            raise RuntimeError("Qwen TTS is not connected")
        await self._send_json_to(self._socket, self._event(event_type, **body))

    @staticmethod
    async def _send_json_to(socket: Any, event: dict[str, object]) -> None:
        await socket.send(json.dumps(event, ensure_ascii=False, separators=(",", ":")))

    @staticmethod
    def _event(event_type: str, **body: object) -> dict[str, object]:
        return {
            "event_id": f"event_{uuid.uuid4().hex}",
            "type": event_type,
            **body,
        }

    async def _recv_json(self) -> dict[str, Any]:
        if self._socket is None:
            raise RuntimeError("Qwen TTS is not connected")
        raw = await self._socket.recv()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            event = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RuntimeError("Qwen TTS returned malformed JSON") from exc
        if not isinstance(event, dict):
            raise RuntimeError("Qwen TTS returned a non-object event")
        return event

    async def _drop_socket(self) -> None:
        socket = self._socket
        self._socket = None
        self._voice_instructions = ""
        if socket is not None:
            await socket.close()

    @staticmethod
    def _raise_server_error(event: dict[str, Any]) -> None:
        error = event.get("error") or {}
        raise RuntimeError(
            f"Qwen TTS error {error.get('code', 'unknown')}: "
            f"{error.get('message', 'unknown error')}"
        )
