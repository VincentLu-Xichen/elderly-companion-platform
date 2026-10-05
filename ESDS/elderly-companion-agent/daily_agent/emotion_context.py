"""Validated, per-turn voice hints; never arbitrary gateway instructions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from typing import Literal

EmotionLabel = Literal["neutral", "calm", "happy", "excited", "low", "anxious", "angry", "uncertain"]
LABELS = {"neutral", "calm", "happy", "excited", "low", "anxious", "angry", "uncertain"}
EVIDENCE = {
    "positive_words", "negative_words", "anxious_words", "angry_words", "low_energy_words",
    "negated_emotion", "reported_emotion", "past_emotion", "ambiguous_words", "mixed_emotions",
    "repeated_exclamation", "high_energy_voice", "low_energy_voice", "variable_energy",
    "clipping_or_shouting", "interruption",
} | {f"{source}:{label}" for source in ("emotion2vec", "sensevoice", "qwen_realtime") for label in LABELS}


@dataclass(frozen=True)
class VoiceEmotionContext:
    label: EmotionLabel
    confidence: float
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.label not in LABELS or not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise ValueError("Invalid voice emotion hint")
        # Only recognized machine-generated evidence can reach the model or trace.
        object.__setattr__(self, "evidence", tuple(dict.fromkeys(x for x in self.evidence if x in EVIDENCE))[:8])

    def to_dict(self) -> dict:
        return asdict(self)

    def model_message(self) -> str:
        data = self.to_dict()
        data["use_for_tone"] = self.confidence >= 0.35 and self.label not in {"neutral", "uncertain"}
        return (
            "本轮语音辅助线索（仅对应最后一条用户消息，下一轮不能沿用）：\n"
            + json.dumps(data, ensure_ascii=False)
            + "\n这些分数是未经校准的弱线索，不是心理状态事实。可能来自关键词、录音音量或语音模型。"
            "优先理解用户原话、否定、转述和纠正；线索与语义不符时以用户的话为准。"
            "use_for_tone 为 false 时保持自然中性，不据此推断感受；为 true 时也只温和调整措辞。"
            "不要向用户宣读标签或置信度，不编造语气、原因或经历，不因此改变话题或主动塞入建议。"
        )
