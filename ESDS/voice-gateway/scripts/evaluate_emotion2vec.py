#!/usr/bin/env python3
"""Evaluate emotion2vec+ on labelled RAVDESS WAV files."""

from __future__ import annotations

import argparse
import statistics
import wave
from collections import Counter, defaultdict
from pathlib import Path

from esds_voice.emotion_backends import Emotion2VecAnalyzer


RAVDESS_LABELS = {
    1: "neutral",
    2: "neutral",
    3: "happy",
    4: "low",
    5: "angry",
    6: "anxious",
    7: "angry",
    8: "excited",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("model_dir", type=Path)
    parser.add_argument("audio_root", type=Path)
    parser.add_argument("--per-label", type=int, default=5)
    parser.add_argument("--threads", type=int, default=4)
    return parser.parse_args()


def read_pcm16(path: Path) -> tuple[bytes, int]:
    with wave.open(str(path), "rb") as wav:
        if wav.getsampwidth() != 2 or wav.getnchannels() != 1:
            raise ValueError(f"expected mono PCM16 WAV: {path}")
        return wav.readframes(wav.getnframes()), wav.getframerate()


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))]


def main() -> None:
    args = parse_args()
    analyzer = Emotion2VecAnalyzer(args.model_dir, num_threads=args.threads)
    analyzer.warmup()
    selected: list[tuple[Path, str]] = []
    counts: Counter[str] = Counter()
    for path in sorted(args.audio_root.rglob("*.wav")):
        parts = path.stem.split("-")
        if len(parts) != 7:
            continue
        expected = RAVDESS_LABELS.get(int(parts[2]))
        if expected is None:
            continue
        if args.per_label and counts[expected] >= args.per_label:
            continue
        counts[expected] += 1
        selected.append((path, expected))

    if not selected:
        raise SystemExit("no RAVDESS-labelled WAV files found")

    confusion: dict[str, Counter[str]] = defaultdict(Counter)
    latencies: list[float] = []
    confidences: list[float] = []
    correct = 0
    for path, expected in selected:
        pcm, sample_rate = read_pcm16(path)
        result = analyzer.analyze_pcm16(pcm, sample_rate)
        predicted = result.label if result is not None else "unknown"
        confusion[expected][predicted] += 1
        correct += int(predicted == expected)
        if result is not None:
            latencies.append(result.latency_ms)
            if result.confidence is not None:
                confidences.append(result.confidence)

    labels = sorted({expected for _, expected in selected})
    print(f"samples={len(selected)} accuracy={correct / len(selected):.3f}")
    print(
        "latency_ms "
        f"mean={statistics.fmean(latencies):.1f} "
        f"p95={percentile(latencies, 0.95):.1f} "
        f"max={max(latencies, default=0):.1f}"
    )
    if confidences:
        print(
            "confidence "
            f"mean={statistics.fmean(confidences):.3f} "
            f"p05={percentile(confidences, 0.05):.3f}"
        )
    print("expected -> predictions")
    for label in labels:
        row = confusion[label]
        recall = row[label] / sum(row.values())
        rendered = ", ".join(f"{name}:{count}" for name, count in sorted(row.items()))
        print(f"{label:8s} recall={recall:.3f} {rendered}")


if __name__ == "__main__":
    main()
