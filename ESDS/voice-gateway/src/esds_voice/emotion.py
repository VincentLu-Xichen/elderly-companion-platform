from __future__ import annotations

import re
import time
import math
from collections import deque
from typing import Iterable

from .contracts import AudioFeatures, EmotionSnapshot
from .lexical_emotion import lexical_signals


class EmotionTracker:
    """Fuses acoustic, lexical, and interaction weak signals.

    This intentionally emits coarse states. It is an interaction hint, not a
    psychological diagnosis.
    """

    _POSITIVE = {
        "开心",
        "高兴",
        "喜欢",
        "太棒",
        "不错",
        "期待",
        "幸福",
        "哈哈",
        "happy",
        "great",
        "excited",
        "love",
    }
    _NEGATIVE = {
        "难过",
        "伤心",
        "失望",
        "讨厌",
        "糟糕",
        "痛苦",
        "没劲",
        "烦",
        "sad",
        "upset",
        "awful",
        "hate",
    }
    _ANXIOUS = {
        "焦虑",
        "紧张",
        "担心",
        "害怕",
        "怎么办",
        "来不及",
        "anxious",
        "worried",
        "nervous",
        "afraid",
    }
    _ANGRY = {
        "生气",
        "愤怒",
        "闭嘴",
        "够了",
        "烦死",
        "气死",
        "angry",
        "furious",
        "shut up",
    }
    _LOW_ENERGY = {
        "累",
        "困",
        "疲惫",
        "没精神",
        "不想动",
        "tired",
        "exhausted",
    }

    def __init__(self, *, window_frames: int = 60, smoothing: float = 0.22) -> None:
        self._audio: deque[AudioFeatures] = deque(maxlen=window_frames)
        self._valence = 0.0
        self._arousal = 0.0
        self._confidence = 0.0
        self._text_valence = 0.0
        self._text_arousal = 0.0
        self._text_evidence: tuple[str, ...] = ()
        self._interaction_arousal = 0.0
        self._model_label: str | None = None
        self._model_evidence: tuple[str, ...] = ()
        self._smoothing = smoothing
        self._last_label = "neutral"
        self._model_confidence = 0.0
        self._current = EmotionSnapshot(0.0, 0.0, "neutral", 0.0, ())

    def update_audio(self, features: AudioFeatures) -> EmotionSnapshot:
        self._audio.append(features)
        return self._recompute()

    def begin_turn(self) -> None:
        self._audio.clear()
        self._valence = self._arousal = self._confidence = 0.0
        self._interaction_arousal = 0.0
        self._last_label = "neutral"
        self._model_confidence = 0.0
        self._current = EmotionSnapshot(0.0, 0.0, "neutral", 0.0, ())
        self._text_valence = 0.0
        self._text_arousal = 0.0
        self._text_evidence = ()
        self._model_label = None
        self._model_evidence = ()

    def update_text(self, text: str) -> EmotionSnapshot:
        normalized = re.sub(r"\s+", " ", text.lower()).strip()
        counts, qualifiers = lexical_signals(normalized, {
            "positive": self._POSITIVE, "negative": self._NEGATIVE,
            "anxious": self._ANXIOUS, "angry": self._ANGRY, "tired": self._LOW_ENERGY,
        })
        positive, negative, anxious, angry, tired = (counts[key] for key in ("positive", "negative", "anxious", "angry", "tired"))

        valence = 0.35 * positive - 0.32 * negative - 0.25 * anxious - 0.42 * angry
        arousal = 0.25 * positive + 0.38 * anxious + 0.48 * angry - 0.30 * tired
        evidence: list[str] = []
        if positive:
            evidence.append("positive_words")
        if negative:
            evidence.append("negative_words")
        if anxious:
            evidence.append("anxious_words")
        if angry:
            evidence.append("angry_words")
        if tired:
            evidence.append("low_energy_words")
        if normalized.count("!") + normalized.count("！") >= 2:
            arousal += 0.18
            evidence.append("repeated_exclamation")
        evidence.extend(qualifiers)

        self._text_valence = _clamp(valence)
        self._text_arousal = _clamp(arousal)
        self._text_evidence = tuple(evidence)
        return self._recompute()

    def note_interruption(self) -> EmotionSnapshot:
        self._interaction_arousal = min(0.55, self._interaction_arousal + 0.16)
        return self._recompute(extra_evidence=("interruption",))

    def update_model(
        self, label: str, *, source: str, confidence: float | None = None
    ) -> EmotionSnapshot:
        if label not in {
            "neutral",
            "calm",
            "happy",
            "excited",
            "low",
            "anxious",
            "angry",
            "uncertain",
        }:
            raise ValueError(f"unsupported model emotion: {label}")
        if confidence is not None and (not math.isfinite(confidence) or not 0 <= confidence <= 1):
            raise ValueError("model confidence must be finite and between 0 and 1")
        self._model_label = label
        self._model_evidence = (f"{source}:{label}",)
        # Model scores are useful ranking signals but are not assumed to be
        # perfectly calibrated across speakers and recording environments.
        if confidence is None:
            model_confidence = 0.46 if label == "neutral" else 0.56
        else:
            model_confidence = min(0.82, confidence)
        self._model_confidence = model_confidence
        return self._recompute(extra_evidence=self._model_evidence)

    def snapshot(self) -> EmotionSnapshot:
        return self._current

    def _recompute(self, extra_evidence: Iterable[str] = ()) -> EmotionSnapshot:
        acoustic_valence = 0.0
        acoustic_arousal = 0.0
        evidence = list(self._text_evidence)
        evidence.extend(self._model_evidence)
        if self._audio:
            levels = [item.rms_dbfs for item in self._audio]
            zcrs = [item.zero_crossing_rate for item in self._audio]
            mean_level = sum(levels) / len(levels)
            dynamic_range = max(levels) - min(levels)
            mean_zcr = sum(zcrs) / len(zcrs)
            if mean_level > -24:
                acoustic_arousal += 0.52
                evidence.append("high_energy_voice")
            elif mean_level > -34:
                acoustic_arousal += 0.24
            elif mean_level < -48:
                acoustic_arousal -= 0.30
                evidence.append("low_energy_voice")
            if dynamic_range > 17:
                acoustic_arousal += 0.18
                evidence.append("variable_energy")
            if mean_zcr > 0.24:
                acoustic_arousal += 0.10
            if any(item.clipped_ratio > 0.02 for item in self._audio):
                acoustic_arousal += 0.16
                acoustic_valence -= 0.08
                evidence.append("clipping_or_shouting")

        target_valence = 0.62 * self._text_valence + 0.38 * acoustic_valence
        target_arousal = (
            0.52 * acoustic_arousal
            + 0.38 * self._text_arousal
            + 0.10 * self._interaction_arousal
        )
        alpha = self._smoothing
        self._valence = _clamp((1 - alpha) * self._valence + alpha * target_valence)
        self._arousal = _clamp((1 - alpha) * self._arousal + alpha * target_arousal)
        # A conservative reliability hint, not an accuracy probability. Frame
        # count and repeated evidence must not inflate confidence. Audio level
        # alone is weak because distance and automatic gain alter it.
        lexical = any(item.endswith("_words") and item != "ambiguous_words" for item in self._text_evidence)
        self._confidence = max(0.45 if lexical else 0.18, self._model_confidence)
        if "ambiguous_words" in self._text_evidence or "mixed_emotions" in self._text_evidence:
            self._confidence = min(self._confidence, 0.30)
        evidence.extend(extra_evidence)
        self._interaction_arousal *= 0.97
        self._current = self._snapshot(tuple(dict.fromkeys(evidence)))
        return self._current

    def _snapshot(self, evidence: tuple[str, ...]) -> EmotionSnapshot:
        lexical_label = _label(0.62 * self._text_valence, 0.38 * self._text_arousal, self._text_evidence)
        explicit = any(item.endswith("_words") and item != "ambiguous_words" for item in self._text_evidence)
        ambiguous = "ambiguous_words" in self._text_evidence or "mixed_emotions" in self._text_evidence
        candidate = lexical_label if explicit or ambiguous else _label(0.0, self._arousal, ())
        if self._model_label is not None and self._model_confidence >= 0.35:
            if ambiguous:
                candidate = "uncertain"
            elif not explicit:
                candidate = self._model_label
                if "negated_emotion" in self._text_evidence and self._model_label not in {"neutral", "calm"}:
                    candidate = "uncertain"
                    self._confidence = min(self._confidence, 0.30)
            elif self._model_label == "neutral":
                candidate = lexical_label
            elif lexical_label == self._model_label:
                candidate = self._model_label
                self._confidence = max(self._confidence, 0.60)
            elif _polarity(lexical_label) != _polarity(self._model_label):
                # Conflicting words/prosody are common (sarcasm, masking, model
                # error). A cautious label gives the response policy room to
                # acknowledge without asserting an emotion as fact.
                candidate = "uncertain"
                self._confidence = min(self._confidence, 0.30)
            else:
                candidate = lexical_label
        self._last_label = candidate
        return EmotionSnapshot(
            valence=round(self._valence, 3),
            arousal=round(self._arousal, 3),
            label=candidate,
            confidence=round(_clamp(self._confidence, 0.0, 1.0), 3),
            evidence=evidence[:6],
            updated_at_ms=time.time_ns() // 1_000_000,
        )


def _label(valence: float, arousal: float, text_evidence: tuple[str, ...]) -> str:
    signals = set(text_evidence)
    if "ambiguous_words" in signals or "mixed_emotions" in signals:
        return "uncertain"
    if "angry_words" in signals:
        return "angry"
    if "anxious_words" in signals:
        return "anxious"
    if "low_energy_words" in signals and valence <= 0.02:
        return "low"
    if "negative_words" in signals:
        return "low"
    if "positive_words" in signals:
        return "excited" if arousal >= 0.12 else "happy"
    if valence <= -0.13 and arousal >= 0.18:
        return "angry"
    if valence <= -0.10 and arousal > 0.03:
        return "anxious"
    if valence <= -0.10 or ("low_energy_words" in signals and arousal < 0.12):
        return "low"
    if valence >= 0.11 and arousal >= 0.12:
        return "excited"
    if valence >= 0.10:
        return "happy"
    if abs(valence) < 0.10 and abs(arousal) < 0.16:
        return "neutral"
    return "calm" if arousal < 0 else "uncertain"


def _polarity(label: str) -> int:
    if label in {"happy", "excited"}:
        return 1
    if label in {"low", "anxious", "angry"}:
        return -1
    return 0


def _clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return min(high, max(low, value))
