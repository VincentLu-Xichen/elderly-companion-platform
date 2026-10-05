#!/usr/bin/env python3
from __future__ import annotations

import statistics
import time
from array import array

from esds_voice.audio import pcm16_features
from esds_voice.emotion import EmotionTracker
from esds_voice.vad import EnergyVad


def percentile(values: list[float], fraction: float) -> float:
    values = sorted(values)
    return values[min(len(values) - 1, round((len(values) - 1) * fraction))]


def main() -> None:
    frame = array("h", [8000, -8000] * 240).tobytes()
    vad = EnergyVad()
    emotion = EmotionTracker()
    timings = []
    for _ in range(10_000):
        started = time.perf_counter_ns()
        features = pcm16_features(frame)
        vad.update(features)
        emotion.update_audio(features)
        timings.append((time.perf_counter_ns() - started) / 1_000_000)
    print(f"frames=10000 mean_ms={statistics.mean(timings):.4f}")
    print(f"p50_ms={percentile(timings, 0.50):.4f}")
    print(f"p95_ms={percentile(timings, 0.95):.4f}")
    print(f"p99_ms={percentile(timings, 0.99):.4f}")


if __name__ == "__main__":
    main()

