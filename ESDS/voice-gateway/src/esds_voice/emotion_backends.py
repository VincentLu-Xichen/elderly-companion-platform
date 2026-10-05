from __future__ import annotations

import contextlib
import io
import logging
import threading
import time
from math import gcd
from pathlib import Path
from typing import Protocol

from .contracts import ModelEmotion

logger = logging.getLogger(__name__)


class EmotionAnalyzer(Protocol):
    def analyze_pcm16(self, pcm: bytes, sample_rate: int) -> ModelEmotion | None: ...


class DisabledEmotionAnalyzer:
    def analyze_pcm16(self, pcm: bytes, sample_rate: int) -> ModelEmotion | None:
        return None


_SENSEVOICE_LABELS = {
    "NEUTRAL": "neutral",
    "HAPPY": "happy",
    "SAD": "low",
    "ANGRY": "angry",
    "FEARFUL": "anxious",
    "FEAR": "anxious",
    "DISGUSTED": "angry",
    "DISGUST": "angry",
    "SURPRISED": "excited",
    "SURPRISE": "excited",
}


def normalize_sensevoice_emotion(raw: str) -> str | None:
    normalized = raw.strip().upper().replace("<|", "").replace("|>", "")
    return _SENSEVOICE_LABELS.get(normalized)


class SenseVoiceEmotionAnalyzer:
    """Local utterance-level SenseVoice inference through sherpa-onnx.

    Model initialization is lazy so the gateway can start and report a clear
    error only when this optional backend is actually selected. A lock protects
    the shared recognizer because sherpa-onnx decode calls are not documented as
    safe for concurrent use.
    """

    def __init__(self, model_dir: str | Path, *, num_threads: int = 2) -> None:
        root = Path(model_dir).expanduser().resolve()
        model = root / "model.int8.onnx"
        if not model.is_file():
            model = root / "model.onnx"
        tokens = root / "tokens.txt"
        if not model.is_file() or not tokens.is_file():
            raise ValueError(
                f"SenseVoice model directory must contain model.int8.onnx/model.onnx "
                f"and tokens.txt: {root}"
            )
        self.model_path = model
        self.tokens_path = tokens
        self.num_threads = max(1, num_threads)
        self._recognizer = None
        self._lock = threading.Lock()

    def _get_recognizer(self):
        if self._recognizer is None:
            try:
                import sherpa_onnx
            except ImportError as exc:  # pragma: no cover - depends on optional extra
                raise RuntimeError(
                    "Install the local-emotion extra: pip install -e '.[local-emotion]'"
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

    def analyze_pcm16(self, pcm: bytes, sample_rate: int) -> ModelEmotion | None:
        if not pcm or len(pcm) % 2:
            return None
        try:
            import numpy as np
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise RuntimeError(
                "Install the local-emotion extra: pip install -e '.[local-emotion]'"
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
        raw_label = str(getattr(result, "emotion", "") or "")
        label = normalize_sensevoice_emotion(raw_label)
        if label is None:
            return None
        return ModelEmotion(
            label=label,
            source="sensevoice",
            raw_label=raw_label,
            latency_ms=latency_ms,
            transcript=str(getattr(result, "text", "") or ""),
            language=str(getattr(result, "lang", "") or ""),
            event=str(getattr(result, "event", "") or ""),
        )


_EMOTION2VEC_LABELS = {
    "ANGRY": "angry",
    "DISGUSTED": "angry",
    "DISGUST": "angry",
    "FEARFUL": "anxious",
    "FEAR": "anxious",
    "HAPPY": "happy",
    "NEUTRAL": "neutral",
    "SAD": "low",
    "SURPRISED": "excited",
    "SURPRISE": "excited",
}


def normalize_emotion2vec_label(raw: str) -> str | None:
    # Official labels are bilingual strings such as ``生气/angry``.
    normalized = raw.rsplit("/", 1)[-1].strip().upper()
    return _EMOTION2VEC_LABELS.get(normalized)


class Emotion2VecAnalyzer:
    """Local 9-class speech-emotion inference through FunASR.

    emotion2vec+ requires 16 kHz input while the device protocol is fixed at
    24 kHz, so resampling happens only once after utterance endpointing.
    """

    def __init__(self, model_dir: str | Path, *, num_threads: int = 4) -> None:
        root = Path(model_dir).expanduser().resolve()
        if not (root / "model.pt").is_file() or not (root / "config.yaml").is_file():
            raise ValueError(
                f"emotion2vec model directory must contain model.pt and config.yaml: {root}"
            )
        self.model_dir = root
        self.num_threads = max(1, num_threads)
        self._model = None
        self._lock = threading.Lock()

    def _get_model(self):
        if self._model is None:
            try:
                from funasr import AutoModel
            except ImportError as exc:  # pragma: no cover - optional extra
                raise RuntimeError(
                    "Install the emotion2vec extra: pip install -e '.[emotion2vec]'"
                ) from exc
            # FunASR currently prints every checkpoint key during model load.
            # Capture that framework noise while preserving raised exceptions.
            captured = io.StringIO()
            root_logger = logging.getLogger()
            previous_level = root_logger.level
            try:
                root_logger.setLevel(logging.ERROR)
                with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
                    self._model = AutoModel(
                        model=str(self.model_dir),
                        device="cpu",
                        ncpu=self.num_threads,
                        disable_update=True,
                        disable_pbar=True,
                        disable_log=True,
                        log_level="ERROR",
                    )
            finally:
                root_logger.setLevel(previous_level)
            output = captured.getvalue().strip()
            if output:
                logger.debug("FunASR model-load output: %s", output[-2_000:])
        return self._model

    def warmup(self) -> None:
        try:
            import numpy as np
        except ImportError as exc:  # pragma: no cover - optional extra
            raise RuntimeError(
                "Install the emotion2vec extra: pip install -e '.[emotion2vec]'"
            ) from exc
        with self._lock:
            self._get_model().generate(
                input=np.zeros(8_000, dtype=np.float32),
                granularity="utterance",
                extract_embedding=False,
            )

    def analyze_pcm16(self, pcm: bytes, sample_rate: int) -> ModelEmotion | None:
        if not pcm or len(pcm) % 2:
            return None
        try:
            import numpy as np
            from scipy.signal import resample_poly
        except ImportError as exc:  # pragma: no cover - optional extra
            raise RuntimeError(
                "Install the emotion2vec extra: pip install -e '.[emotion2vec]'"
            ) from exc

        samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
        if sample_rate != 16_000:
            divisor = gcd(sample_rate, 16_000)
            samples = resample_poly(samples, 16_000 // divisor, sample_rate // divisor)

        started = time.perf_counter()
        with self._lock:
            rows = self._get_model().generate(
                input=samples,
                granularity="utterance",
                extract_embedding=False,
            )
        latency_ms = (time.perf_counter() - started) * 1000
        if not rows:
            return None
        labels = rows[0].get("labels") or []
        scores = rows[0].get("scores") or []
        if not labels or len(labels) != len(scores):
            return None
        best_index = max(range(len(scores)), key=lambda index: float(scores[index]))
        raw_label = str(labels[best_index])
        label = normalize_emotion2vec_label(raw_label)
        if label is None:
            return None
        confidence = min(1.0, max(0.0, float(scores[best_index])))
        return ModelEmotion(
            label=label,
            source="emotion2vec",
            raw_label=raw_label,
            latency_ms=latency_ms,
            confidence=confidence,
        )
