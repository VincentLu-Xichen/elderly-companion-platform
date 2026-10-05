from __future__ import annotations

import asyncio
import inspect
import json
import logging
import re
import time
import unicodedata
import uuid
from collections.abc import AsyncIterator
from typing import Protocol

from ..transcription import SenseVoiceTranscriber
from ..contracts import EmotionSnapshot
from .base import ProviderEvent

logger = logging.getLogger(__name__)


def sanitize_spoken_text(text: str) -> str:
    """Remove symbols that should never reach transcripts or speech synthesis."""
    return "".join(
        character
        for character in text
        if unicodedata.category(character) not in {"So", "Sk"}
        and character not in {"\u200d", "\ufe0e", "\ufe0f", "#", "*", "`"}
    )


class ChatClient(Protocol):
    async def warmup(self) -> None: ...

    def stream_reply(
        self, messages: list[dict[str, str]]
    ) -> AsyncIterator[str]: ...


class SpeechSynthesizer(Protocol):
    def stream_pcm24k(
        self, text: str, *, instructions: str
    ) -> AsyncIterator[bytes]: ...


class OllamaChatClient:
    """Native Ollama streaming client with thinking explicitly disabled."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        temperature: float = 0.7,
        keep_alive: str = "30m",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.keep_alive = keep_alive

    async def warmup(self) -> None:
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover - base dependency in local extra
            raise RuntimeError("Install local companion dependencies") from exc
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": "只回复：好"}],
            "stream": False,
            "think": False,
            "keep_alive": self.keep_alive,
            "options": {"temperature": 0, "num_predict": 4},
        }
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(f"{self.base_url}/api/chat", json=payload)
                response.raise_for_status()
        except httpx.ConnectError as exc:
            raise RuntimeError(
                "Ollama is not reachable. Start it with: ollama serve"
            ) from exc
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:300]
            raise RuntimeError(
                f"Ollama model '{self.model}' is unavailable: {detail}. "
                f"Run: ollama pull {self.model}"
            ) from exc

    async def stream_reply(
        self, messages: list[dict[str, str]]
    ) -> AsyncIterator[str]:
        import httpx

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "think": False,
            "keep_alive": self.keep_alive,
            "options": {
                "temperature": self.temperature,
                "num_ctx": 2_048,
                "num_predict": 120,
                "top_p": 0.85,
                "repeat_penalty": 1.08,
            },
        }
        timeout = httpx.Timeout(connect=10, read=120, write=10, pool=10)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST", f"{self.base_url}/api/chat", json=payload
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except ValueError:
                        logger.warning("Ignoring malformed Ollama stream event")
                        continue
                    message = event.get("message") or {}
                    content = message.get("content") or ""
                    if content:
                        yield str(content)
                    if event.get("done"):
                        break


class EdgeTtsSynthesizer:
    """Stream Edge neural TTS MP3 through ffmpeg into 24 kHz mono PCM16."""

    def __init__(
        self,
        *,
        voice: str = "zh-CN-XiaoyiNeural",
        ffmpeg_path: str = "ffmpeg",
    ) -> None:
        self.voice = voice
        self.ffmpeg_path = ffmpeg_path
        self._acknowledgements: dict[str, tuple[str, bytes]] = {}

    async def warmup(self) -> None:
        profiles = {
            "neutral": ("嗯，你说。", "保持自然"),
            "gentle": ("嗯，我在这儿。", "语速稍慢"),
            "happy": ("嘿，我听到啦。", "可以略带笑意回应"),
            "steady": ("好，我听着呢。", "不要争辩"),
        }

        async def render(text: str, instructions: str) -> tuple[str, bytes]:
            chunks = [
                chunk
                async for chunk in self.stream_pcm24k(
                    text,
                    instructions=instructions,
                )
            ]
            return text, b"".join(chunks)

        results = await asyncio.gather(
            *(render(text, instructions) for text, instructions in profiles.values())
        )
        self._acknowledgements = dict(zip(profiles, results, strict=True))

    async def acknowledgement(self, instructions: str) -> tuple[str, bytes] | None:
        if not self._acknowledgements:
            return None
        if "语速稍慢" in instructions or "降低信息密度" in instructions:
            key = "gentle"
        elif "略带笑意" in instructions or "积极情绪" in instructions:
            key = "happy"
        elif "不要争辩" in instructions:
            key = "steady"
        else:
            key = "neutral"
        return self._acknowledgements[key]

    async def stream_pcm24k(
        self, text: str, *, instructions: str
    ) -> AsyncIterator[bytes]:
        try:
            import edge_tts
        except ImportError as exc:  # pragma: no cover - optional extra
            raise RuntimeError(
                "Install local companion dependencies: pip install -e '.[local-companion]'"
            ) from exc

        rate, pitch = _voice_style(instructions)
        communicator = edge_tts.Communicate(
            text=text,
            voice=self.voice,
            rate=rate,
            pitch=pitch,
        )
        process = await asyncio.create_subprocess_exec(
            self.ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            "pipe:0",
            "-f",
            "s16le",
            "-acodec",
            "pcm_s16le",
            "-ac",
            "1",
            "-ar",
            "24000",
            "pipe:1",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        assert process.stdin is not None
        assert process.stdout is not None

        async def feed_mp3() -> None:
            try:
                async for chunk in communicator.stream():
                    if chunk.get("type") == "audio" and chunk.get("data"):
                        process.stdin.write(chunk["data"])
                        await process.stdin.drain()
            finally:
                process.stdin.close()

        feeder = asyncio.create_task(feed_mp3(), name="edge-tts-mp3-feeder")
        try:
            while True:
                pcm = await process.stdout.read(3_840)
                if not pcm:
                    break
                yield pcm
            await feeder
            return_code = await process.wait()
            if return_code:
                stderr = b""
                if process.stderr is not None:
                    stderr = await process.stderr.read()
                raise RuntimeError(f"ffmpeg TTS decode failed: {stderr.decode()[:300]}")
        finally:
            if not feeder.done():
                feeder.cancel()
                await asyncio.gather(feeder, return_exceptions=True)
            if process.returncode is None:
                process.terminate()
                await process.wait()


class LocalCompanionProvider:
    """Modular ASR + dialogue model + streaming TTS provider."""

    manual_audio_commit = True

    def __init__(
        self,
        *,
        transcriber: object,
        chat_client: ChatClient,
        synthesizer: SpeechSynthesizer,
        instructions: str,
        history_turns: int = 8,
    ) -> None:
        self.transcriber = transcriber
        self.chat_client = chat_client
        self.synthesizer = synthesizer
        self.instructions = instructions
        self.history_turns = max(1, history_turns)
        self._events: asyncio.Queue[ProviderEvent | None] = asyncio.Queue()
        self._audio = bytearray()
        self._pending_user_text = ""
        self._history: list[dict[str, str]] = []
        self._response_task: asyncio.Task[None] | None = None
        self._closed = False

    async def connect(self) -> None:
        tts_warmup = getattr(self.synthesizer, "warmup", None)
        asr_warmup = getattr(self.transcriber, "warmup")
        if inspect.iscoroutinefunction(asr_warmup):
            asr_job = asr_warmup()
        else:
            asr_job = asyncio.to_thread(asr_warmup)
        jobs = [
            asr_job,
            self.chat_client.warmup(),
        ]
        if tts_warmup is not None:
            jobs.append(tts_warmup())
        await asyncio.gather(*jobs)

    async def send_audio(self, pcm: bytes) -> None:
        first_chunk = not self._audio
        self._audio.extend(pcm)
        stream_audio = getattr(self.transcriber, "send_stream_audio", None)
        if stream_audio is not None:
            if first_chunk:
                await self.transcriber.start_stream(24_000)
            await stream_audio(pcm)

    async def finish_audio_turn(self) -> None:
        pcm = bytes(self._audio)
        self._audio.clear()
        finish_stream = getattr(self.transcriber, "finish_stream", None)
        if finish_stream is not None:
            result = await finish_stream()
        else:
            result = await asyncio.to_thread(
                self.transcriber.transcribe_pcm16,
                pcm,
                24_000,
            )
        if result is None:
            await self._events.put(
                ProviderEvent(
                    "error",
                    text="没有听清，请再说一次",
                    data={"code": "local_asr_empty"},
                )
            )
            return
        logger.info("voice_asr_complete latency_ms=%.1f chars=%d", result.latency_ms, len(result.text))
        self._pending_user_text = result.text
        await self._events.put(
            ProviderEvent(
                "user.transcript",
                text=result.text,
                item_id=f"user-{uuid.uuid4().hex}",
                data={
                    "final": True,
                    "language": result.language,
                    "asr_emotion": result.event,
                    "provider_emotion": result.event,
                    "latency_ms": result.latency_ms,
                },
            )
        )

    async def cancel(
        self, *, item_id: str | None, played_ms: int, cancel_response: bool = True
    ) -> None:
        task = self._response_task
        if cancel_response and task is not None and not task.done():
            task.cancel()

    async def update_instructions(self, instructions: str) -> None:
        self.instructions = instructions

    async def create_response(self, instructions: str) -> None:
        await self.create_response_with_emotion(instructions, None)

    async def create_response_with_emotion(
        self, instructions: str, emotion: EmotionSnapshot | None,
    ) -> None:
        if not self._pending_user_text:
            # A stale response-wait can re-enter after the transcript path already
            # started TTS. Never cancel that in-flight reply for an empty buffer.
            task = self._response_task
            if task is not None and not task.done():
                return
            await self._events.put(
                ProviderEvent(
                    "error",
                    text="没有可回答的本地转写",
                    data={"code": "local_missing_transcript"},
                )
            )
            return
        previous = self._response_task
        if previous is not None and not previous.done():
            previous.cancel()
            await asyncio.gather(previous, return_exceptions=True)
        user_text = self._pending_user_text
        self._pending_user_text = ""
        self._response_task = asyncio.create_task(
            self._run_response(user_text, instructions, emotion=emotion),
            name="local-companion-response",
        )

    async def create_scripted_response(
        self,
        text: str,
        instructions: str,
        *,
        remember: bool = False,
    ) -> None:
        spoken = sanitize_spoken_text(text).strip()
        if not spoken:
            raise ValueError("scripted response must contain speakable text")
        previous = self._response_task
        if previous is not None and not previous.done():
            previous.cancel()
            await asyncio.gather(previous, return_exceptions=True)
        self._response_task = asyncio.create_task(
            self._run_response(
                "",
                instructions,
                scripted_text=spoken,
                remember_scripted=remember,
            ),
            name="local-companion-scripted-response",
        )

    async def events(self) -> AsyncIterator[ProviderEvent]:
        while True:
            event = await self._events.get()
            if event is None:
                return
            yield event

    async def close(self) -> None:
        self._closed = True
        task = self._response_task
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        synthesizer_close = getattr(self.synthesizer, "close", None)
        if synthesizer_close is not None:
            await synthesizer_close()
        transcriber_close = getattr(self.transcriber, "close", None)
        if transcriber_close is not None:
            close_result = transcriber_close()
            if inspect.isawaitable(close_result):
                await close_result
        chat_close = getattr(self.chat_client, "close", None)
        if chat_close is not None:
            close_result = chat_close()
            if inspect.isawaitable(close_result):
                await close_result
        await self._events.put(None)

    async def _run_response(
        self,
        user_text: str,
        instructions: str,
        *,
        scripted_text: str | None = None,
        remember_scripted: bool = False,
        emotion: EmotionSnapshot | None = None,
    ) -> None:
        timing: dict[str, float | None] = {
            "started": time.perf_counter(),
            "model_first": None,
            "model_done": None,
            "audio_first": None,
        }
        response_id = f"local-response-{uuid.uuid4().hex}"
        item_id = f"assistant-{uuid.uuid4().hex}"
        await self._events.put(
            ProviderEvent("response.started", data={"response_id": response_id})
        )
        await self._events.put(ProviderEvent("response.item", item_id=item_id))
        acknowledgement = (
            None
            if scripted_text is not None
            else getattr(self.synthesizer, "acknowledgement", None)
        )
        preface = (
            "\n系统会先播放一句很短的承接语。你的正文请直接回应用户的具体内容，"
            "不要再以“嗯”“我在听”“听起来”或同义套话开头。"
            if acknowledgement is not None
            else ""
        )
        messages = [
            {
                "role": "system",
                "content": instructions + preface,
            },
            *self._history,
            {"role": "user", "content": user_text},
        ]
        sentence_queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=4)
        full_text: list[str] = []
        prepare = getattr(self.synthesizer, "prepare", None)
        prepare_task = (
            asyncio.create_task(prepare(instructions), name="local-tts-prepare")
            if prepare is not None
            else None
        )

        if acknowledgement is not None:
            prepared = await acknowledgement(instructions)
            if prepared is not None:
                acknowledgement_text, acknowledgement_audio = prepared
                if acknowledgement_audio:
                    timing["audio_first"] = time.perf_counter()
                    full_text.append(acknowledgement_text)
                    await self._events.put(
                        ProviderEvent(
                            "assistant.transcript.delta",
                            text=acknowledgement_text,
                            item_id=item_id,
                            data={"prefetched": True},
                        )
                    )
                    await self._events.put(
                        ProviderEvent(
                            "audio.delta",
                            audio=acknowledgement_audio,
                            item_id=item_id,
                            data={"response_id": response_id, "prefetched": True},
                        )
                    )

        async def produce_text() -> None:
            pending = ""
            if scripted_text is not None:
                tokens = _single_text_stream(scripted_text)
            else:
                with_emotion = getattr(self.chat_client, "stream_reply_with_emotion", None)
                tokens = (
                    with_emotion(messages, emotion) if with_emotion is not None
                    else self.chat_client.stream_reply(messages)
                )
            async for token in tokens:
                spoken_token = sanitize_spoken_text(token)
                if not spoken_token:
                    continue
                if timing["model_first"] is None:
                    timing["model_first"] = time.perf_counter()
                full_text.append(spoken_token)
                pending += spoken_token
                await self._events.put(
                    ProviderEvent(
                        "assistant.transcript.delta",
                        text=spoken_token,
                        item_id=item_id,
                    )
                )
                segments, pending = _extract_speakable_segments(pending)
                for segment in segments:
                    await sentence_queue.put(segment)
            if pending.strip():
                await sentence_queue.put(pending.strip())
            await sentence_queue.put(None)
            timing["model_done"] = time.perf_counter()

        async def speak_text() -> None:
            if prepare_task is not None:
                await prepare_task
            while True:
                sentence = await sentence_queue.get()
                if sentence is None:
                    return
                async for pcm in self.synthesizer.stream_pcm24k(
                    sentence, instructions=instructions
                ):
                    if timing["audio_first"] is None:
                        timing["audio_first"] = time.perf_counter()
                    await self._events.put(
                        ProviderEvent(
                            "audio.delta",
                            audio=pcm,
                            item_id=item_id,
                            data={"response_id": response_id},
                        )
                    )

        producer = asyncio.create_task(produce_text(), name="local-text-producer")
        speaker = asyncio.create_task(speak_text(), name="local-tts-speaker")
        workers = (producer, speaker)
        try:
            await asyncio.gather(*workers)
            answer = "".join(full_text).strip()
            elapsed = time.perf_counter() - timing["started"]
            model_first = timing["model_first"]
            model_done = timing["model_done"]
            audio_first = timing["audio_first"]
            logger.info(
                "voice_reply_timing model_first_ms=%d model_total_ms=%d "
                "audio_first_ms=%d total_ms=%d",
                -1 if model_first is None else round((model_first - timing["started"]) * 1000),
                -1 if model_done is None else round((model_done - timing["started"]) * 1000),
                -1 if audio_first is None else round((audio_first - timing["started"]) * 1000),
                round(elapsed * 1000),
            )
            if answer:
                if scripted_text is None:
                    self._history.extend(
                        [
                            {"role": "user", "content": user_text},
                            {"role": "assistant", "content": answer},
                        ]
                    )
                elif remember_scripted:
                    self._history.append({"role": "assistant", "content": answer})
                self._history = self._history[-self.history_turns * 2 :]
            await self._events.put(
                ProviderEvent(
                    "assistant.transcript.done",
                    text=answer,
                    item_id=item_id,
                )
            )
            await self._events.put(
                ProviderEvent(
                    "response.done",
                    data={"status": "completed", "response_id": response_id},
                )
            )
        except asyncio.CancelledError:
            if prepare_task is not None:
                prepare_task.cancel()
            for worker in workers:
                worker.cancel()
            await asyncio.gather(
                *workers,
                *(() if prepare_task is None else (prepare_task,)),
                return_exceptions=True,
            )
            await self._events.put(
                ProviderEvent(
                    "response.done",
                    data={"status": "cancelled", "response_id": response_id},
                )
            )
            raise
        except Exception as exc:
            if prepare_task is not None:
                prepare_task.cancel()
            for worker in workers:
                worker.cancel()
            await asyncio.gather(
                *workers,
                *(() if prepare_task is None else (prepare_task,)),
                return_exceptions=True,
            )
            logger.exception("local companion response failed")
            await self._events.put(
                ProviderEvent(
                    "error",
                    text=str(exc),
                    data={"code": "local_response_failed"},
                )
            )
            await self._events.put(
                ProviderEvent(
                    "response.done",
                    data={"status": "failed", "response_id": response_id},
                )
            )


_BOUNDARY = re.compile(r"^(.+?[，。！？；,.!?;：:\n])(?=.+|$)", re.DOTALL)


async def _single_text_stream(text: str) -> AsyncIterator[str]:
    yield text


def _extract_speakable_segments(buffer: str) -> tuple[list[str], str]:
    segments: list[str] = []
    remaining = buffer
    while True:
        match = _BOUNDARY.match(remaining)
        if match is None:
            break
        segment = match.group(1).strip()
        remaining = remaining[match.end() :]
        # Avoid sending a one-character discourse marker as its own TTS job.
        if len(segment) < 3 and remaining:
            remaining = segment + remaining
            break
        if segment:
            segments.append(segment)
    # Bound first-audio latency even if the model avoids punctuation.
    if not segments and len(remaining) >= 32:
        split_at = max(12, remaining.rfind(" ", 12, 32))
        if split_at <= 0:
            split_at = 28
        segments.append(remaining[:split_at].strip())
        remaining = remaining[split_at:]
    return segments, remaining


def _voice_style(instructions: str) -> tuple[str, str]:
    if "语速稍慢" in instructions or "降低信息密度" in instructions:
        return "-8%", "-2Hz"
    if "略带笑意" in instructions or "积极情绪" in instructions:
        return "+5%", "+2Hz"
    if "不要争辩" in instructions:
        return "-4%", "-1Hz"
    # The default character is a light, lively sprite. Keep this adjustment
    # deliberately small so it still sounds natural over longer conversations.
    return "+2%", "+1Hz"
