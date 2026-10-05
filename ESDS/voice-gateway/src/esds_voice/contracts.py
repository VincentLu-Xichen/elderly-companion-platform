from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal


@dataclass(frozen=True, slots=True)
class AudioFeatures:
    rms_dbfs: float
    peak_dbfs: float
    zero_crossing_rate: float
    clipped_ratio: float
    sample_count: int


@dataclass(frozen=True, slots=True)
class AsrResult:
    text: str
    language: str = ""
    event: str = ""
    latency_ms: float = 0.0


@dataclass(frozen=True, slots=True)
class ModelEmotion:
    label: str
    source: str
    raw_label: str
    latency_ms: float
    confidence: float | None = None
    transcript: str = ""
    language: str = ""
    event: str = ""


@dataclass(frozen=True, slots=True)
class EmotionSnapshot:
    valence: float
    arousal: float
    label: str
    confidence: float
    evidence: tuple[str, ...]
    updated_at_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        body = asdict(self)
        body["evidence"] = list(self.evidence)
        return body


@dataclass(frozen=True, slots=True)
class EmpathyDecision:
    emotion: EmotionSnapshot
    content_instructions: str
    delivery_instructions: str


@dataclass(frozen=True, slots=True)
class UnderstoodTurn:
    transcript: AsrResult
    emotion: EmotionSnapshot


@dataclass(frozen=True, slots=True)
class AssistantEvent:
    type: Literal["text.delta", "text.done", "audio.delta"]
    text: str | None = None
    audio: bytes | None = None
