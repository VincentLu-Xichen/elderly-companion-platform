from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .audio import pcm16_features
from .config import Settings
from .contracts import EmotionSnapshot
from .emotion import EmotionTracker
from .emotion_backends import DisabledEmotionAnalyzer, EmotionAnalyzer
from .enhance import create_speech_enhancer
from .policy import provider_instructions
from .protocol import DeviceHello, ProtocolError, event_json, parse_control, safe_error
from .providers.base import ProviderEvent, RealtimeProvider
from .transcript_guard import unreliable_transcript_reason
from .vad import EnergyVad

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _AudioFrame:
    turn: int
    pcm: bytes


@dataclass(frozen=True, slots=True)
class _AudioCommit:
    turn: int


class SessionState(StrEnum):
    LISTENING = "listening"
    USER_SPEAKING = "user_speaking"
    PROCESSING = "processing"
    ASSISTANT_SPEAKING = "assistant_speaking"
    INTERRUPTING = "interrupting"


class DeviceSession:
    """Voice-only session coordinator.

    It deliberately excludes camera, presence, praise and visual-context events.
    The first migration runs half-duplex: microphone audio is ignored while a
    response is being generated or played, which is the safest Raspberry Pi
    baseline before device AEC and semantic barge-in are validated.
    """

    def __init__(
        self,
        *,
        socket: Any,
        hello: DeviceHello,
        provider: RealtimeProvider,
        settings: Settings,
        emotion_analyzer: EmotionAnalyzer | None = None,
    ) -> None:
        self.socket = socket
        self.hello = hello
        self.provider = provider
        self.settings = settings
        self.emotion_analyzer = emotion_analyzer or DisabledEmotionAnalyzer()
        self.session_id = uuid.uuid4().hex
        self.state = SessionState.LISTENING
        self.emotion = EmotionTracker()
        self.vad = EnergyVad(
            start_dbfs=settings.vad_start_dbfs,
            stop_dbfs=settings.vad_stop_dbfs,
            start_frames=settings.vad_start_frames,
            stop_frames=settings.vad_stop_frames,
            start_snr_db=settings.vad_start_snr_db,
            stop_snr_db=settings.vad_stop_snr_db,
            calibration_frames=settings.vad_calibration_ms // settings.frame_ms,
            noise_window_frames=settings.vad_noise_window_ms // settings.frame_ms,
        )
        self._enhancer = create_speech_enhancer(
            enabled=settings.speech_enhance,
            backend=settings.speech_enhance_backend,
            sample_rate=settings.sample_rate,
        )
        self._upload_queue: asyncio.Queue[_AudioFrame | _AudioCommit] = asyncio.Queue(
            settings.max_queue_frames
        )
        self._send_lock = asyncio.Lock()
        self._preroll: deque[bytes] = deque(
            maxlen=max(1, 200 // hello.audio.frame_ms)
        )
        self._capturing = False
        self._utterance: list[bytes] = []
        self._utterance_bytes = 0
        self._max_utterance_bytes = (
            settings.sample_rate * 2 * settings.max_utterance_seconds
        )
        self._turn = 0
        self._responded_turn = 0
        self._emotion_task: asyncio.Task[EmotionSnapshot | None] | None = None
        self._last_emotion_label = "neutral"
        self._last_emotion_sent_ns = 0
        self._last_item_id: str | None = None
        self._played_ms = 0
        self._had_response_audio = False
        self._generation_done = False
        self._response_requested_at: float | None = None
        self._mic_gate_until_ns = 0
        self._playback_watchdog: asyncio.Task[None] | None = None
        self._dropped_frames = 0

    async def run(self) -> None:
        tasks: set[asyncio.Task[None]] = set()
        try:
            await self.provider.connect()
            await self.provider.update_instructions(
                provider_instructions(self.emotion.snapshot())
            )
            await self._send_text(
                event_json(
                    "session.ready",
                    session_id=self.session_id,
                    protocol="companion-audio/1",
                    state=self.state,
                    mode="active",
                    interaction={"duplex": "half", "visual_input": False},
                    audio={
                        "sample_rate": self.settings.sample_rate,
                        "channels": 1,
                        "format": "pcm16",
                        "frame_ms": self.hello.audio.frame_ms,
                    },
                )
            )
            tasks = {
                asyncio.create_task(self._device_reader(), name="device-reader"),
                asyncio.create_task(self._audio_uploader(), name="audio-uploader"),
                asyncio.create_task(self._provider_reader(), name="provider-reader"),
            }
            done, pending = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                error = task.exception()
                if error is not None:
                    raise error
        finally:
            self._cancel_playback_watchdog()
            if self._emotion_task is not None:
                self._emotion_task.cancel()
                await asyncio.gather(self._emotion_task, return_exceptions=True)
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            await self.provider.close()

    async def _device_reader(self) -> None:
        try:
            async for message in self.socket:
                if isinstance(message, bytes):
                    await self._handle_audio(message)
                else:
                    await self._handle_control(message)
        except Exception as exc:
            # Browser reconnects and normal page exits intentionally end the
            # current device session. websockets only treats 1000/1001 as
            # clean, so our private reconnect code 4000 otherwise becomes a
            # misleading server error.
            if (
                exc.__class__.__name__.startswith("ConnectionClosed")
                and getattr(exc, "code", None) in {1000, 1001, 4000}
            ):
                return
            raise

    async def _handle_audio(self, pcm: bytes) -> None:
        if (
            not pcm
            or len(pcm) % 2
            or len(pcm) > self.settings.max_audio_message_bytes
        ):
            await self._send_text(
                safe_error("invalid_audio", "invalid PCM16 audio frame")
            )
            return
        if self.state not in {
            SessionState.LISTENING,
            SessionState.USER_SPEAKING,
        }:
            return
        if time.monotonic_ns() < self._mic_gate_until_ns:
            return
        if self._enhancer is not None:
            pcm = self._enhancer.process(pcm)
        try:
            features = pcm16_features(pcm)
        except ValueError as exc:
            await self._send_text(safe_error("invalid_audio", str(exc)))
            return

        snapshot = self.emotion.update_audio(features)
        was_capturing = self._capturing
        accepted = False
        if was_capturing and self._utterance_bytes + len(pcm) <= self._max_utterance_bytes:
            self._utterance.append(pcm)
            self._utterance_bytes += len(pcm)
            accepted = True
        self._preroll.append(pcm)

        vad_event = self.vad.update(features)
        if vad_event is not None and vad_event.type == "speech.started":
            self._start_utterance()
            await self._set_state(SessionState.USER_SPEAKING)
            if self.provider.manual_audio_commit:
                for captured in self._utterance:
                    self._queue_audio(captured)
        elif vad_event is not None and self._capturing:
            pcm_turn = self._finish_utterance()
            await self._set_state(SessionState.PROCESSING)
            if self.provider.manual_audio_commit:
                await self._upload_queue.put(_AudioCommit(self._turn))
            if pcm_turn:
                self._emotion_task = asyncio.create_task(
                    self._analyze_emotion(pcm_turn, self._turn),
                    name=f"emotion-{self._turn}",
                )
        elif self.provider.manual_audio_commit and was_capturing and accepted:
            self._queue_audio(pcm)
        elif not self.provider.manual_audio_commit:
            self._queue_audio(pcm)

        await self._publish_emotion(snapshot)

    def _start_utterance(self) -> None:
        if self._emotion_task is not None and not self._emotion_task.done():
            self._emotion_task.cancel()
        self._turn += 1
        self._capturing = True
        self._utterance = list(self._preroll)
        self._utterance_bytes = sum(map(len, self._utterance))
        self.emotion.begin_turn()

    def _finish_utterance(self) -> bytes:
        self._capturing = False
        pcm = b"".join(self._utterance)
        self._utterance.clear()
        self._utterance_bytes = 0
        return pcm

    def _queue_audio(self, pcm: bytes) -> None:
        if self._upload_queue.full():
            dropped = self._upload_queue.get_nowait()
            self._upload_queue.task_done()
            self._dropped_frames += int(isinstance(dropped, _AudioFrame))
        self._upload_queue.put_nowait(_AudioFrame(self._turn, pcm))

    async def _audio_uploader(self) -> None:
        while True:
            item = await self._upload_queue.get()
            try:
                if isinstance(item, _AudioCommit):
                    await self.provider.finish_audio_turn()
                else:
                    await self.provider.send_audio(item.pcm)
            finally:
                self._upload_queue.task_done()

    async def _provider_reader(self) -> None:
        async for event in self.provider.events():
            await self._handle_provider_event(event)

    async def _handle_provider_event(self, event: ProviderEvent) -> None:
        if event.type == "audio.delta" and event.audio:
            if self._response_requested_at is not None:
                logger.info(
                    "voice_turn_first_audio_ms=%.1f turn=%d",
                    (time.perf_counter() - self._response_requested_at) * 1000,
                    self._turn,
                )
                self._response_requested_at = None
            self._had_response_audio = True
            self._generation_done = False
            if event.item_id:
                self._last_item_id = event.item_id
            await self._set_state(SessionState.ASSISTANT_SPEAKING)
            frame_bytes = self.hello.audio.frame_bytes
            for offset in range(0, len(event.audio), frame_bytes):
                await self._send_binary(event.audio[offset : offset + frame_bytes])
            return

        if event.type == "response.item" and event.item_id:
            self._last_item_id = event.item_id
            return

        if event.type == "response.started":
            self._generation_done = False
            self._had_response_audio = False
            self._played_ms = 0
            return

        if event.type == "user.transcript" and event.text:
            final = bool(event.data.get("final"))
            provider_emotion = self._normalize_provider_emotion(
                event.data.get("provider_emotion")
            )
            if provider_emotion is not None:
                provider_snapshot = self.emotion.update_model(
                    provider_emotion,
                    source="qwen_realtime",
                )
                await self._publish_emotion(provider_snapshot, force=final)
            await self._send_text(
                event_json(
                    "transcript.user",
                    text=event.text,
                    final=final,
                    item_id=event.item_id,
                    turn=self._turn,
                    language=event.data.get("language", ""),
                )
            )
            snapshot = self.emotion.update_text(event.text)
            await self._publish_emotion(snapshot, force=final)
            if final:
                reason = unreliable_transcript_reason(
                    event.text, min_chars=self.settings.asr_reply_min_chars
                )
                if reason is not None:
                    await self._send_text(
                        event_json(
                            "turn.ignored",
                            turn=self._turn,
                            reason=reason,
                            text=event.text,
                        )
                    )
                    await self._set_state(SessionState.LISTENING)
                    return
                await self._request_response(snapshot)
            return

        if event.type.startswith("assistant.transcript"):
            await self._send_text(
                event_json(
                    "transcript.assistant",
                    text=event.text or "",
                    final=event.type.endswith("done"),
                    item_id=event.item_id,
                )
            )
            return

        if event.type == "response.done":
            status = str(event.data.get("status", "done"))
            cancelled = status in {"cancelled", "canceled"}
            self._generation_done = not cancelled
            await self._send_text(
                event_json(
                    "audio.done",
                    item_id=self._last_item_id,
                    status=status,
                    usage=event.data.get("usage"),
                )
            )
            if cancelled or not self._had_response_audio:
                self._response_requested_at = None
                await self._return_to_listening()
            else:
                self._arm_playback_watchdog()
            return

        if event.type == "error":
            self._response_requested_at = None
            code = str(event.data.get("code") or "provider_error")
            if code == "local_asr_empty":
                await self._send_text(
                    event_json("turn.ignored", turn=self._turn, reason="empty_asr")
                )
            else:
                await self._send_text(
                    safe_error(code, event.text or "provider error", retryable=True)
                )
            await self._return_to_listening()

    @staticmethod
    def _normalize_provider_emotion(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        normalized = value.strip().lower()
        aliases = {
            "neutral": "neutral",
            "calm": "calm",
            "happy": "happy",
            "excited": "excited",
            "surprised": "excited",
            "sad": "low",
            "low": "low",
            "fearful": "anxious",
            "fear": "anxious",
            "anxious": "anxious",
            "angry": "angry",
        }
        return aliases.get(normalized)

    async def _request_response(self, fallback: EmotionSnapshot) -> None:
        if self._responded_turn == self._turn:
            return
        self._responded_turn = self._turn
        self._response_requested_at = time.perf_counter()
        snapshot = await self._wait_for_model_emotion(fallback)
        instructions = provider_instructions(snapshot)
        await self.provider.update_instructions(instructions)
        with_emotion = getattr(self.provider, "create_response_with_emotion", None)
        if with_emotion is not None:
            await with_emotion(instructions, snapshot)
        else:
            await self.provider.create_response(instructions)

    async def _wait_for_model_emotion(
        self, fallback: EmotionSnapshot
    ) -> EmotionSnapshot:
        task = self._emotion_task
        timeout = self.settings.emotion_timeout_ms / 1000
        if task is None or timeout <= 0:
            return fallback
        try:
            result = await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
            # The model task may have completed before the final transcript.
            # Read the latest fused state, not its pre-transcript return value.
            return self.emotion.snapshot() if result is not None else fallback
        except TimeoutError:
            logger.debug(
                "emotion analysis missed %sms deadline session=%s",
                self.settings.emotion_timeout_ms,
                self.session_id,
            )
            return fallback

    async def _analyze_emotion(
        self, pcm: bytes, turn: int
    ) -> EmotionSnapshot | None:
        if len(pcm) < self.settings.sample_rate * 2 // 5:
            return None
        try:
            result = await asyncio.to_thread(
                self.emotion_analyzer.analyze_pcm16,
                pcm,
                self.settings.sample_rate,
            )
            if result is None or turn != self._turn:
                return None
            snapshot = self.emotion.update_model(
                result.label,
                source=result.source,
                confidence=result.confidence,
            )
            await self._publish_emotion(snapshot, force=True)
            return snapshot
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("emotion analysis failed session=%s", self.session_id)
            return None

    async def _publish_emotion(
        self, snapshot: EmotionSnapshot, *, force: bool = False
    ) -> None:
        now = time.monotonic_ns()
        changed = snapshot.label != self._last_emotion_label
        if not force and not changed and now - self._last_emotion_sent_ns < 300_000_000:
            return
        self._last_emotion_sent_ns = now
        self._last_emotion_label = snapshot.label
        await self._send_text(
            event_json("emotion.updated", emotion=snapshot.to_dict())
        )

    async def _handle_control(self, raw: str) -> None:
        try:
            event = parse_control(raw)
        except ProtocolError as exc:
            await self._send_text(safe_error("invalid_control", str(exc)))
            return
        event_type = event["type"]
        if event_type == "ping":
            await self._send_text(
                event_json("pong", echo=event.get("timestamp_ms"))
            )
        elif event_type == "playback.progress":
            played_ms = event.get("played_ms")
            if isinstance(played_ms, int) and played_ms >= 0:
                self._played_ms = played_ms
            item_id = event.get("item_id")
            if isinstance(item_id, str):
                self._last_item_id = item_id
        elif event_type == "playback.drained":
            await self._return_to_listening()
        elif event_type in {"response.cancel", "audio.flush"}:
            await self._interrupt()
        elif event_type in {"client.metrics", "client.audio_settings"}:
            return
        else:
            await self._send_text(
                safe_error(
                    "unsupported_event",
                    f"unsupported voice-only event: {event_type}",
                )
            )

    async def _interrupt(self) -> None:
        self._cancel_playback_watchdog()
        await self._set_state(SessionState.INTERRUPTING)
        await self._send_text(
            event_json(
                "audio.flush",
                item_id=self._last_item_id,
                played_ms=self._played_ms,
            )
        )
        await self.provider.cancel(
            item_id=self._last_item_id,
            played_ms=self._played_ms,
            cancel_response=not self._generation_done,
        )
        await self._return_to_listening()

    async def _return_to_listening(self) -> None:
        self._cancel_playback_watchdog()
        self._last_item_id = None
        self._played_ms = 0
        self._had_response_audio = False
        self._generation_done = False
        self._mic_gate_until_ns = time.monotonic_ns() + (
            self.settings.playback_echo_guard_ms * 1_000_000
        )
        await self._set_state(SessionState.LISTENING)

    def _cancel_playback_watchdog(self) -> None:
        task = self._playback_watchdog
        self._playback_watchdog = None
        if task is not None and not task.done():
            task.cancel()

    def _arm_playback_watchdog(self) -> None:
        self._cancel_playback_watchdog()
        self._playback_watchdog = asyncio.create_task(
            self._playback_drain_watch(), name="playback-drain-watch"
        )

    async def _playback_drain_watch(self) -> None:
        try:
            await asyncio.sleep(15)
            if (
                self.state == SessionState.ASSISTANT_SPEAKING
                and self._generation_done
            ):
                logger.warning(
                    "playback.drained missing session=%s; recovering",
                    self.session_id,
                )
                await self._return_to_listening()
        except asyncio.CancelledError:
            raise

    async def _set_state(self, state: SessionState) -> None:
        if state == self.state:
            return
        previous = self.state
        self.state = state
        await self._send_text(
            event_json(
                "state.changed",
                previous=previous,
                state=state,
                session_id=self.session_id,
            )
        )

    async def _send_text(self, message: str) -> None:
        async with self._send_lock:
            await self.socket.send(message)

    async def _send_binary(self, message: bytes) -> None:
        if not message:
            return
        async with self._send_lock:
            await self.socket.send(message)
