from __future__ import annotations

import asyncio
import hmac
import logging
from collections.abc import Callable
from typing import Any

from .config import Settings
from .contracts import EmotionSnapshot
from .emotion_backends import (
    DisabledEmotionAnalyzer,
    Emotion2VecAnalyzer,
    EmotionAnalyzer,
)
from .policy import provider_instructions
from .protocol import DeviceHello, ProtocolError, safe_error
from .providers import (
    AgentBridgeChatClient,
    CbtAgentBridgeChatClient,
    EdgeTtsSynthesizer,
    LocalCompanionProvider,
    MockRealtimeProvider,
    OllamaChatClient,
    QwenRealtimeProvider,
    QwenRealtimeTtsSynthesizer,
    RealtimeProvider,
)
from .session import DeviceSession
from .transcription import QwenRealtimeTranscriber, SenseVoiceTranscriber

logger = logging.getLogger(__name__)
ProviderFactory = Callable[[DeviceHello], RealtimeProvider]


class Gateway:
    def __init__(
        self,
        settings: Settings,
        *,
        provider_factory: ProviderFactory | None = None,
        emotion_analyzer: EmotionAnalyzer | None = None,
    ) -> None:
        self.settings = settings
        self.provider_factory = provider_factory or self._provider_for
        self.emotion_analyzer = (
            emotion_analyzer or self._emotion_analyzer_for(settings)
        )
        self._active_connections = 0

    async def handle(self, socket: Any) -> None:
        request = getattr(socket, "request", None)
        path = getattr(request, "path", "/v1/device")
        if path != "/v1/device":
            await socket.close(code=1008, reason="unsupported path")
            return
        if self._active_connections >= self.settings.max_connections:
            await socket.close(code=1013, reason="gateway at capacity")
            return
        self._active_connections += 1
        try:
            await self._handle_session(socket)
        finally:
            self._active_connections -= 1

    async def _handle_session(self, socket: Any) -> None:
        try:
            raw = await asyncio.wait_for(socket.recv(), timeout=5)
            hello = DeviceHello.parse(raw)
            self._authorize(hello)
        except TimeoutError:
            await socket.send(
                safe_error("hello_timeout", "device.hello not received in time")
            )
            await socket.close(code=1008, reason="hello timeout")
            return
        except ProtocolError as exc:
            await socket.send(safe_error("invalid_hello", str(exc)))
            await socket.close(code=1008, reason="invalid hello")
            return

        session = DeviceSession(
            socket=socket,
            hello=hello,
            provider=self.provider_factory(hello),
            settings=self.settings,
            emotion_analyzer=self.emotion_analyzer,
        )
        logger.info(
            "device connected id=%s type=%s provider=%s",
            hello.device_id,
            hello.device_type,
            self.settings.runtime_provider,
        )
        try:
            await session.run()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("device session failed id=%s", hello.device_id)
            try:
                await socket.send(
                    safe_error(
                        "session_failed",
                        "voice session ended unexpectedly",
                        retryable=True,
                    )
                )
                await socket.close(code=1011, reason="session failed")
            except Exception:
                pass
        finally:
            logger.info("device disconnected id=%s", hello.device_id)

    def _authorize(self, hello: DeviceHello) -> None:
        expected = self.settings.device_token
        if expected is None:
            return
        supplied = hello.token or ""
        if not hmac.compare_digest(supplied.encode(), expected.encode()):
            raise ProtocolError("invalid device token")

    def _provider_for(self, hello: DeviceHello) -> RealtimeProvider:
        del hello
        if self.settings.runtime_provider == "mock":
            return MockRealtimeProvider()

        initial = provider_instructions(
            EmotionSnapshot(0.0, 0.0, "neutral", 0.0, (), 0)
        )
        if self.settings.runtime_provider == "qwen_realtime":
            assert self.settings.dashscope_api_key is not None
            assert self.settings.qwen_realtime_workspace_id is not None
            return QwenRealtimeProvider(
                api_key=self.settings.dashscope_api_key,
                workspace_id=self.settings.qwen_realtime_workspace_id,
                region=self.settings.qwen_realtime_region,
                model=self.settings.qwen_realtime_model,
                voice=self.settings.qwen_realtime_voice,
                instructions=initial,
            )

        if self.settings.asr_provider == "qwen":
            assert self.settings.dashscope_api_key is not None
            transcriber = QwenRealtimeTranscriber(
                api_key=self.settings.dashscope_api_key,
                model=self.settings.qwen_asr_model,
                region=self.settings.qwen_asr_region,
                workspace_id=self.settings.qwen_asr_workspace_id,
                language=self.settings.qwen_asr_language,
                context=self.settings.qwen_asr_context,
                timeout_seconds=self.settings.qwen_asr_timeout_seconds,
            )
        else:
            assert self.settings.sensevoice_model_dir is not None
            transcriber = SenseVoiceTranscriber(
                self.settings.sensevoice_model_dir,
                num_threads=self.settings.sensevoice_threads,
            )

        if self.settings.tts_provider == "qwen":
            assert self.settings.dashscope_api_key is not None
            synthesizer = QwenRealtimeTtsSynthesizer(
                api_key=self.settings.dashscope_api_key,
                model=self.settings.qwen_tts_model,
                voice=self.settings.qwen_tts_voice,
                region=self.settings.qwen_tts_region,
                workspace_id=self.settings.qwen_tts_workspace_id,
                optimize_instructions=(
                    self.settings.qwen_tts_optimize_instructions
                ),
            )
        else:
            synthesizer = EdgeTtsSynthesizer(
                voice=self.settings.edge_tts_voice,
                ffmpeg_path=self.settings.ffmpeg_path,
            )

        if self.settings.chat_provider in {"agent_bridge", "cbt_agent_bridge"}:
            assert self.settings.agent_bridge_token is not None
            bridge_class = (
                CbtAgentBridgeChatClient
                if self.settings.chat_provider == "cbt_agent_bridge"
                else AgentBridgeChatClient
            )
            bridge_kwargs = {
                "base_url": self.settings.agent_bridge_url,
                "token": self.settings.agent_bridge_token,
                "device_id": self.settings.agent_bridge_device_id,
                "timeout_seconds": self.settings.agent_bridge_timeout_seconds,
            }
            if self.settings.chat_provider == "cbt_agent_bridge":
                bridge_kwargs["lesson_id"] = self.settings.cbt_lesson_id
            chat_client = bridge_class(
                **bridge_kwargs,
            )
        else:
            chat_client = OllamaChatClient(
                base_url=self.settings.ollama_url,
                model=self.settings.ollama_model,
            )

        return LocalCompanionProvider(
            transcriber=transcriber,
            chat_client=chat_client,
            synthesizer=synthesizer,
            instructions=initial,
            history_turns=self.settings.history_turns,
        )

    @staticmethod
    def _emotion_analyzer_for(settings: Settings) -> EmotionAnalyzer:
        if settings.emotion_backend == "heuristic":
            return DisabledEmotionAnalyzer()
        assert settings.emotion2vec_model_dir is not None
        analyzer = Emotion2VecAnalyzer(
            settings.emotion2vec_model_dir,
            num_threads=settings.emotion2vec_threads,
        )
        analyzer.warmup()
        return analyzer


async def serve_forever(settings: Settings) -> None:
    try:
        from websockets.asyncio.server import serve
    except ImportError as exc:
        raise RuntimeError("Install project dependencies before starting ESDS") from exc

    gateway = Gateway(settings)
    async with serve(
        gateway.handle,
        settings.host,
        settings.port,
        max_size=settings.max_ws_message_bytes,
        max_queue=4,
        compression=None,
        ping_interval=20,
        ping_timeout=20,
    ):
        logger.info(
            "ESDS voice gateway listening ws://%s:%s/v1/device provider=%s",
            settings.host,
            settings.port,
            settings.runtime_provider,
        )
        await asyncio.Future()
