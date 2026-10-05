from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return default if raw is None else int(raw)


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return default if raw is None else float(raw)


@dataclass(frozen=True, slots=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8765
    runtime_provider: str = "local"
    device_token: str | None = None

    asr_provider: str = "sensevoice"
    sensevoice_model_dir: str | None = None
    sensevoice_threads: int = 2
    qwen_asr_model: str = "qwen3-asr-flash-realtime"
    qwen_asr_region: str = "beijing"
    qwen_asr_workspace_id: str | None = None
    qwen_asr_language: str = "zh"
    qwen_asr_context: str = ""
    qwen_asr_timeout_seconds: float = 8.0

    qwen_realtime_model: str = "qwen3.5-omni-flash-realtime"
    qwen_realtime_voice: str = "Tina"
    qwen_realtime_region: str = "beijing"
    qwen_realtime_workspace_id: str | None = None

    emotion_backend: str = "emotion2vec"
    emotion2vec_model_dir: str | None = None
    emotion2vec_threads: int = 4
    emotion_timeout_ms: int = 240

    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:4b-instruct"
    chat_provider: str = "ollama"
    cbt_lesson_id: str = "lesson-1"
    agent_bridge_url: str = "http://127.0.0.1:8000"
    agent_bridge_token: str | None = None
    agent_bridge_device_id: str = ""
    agent_bridge_timeout_seconds: float = 65.0
    history_turns: int = 8

    tts_provider: str = "qwen"
    dashscope_api_key: str | None = None
    qwen_tts_model: str = "qwen3-tts-instruct-flash-realtime"
    qwen_tts_voice: str = "Cherry"
    qwen_tts_region: str = "beijing"
    qwen_tts_workspace_id: str | None = None
    qwen_tts_optimize_instructions: bool = False
    edge_tts_voice: str = "zh-CN-XiaoyiNeural"
    ffmpeg_path: str = "ffmpeg"

    sample_rate: int = 24_000
    frame_ms: int = 20
    max_utterance_seconds: int = 20
    vad_start_dbfs: float = -43.0
    vad_stop_dbfs: float = -49.0
    vad_start_snr_db: float = 14.0
    vad_stop_snr_db: float = 6.0
    vad_start_frames: int = 4
    vad_stop_frames: int = 18
    vad_calibration_ms: int = 500
    vad_noise_window_ms: int = 3_000
    speech_enhance: bool = True
    speech_enhance_backend: str = "spectral"
    playback_echo_guard_ms: int = 450
    asr_reply_min_chars: int = 2
    max_audio_message_bytes: int = 48_000
    max_ws_message_bytes: int = 64_000
    max_queue_frames: int = 100
    max_connections: int = 32
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        settings = cls(
            host=os.getenv("ESDS_HOST", "127.0.0.1"),
            port=_env_int("ESDS_PORT", 8765),
            runtime_provider=os.getenv("ESDS_RUNTIME_PROVIDER", "local").lower(),
            device_token=os.getenv("ESDS_DEVICE_TOKEN") or None,
            asr_provider=os.getenv("ESDS_ASR_PROVIDER", "sensevoice").lower(),
            sensevoice_model_dir=os.getenv("ESDS_SENSEVOICE_MODEL_DIR") or None,
            sensevoice_threads=_env_int("ESDS_SENSEVOICE_THREADS", 2),
            qwen_asr_model=os.getenv(
                "ESDS_QWEN_ASR_MODEL", "qwen3-asr-flash-realtime"
            ),
            qwen_asr_region=os.getenv("ESDS_QWEN_ASR_REGION", "beijing").lower(),
            qwen_asr_workspace_id=os.getenv("ESDS_QWEN_ASR_WORKSPACE_ID") or None,
            qwen_asr_language=os.getenv("ESDS_QWEN_ASR_LANGUAGE", "zh"),
            qwen_asr_context=os.getenv("ESDS_QWEN_ASR_CONTEXT", ""),
            qwen_asr_timeout_seconds=_env_float(
                "ESDS_QWEN_ASR_TIMEOUT_SECONDS", 8.0
            ),
            qwen_realtime_model=os.getenv(
                "ESDS_QWEN_REALTIME_MODEL", "qwen3.5-omni-flash-realtime"
            ),
            qwen_realtime_voice=os.getenv("ESDS_QWEN_REALTIME_VOICE", "Tina"),
            qwen_realtime_region=os.getenv(
                "ESDS_QWEN_REALTIME_REGION", "beijing"
            ).lower(),
            qwen_realtime_workspace_id=(
                os.getenv("ESDS_QWEN_REALTIME_WORKSPACE_ID")
                or os.getenv("QWEN_WORKSPACE_ID")
                or None
            ),
            emotion_backend=os.getenv("ESDS_EMOTION_BACKEND", "emotion2vec").lower(),
            emotion2vec_model_dir=os.getenv("ESDS_EMOTION2VEC_MODEL_DIR") or None,
            emotion2vec_threads=_env_int("ESDS_EMOTION2VEC_THREADS", 4),
            emotion_timeout_ms=_env_int("ESDS_EMOTION_TIMEOUT_MS", 240),
            ollama_url=os.getenv("ESDS_OLLAMA_URL", "http://127.0.0.1:11434"),
            ollama_model=os.getenv("ESDS_OLLAMA_MODEL", "qwen3:4b-instruct"),
            chat_provider=os.getenv("ESDS_CHAT_PROVIDER", "ollama").lower(),
            cbt_lesson_id=os.getenv("ESDS_CBT_LESSON_ID", "lesson-1"),
            agent_bridge_url=os.getenv(
                "ESDS_AGENT_BRIDGE_URL", "http://127.0.0.1:8000"
            ),
            agent_bridge_token=os.getenv("ESDS_AGENT_BRIDGE_TOKEN") or None,
            agent_bridge_device_id=os.getenv("ESDS_AGENT_BRIDGE_DEVICE_ID", ""),
            agent_bridge_timeout_seconds=_env_float(
                "ESDS_AGENT_BRIDGE_TIMEOUT_SECONDS", 65.0
            ),
            history_turns=_env_int("ESDS_HISTORY_TURNS", 8),
            tts_provider=os.getenv("ESDS_TTS_PROVIDER", "qwen").lower(),
            dashscope_api_key=os.getenv("DASHSCOPE_API_KEY") or None,
            qwen_tts_model=os.getenv(
                "ESDS_QWEN_TTS_MODEL", "qwen3-tts-instruct-flash-realtime"
            ),
            qwen_tts_voice=os.getenv("ESDS_QWEN_TTS_VOICE", "Cherry"),
            qwen_tts_region=os.getenv("ESDS_QWEN_TTS_REGION", "beijing").lower(),
            qwen_tts_workspace_id=os.getenv("ESDS_QWEN_TTS_WORKSPACE_ID") or None,
            qwen_tts_optimize_instructions=_env_bool(
                "ESDS_QWEN_TTS_OPTIMIZE_INSTRUCTIONS", False
            ),
            edge_tts_voice=os.getenv(
                "ESDS_EDGE_TTS_VOICE", "zh-CN-XiaoyiNeural"
            ),
            ffmpeg_path=os.getenv("ESDS_FFMPEG_PATH", "ffmpeg"),
            sample_rate=_env_int("ESDS_SAMPLE_RATE", 24_000),
            frame_ms=_env_int("ESDS_FRAME_MS", 20),
            max_utterance_seconds=_env_int("ESDS_MAX_UTTERANCE_SECONDS", 20),
            vad_start_dbfs=_env_float("ESDS_VAD_START_DBFS", -43.0),
            vad_stop_dbfs=_env_float("ESDS_VAD_STOP_DBFS", -49.0),
            vad_start_snr_db=_env_float("ESDS_VAD_START_SNR_DB", 14.0),
            vad_stop_snr_db=_env_float("ESDS_VAD_STOP_SNR_DB", 6.0),
            vad_start_frames=_env_int("ESDS_VAD_START_FRAMES", 4),
            vad_stop_frames=_env_int("ESDS_VAD_STOP_FRAMES", 18),
            vad_calibration_ms=_env_int("ESDS_VAD_CALIBRATION_MS", 500),
            vad_noise_window_ms=_env_int("ESDS_VAD_NOISE_WINDOW_MS", 3_000),
            speech_enhance=_env_bool("ESDS_SPEECH_ENHANCE", True),
            speech_enhance_backend=os.getenv(
                "ESDS_SPEECH_ENHANCE_BACKEND", "spectral"
            ).lower(),
            playback_echo_guard_ms=_env_int("ESDS_PLAYBACK_ECHO_GUARD_MS", 450),
            asr_reply_min_chars=_env_int("ESDS_ASR_REPLY_MIN_CHARS", 2),
            max_audio_message_bytes=_env_int(
                "ESDS_MAX_AUDIO_MESSAGE_BYTES", 48_000
            ),
            max_ws_message_bytes=_env_int("ESDS_MAX_WS_MESSAGE_BYTES", 64_000),
            max_queue_frames=_env_int("ESDS_MAX_QUEUE_FRAMES", 100),
            max_connections=_env_int("ESDS_MAX_CONNECTIONS", 32),
            log_level=os.getenv("ESDS_LOG_LEVEL", "INFO"),
        )
        settings.validate()
        return settings

    @property
    def frame_bytes(self) -> int:
        return self.sample_rate * self.frame_ms // 1000 * 2

    def validate(self) -> None:
        if self.runtime_provider not in {"local", "qwen_realtime", "mock"}:
            raise ValueError(
                "ESDS_RUNTIME_PROVIDER must be local, qwen_realtime, or mock"
            )
        if self.sample_rate != 24_000:
            raise ValueError("ESDS_SAMPLE_RATE must be 24000")
        if self.frame_ms not in {10, 20, 30}:
            raise ValueError("ESDS_FRAME_MS must be 10, 20, or 30")
        if self.asr_provider not in {"sensevoice", "qwen"}:
            raise ValueError("ESDS_ASR_PROVIDER must be sensevoice or qwen")
        if self.chat_provider not in {"ollama", "agent_bridge", "cbt_agent_bridge"}:
            raise ValueError(
                "ESDS_CHAT_PROVIDER must be ollama, agent_bridge, or cbt_agent_bridge"
            )
        if self.runtime_provider == "local" and self.chat_provider in {"agent_bridge", "cbt_agent_bridge"}:
            if not self.agent_bridge_token:
                raise ValueError("ESDS_AGENT_BRIDGE_TOKEN is required")
            if not self.agent_bridge_device_id:
                raise ValueError("ESDS_AGENT_BRIDGE_DEVICE_ID is required")
            if self.agent_bridge_timeout_seconds <= 0:
                raise ValueError(
                    "ESDS_AGENT_BRIDGE_TIMEOUT_SECONDS must be positive"
                )
        if self.chat_provider == "cbt_agent_bridge" and self.cbt_lesson_id != "lesson-1":
            raise ValueError("ESDS_CBT_LESSON_ID currently supports lesson-1 only")
        if (
            self.runtime_provider == "local"
            and self.asr_provider == "sensevoice"
            and not self.sensevoice_model_dir
        ):
            raise ValueError(
                "ESDS_SENSEVOICE_MODEL_DIR is required for SenseVoice ASR"
            )
        if (
            self.runtime_provider == "local"
            and self.asr_provider == "qwen"
            and not self.dashscope_api_key
        ):
            raise ValueError("DASHSCOPE_API_KEY is required for Qwen ASR")
        if self.emotion_backend not in {"emotion2vec", "heuristic"}:
            raise ValueError("ESDS_EMOTION_BACKEND must be emotion2vec or heuristic")
        if self.emotion_backend == "emotion2vec" and not self.emotion2vec_model_dir:
            raise ValueError(
                "ESDS_EMOTION2VEC_MODEL_DIR is required for emotion2vec"
            )
        if self.tts_provider not in {"qwen", "edge"}:
            raise ValueError("ESDS_TTS_PROVIDER must be qwen or edge")
        if (
            self.runtime_provider == "local"
            and self.tts_provider == "qwen"
            and not self.dashscope_api_key
        ):
            raise ValueError("DASHSCOPE_API_KEY is required for Qwen TTS")
        if self.runtime_provider == "qwen_realtime":
            if not self.dashscope_api_key:
                raise ValueError(
                    "DASHSCOPE_API_KEY is required for Qwen Realtime"
                )
            if not self.qwen_realtime_workspace_id:
                raise ValueError(
                    "ESDS_QWEN_REALTIME_WORKSPACE_ID is required for Qwen Realtime"
                )
        if self.qwen_asr_region not in {"beijing", "singapore"}:
            raise ValueError("ESDS_QWEN_ASR_REGION must be beijing or singapore")
        if self.qwen_tts_region not in {"beijing", "singapore"}:
            raise ValueError("ESDS_QWEN_TTS_REGION must be beijing or singapore")
        if self.qwen_realtime_region not in {"beijing", "singapore"}:
            raise ValueError(
                "ESDS_QWEN_REALTIME_REGION must be beijing or singapore"
            )
        if self.vad_stop_dbfs > self.vad_start_dbfs:
            raise ValueError("VAD stop dBFS must not exceed start dBFS")
        if self.vad_stop_snr_db >= self.vad_start_snr_db:
            raise ValueError("VAD stop SNR must be below start SNR")
        if not 0 <= self.emotion_timeout_ms <= 2_000:
            raise ValueError("ESDS_EMOTION_TIMEOUT_MS must be between 0 and 2000")
        if not 1 <= self.max_utterance_seconds <= 120:
            raise ValueError("ESDS_MAX_UTTERANCE_SECONDS must be between 1 and 120")
        if not 1 <= self.sensevoice_threads <= 16:
            raise ValueError("ESDS_SENSEVOICE_THREADS must be between 1 and 16")
        if not 1 <= self.emotion2vec_threads <= 16:
            raise ValueError("ESDS_EMOTION2VEC_THREADS must be between 1 and 16")
        if not 1 <= self.history_turns <= 50:
            raise ValueError("ESDS_HISTORY_TURNS must be between 1 and 50")
        if not 1 <= self.asr_reply_min_chars <= 32:
            raise ValueError("ESDS_ASR_REPLY_MIN_CHARS must be between 1 and 32")
        if not 1 <= self.max_connections <= 10_000:
            raise ValueError("ESDS_MAX_CONNECTIONS must be between 1 and 10000")
        if not 1 <= self.max_queue_frames <= 250:
            raise ValueError("ESDS_MAX_QUEUE_FRAMES must be between 1 and 250")
        if self.max_ws_message_bytes < self.max_audio_message_bytes:
            raise ValueError(
                "ESDS_MAX_WS_MESSAGE_BYTES must be >= ESDS_MAX_AUDIO_MESSAGE_BYTES"
            )
