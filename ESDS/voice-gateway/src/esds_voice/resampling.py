from __future__ import annotations

from typing import Any


class Pcm24kTo16k:
    """Stateful high-quality PCM16 resampler for Qwen ASR."""

    quality = "soxr-HQ"

    def __init__(self) -> None:
        try:
            import numpy as np
            import soxr
        except ImportError as exc:
            raise RuntimeError("numpy and soxr are required for Qwen ASR") from exc
        self._np = np
        self._soxr = soxr
        self._stream: Any = self._new_stream()

    def _new_stream(self) -> Any:
        return self._soxr.ResampleStream(
            24_000, 16_000, 1, dtype="int16", quality="HQ"
        )

    def process(self, pcm: bytes, *, final: bool = False) -> bytes:
        if len(pcm) % 2:
            raise ValueError("PCM16 audio must contain an even number of bytes")
        samples = self._np.frombuffer(pcm, dtype="<i2")
        converted = self._stream.resample_chunk(samples, last=final)
        if final:
            self._stream = self._new_stream()
        return converted.astype("<i2", copy=False).tobytes()

    def reset(self) -> None:
        """Discard buffered samples and start a clean streaming conversion."""
        self._stream = self._new_stream()
