from __future__ import annotations

import asyncio
import base64
import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import quote

from .contracts import AsrResult
from .resampling import Pcm24kTo16k

TranscriptionResult = AsrResult


_QWEN_ASR_REGION_URLS = {
    "beijing": "wss://dashscope.aliyuncs.com/api-ws/v1/realtime",
    "singapore": "wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime",
}

_QWEN_ASR_WORKSPACE_URLS = {
    "beijing": "wss://{workspace_id}.cn-beijing.maas.aliyuncs.com/api-ws/v1/realtime",
    "singapore": (
        "wss://{workspace_id}.ap-southeast-1.maas.aliyuncs.com/api-ws/v1/realtime"
    ),
}


def _strip_sensevoice_tag(value: str) -> str:
    return value.strip().removeprefix("<|").removesuffix("|>")


class SenseVoiceTranscriber:
    """Free local utterance ASR backed by SenseVoice int8 and sherpa-onnx."""

    def __init__(self, model_dir: str | Path, *, num_threads: int = 2) -> None:
        root = Path(model_dir).expanduser().resolve()
        model = root / "model.int8.onnx"
        if not model.is_file():
            model = root / "model.onnx"
        tokens = root / "tokens.txt"
        if not model.is_file() or not tokens.is_file():
            raise ValueError(
                "SenseVoice ASR directory must contain model.int8.onnx/model.onnx "
                f"and tokens.txt: {root}"
            )
        self.model_path = model
        self.tokens_path = tokens
        self.num_threads = max(1, num_threads)
        self._recognizer: Any = None
        self._lock = threading.Lock()

    def _get_recognizer(self):
        if self._recognizer is None:
            try:
                import sherpa_onnx
            except ImportError as exc:  # pragma: no cover - optional extra
                raise RuntimeError(
                    "Install local speech dependencies: pip install -e '.[local-speech]'"
                ) from exc
            self._recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
                model=str(self.model_path),
                tokens=str(self.tokens_path),
                num_threads=self.num_threads,
                use_itn=True,
            )
        return self._recognizer

    def warmup(self) -> None:
        with self._lock:
            self._get_recognizer()

    def transcribe_pcm16(
        self, pcm: bytes, sample_rate: int
    ) -> TranscriptionResult | None:
        if not pcm or len(pcm) % 2 or sample_rate <= 0:
            return None
        try:
            import numpy as np
        except ImportError as exc:  # pragma: no cover - optional extra
            raise RuntimeError(
                "Install local speech dependencies: pip install -e '.[local-speech]'"
            ) from exc

        samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
        started = time.perf_counter()
        with self._lock:
            recognizer = self._get_recognizer()
            stream = recognizer.create_stream()
            stream.accept_waveform(sample_rate, samples)
            recognizer.decode_stream(stream)
            result = stream.result
        latency_ms = (time.perf_counter() - started) * 1000
        text = str(getattr(result, "text", "") or "").strip()
        if not text:
            return None
        return TranscriptionResult(
            text=text,
            language=_strip_sensevoice_tag(str(getattr(result, "lang", "") or "")),
            event=_strip_sensevoice_tag(str(getattr(result, "event", "") or "")),
            latency_ms=latency_ms,
        )


class QwenRealtimeTranscriber:
    """Low-latency Qwen3-ASR client using one warm WebSocket per device session.

    The browser sends 24 kHz PCM to the gateway. Qwen3-ASR currently accepts
    8/16 kHz PCM, so audio is resampled continuously to 16 kHz before upload.
    Manual commit mode keeps the project's noise-aware local VAD as the single
    source of utterance boundaries.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "qwen3-asr-flash-realtime",
        region: str = "beijing",
        workspace_id: str | None = None,
        language: str = "zh",
        context: str = "",
        timeout_seconds: float = 8.0,
        connector: Callable[[str, dict[str, str]], Awaitable[Any]] | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("DashScope API key is required for Qwen ASR")
        if region not in _QWEN_ASR_REGION_URLS:
            raise ValueError(f"unsupported Qwen ASR region: {region}")
        if timeout_seconds <= 0:
            raise ValueError("Qwen ASR timeout must be positive")
        self.api_key = api_key
        self.model = model
        self.region = region
        self.workspace_id = workspace_id
        self.language = language
        self.context = context.strip()
        self.timeout_seconds = timeout_seconds
        self._connector = connector
        self._socket: Any = None
        self._connect_lock = asyncio.Lock()
        self._stream_started = False
        self._source_sample_rate = 0
        self._resampler: Pcm24kTo16k | None = None

    async def warmup(self) -> None:
        await self._ensure_session()

    async def start_stream(self, sample_rate: int) -> None:
        if sample_rate not in {16_000, 24_000}:
            raise ValueError("Qwen ASR PCM sample_rate must be 16000 or 24000")
        if self._stream_started:
            raise RuntimeError("Qwen ASR stream is already active")
        await self._ensure_session()
        self._source_sample_rate = sample_rate
        self._resampler = Pcm24kTo16k() if sample_rate == 24_000 else None
        self._stream_started = True

    async def send_stream_audio(self, pcm: bytes) -> None:
        if not self._stream_started:
            raise RuntimeError("Qwen ASR stream has not started")
        if not pcm or len(pcm) % 2:
            return
        converted = self._resample(pcm)
        if not converted:
            return
        await self._send_event(
            "input_audio_buffer.append",
            audio=base64.b64encode(converted).decode("ascii"),
        )

    async def finish_stream(self) -> TranscriptionResult | None:
        if not self._stream_started:
            return None
        self._stream_started = False
        started = time.perf_counter()
        try:
            if self._resampler is not None:
                tail = self._resampler.process(b"", final=True)
                if tail:
                    await self._send_event(
                        "input_audio_buffer.append",
                        audio=base64.b64encode(tail).decode("ascii"),
                    )
            await self._send_event("input_audio_buffer.commit")
            while True:
                event = await asyncio.wait_for(
                    self._recv_json(),
                    timeout=self.timeout_seconds,
                )
                event_type = event.get("type")
                if event_type == "conversation.item.input_audio_transcription.completed":
                    text = str(event.get("transcript") or "").strip()
                    if not text:
                        return None
                    return TranscriptionResult(
                        text=text,
                        language=str(event.get("language") or self.language),
                        event=str(event.get("emotion") or ""),
                        latency_ms=(time.perf_counter() - started) * 1000,
                    )
                if event_type == "conversation.item.input_audio_transcription.failed":
                    self._raise_server_error(event)
                if event_type == "error":
                    self._raise_server_error(event)
        except BaseException:
            await self._drop_socket()
            raise
        finally:
            self._source_sample_rate = 0
            self._resampler = None

    async def close(self) -> None:
        socket = self._socket
        self._socket = None
        self._stream_started = False
        self._source_sample_rate = 0
        self._resampler = None
        if socket is None:
            return
        try:
            await self._send_json_to(socket, self._event("session.finish"))
            await asyncio.wait_for(socket.recv(), timeout=1)
        except Exception:
            pass
        finally:
            await socket.close()

    def _resample(self, pcm: bytes) -> bytes:
        if self._resampler is None:
            return pcm
        return self._resampler.process(pcm)

    async def _ensure_session(self) -> None:
        async with self._connect_lock:
            if self._socket is not None:
                if getattr(self._socket, "close_code", None) is None:
                    return
                await self._drop_socket()
            try:
                self._socket = await self._open_socket()
                created = await self._recv_json()
                if created.get("type") == "error":
                    self._raise_server_error(created)
                if created.get("type") != "session.created":
                    raise RuntimeError(
                        "Qwen ASR expected session.created, "
                        f"got {created.get('type')}"
                    )
                transcription: dict[str, object] = {"language": self.language}
                if self.context:
                    transcription["corpus"] = {"text": self.context}
                await self._send_event(
                    "session.update",
                    session={
                        "modalities": ["text"],
                        "input_audio_format": "pcm",
                        "sample_rate": 16_000,
                        "input_audio_transcription": transcription,
                        "turn_detection": None,
                    },
                )
                updated = await self._recv_json()
                if updated.get("type") == "error":
                    self._raise_server_error(updated)
                if updated.get("type") != "session.updated":
                    raise RuntimeError(
                        "Qwen ASR expected session.updated, "
                        f"got {updated.get('type')}"
                    )
            except BaseException:
                await self._drop_socket()
                raise

    async def _open_socket(self) -> Any:
        if self.workspace_id:
            base_url = _QWEN_ASR_WORKSPACE_URLS[self.region].format(
                workspace_id=self.workspace_id
            )
        else:
            base_url = _QWEN_ASR_REGION_URLS[self.region]
        url = f"{base_url}?model={quote(self.model)}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1",
        }
        if self._connector is not None:
            return await self._connector(url, headers)
        try:
            from websockets.asyncio.client import connect
        except ImportError as exc:  # pragma: no cover - base dependency
            raise RuntimeError("Install project dependencies before using Qwen ASR") from exc
        return await connect(
            url,
            additional_headers=headers,
            proxy=None,
            open_timeout=10,
            close_timeout=3,
            ping_interval=20,
            ping_timeout=20,
            max_size=2 * 1024 * 1024,
            max_queue=512,
            compression=None,
        )

    async def _send_event(self, event_type: str, **body: object) -> None:
        if self._socket is None:
            raise RuntimeError("Qwen ASR is not connected")
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
            raise RuntimeError("Qwen ASR is not connected")
        raw = await self._socket.recv()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            event = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RuntimeError("Qwen ASR returned malformed JSON") from exc
        if not isinstance(event, dict):
            raise RuntimeError("Qwen ASR returned a non-object event")
        return event

    async def _drop_socket(self) -> None:
        socket = self._socket
        self._socket = None
        if socket is not None:
            await socket.close()

    @staticmethod
    def _raise_server_error(event: dict[str, Any]) -> None:
        error = event.get("error") or {}
        raise RuntimeError(
            f"Qwen ASR error {error.get('code', 'unknown')}: "
            f"{error.get('message', 'unknown error')}"
        )
