from __future__ import annotations

import math
import sys
from array import array

from .contracts import AudioFeatures


def pcm16_features(pcm: bytes) -> AudioFeatures:
    if not pcm or len(pcm) % 2:
        raise ValueError("PCM16 audio must contain a non-empty, even number of bytes")
    samples = array("h")
    samples.frombytes(pcm)
    if sys.byteorder != "little":
        samples.byteswap()

    square_sum = 0.0
    peak = 0
    clipped = 0
    crossings = 0
    previous = samples[0]
    for sample in samples:
        absolute = abs(sample)
        peak = max(peak, absolute)
        square_sum += float(sample) * sample
        clipped += int(absolute >= 32_600)
        if (sample >= 0) != (previous >= 0):
            crossings += 1
        previous = sample

    count = len(samples)
    rms = math.sqrt(square_sum / count)
    return AudioFeatures(
        rms_dbfs=_to_dbfs(rms),
        peak_dbfs=_to_dbfs(peak),
        zero_crossing_rate=crossings / max(1, count - 1),
        clipped_ratio=clipped / count,
        sample_count=count,
    )


def pcm16_silence(sample_rate: int = 24_000, frame_ms: int = 20) -> bytes:
    return bytes(sample_rate * frame_ms // 1000 * 2)


def _to_dbfs(value: float) -> float:
    if value <= 0:
        return -96.0
    return max(-96.0, 20.0 * math.log10(value / 32_768.0))
