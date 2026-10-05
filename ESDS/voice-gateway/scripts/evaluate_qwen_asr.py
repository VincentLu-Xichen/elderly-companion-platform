#!/usr/bin/env python3
"""Evaluate Qwen realtime ASR accuracy and post-utterance latency on WAV samples."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import statistics
import sys
import unicodedata
import wave
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from esds_voice.transcription import QwenRealtimeTranscriber


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="用同一批 24/16 kHz 单声道 WAV 评测千问实时 ASR"
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=PROJECT_ROOT / "artifacts/qwen_tts_evaluation_fast/report.json",
        help="包含 samples[].wav/text 的评测清单",
    )
    parser.add_argument("--limit", type=int, default=0, help="仅评测前 N 条，0=全部")
    parser.add_argument(
        "--realtime",
        action="store_true",
        help="按录音原速上传；默认快速上传，只统计停句后的服务延迟",
    )
    parser.add_argument(
        "--context",
        default=os.getenv(
            "ESDS_QWEN_ASR_CONTEXT",
            "ESDS 语音共情 emotion2vec Cherry",
        ),
    )
    return parser.parse_args()


def normalize_text(value: str) -> str:
    return "".join(
        character.lower()
        for character in value
        if not character.isspace()
        and not unicodedata.category(character).startswith(("P", "S"))
    )


def edit_distance(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for row, left_character in enumerate(left, 1):
        current = [row]
        for column, right_character in enumerate(right, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[column] + 1,
                    previous[column - 1] + (left_character != right_character),
                )
            )
        previous = current
    return previous[-1]


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def read_wav(path: Path) -> tuple[bytes, int]:
    with wave.open(str(path), "rb") as source:
        if source.getnchannels() != 1 or source.getsampwidth() != 2:
            raise ValueError(f"{path} 必须是 PCM16 单声道 WAV")
        sample_rate = source.getframerate()
        if sample_rate not in {16_000, 24_000}:
            raise ValueError(f"{path} 采样率必须是 16 或 24 kHz")
        return source.readframes(source.getnframes()), sample_rate


async def run(args: argparse.Namespace) -> None:
    api_key = (os.getenv("DASHSCOPE_API_KEY") or "").strip()
    if not api_key:
        api_key = getpass.getpass(
            "请输入百炼 DASHSCOPE API Key（仅保存在当前进程内）: "
        ).strip()
    if not api_key:
        raise SystemExit("缺少 DASHSCOPE_API_KEY")
    payload = json.loads(args.report.read_text(encoding="utf-8"))
    samples = payload.get("samples") or []
    if args.limit > 0:
        samples = samples[: args.limit]
    if not samples:
        raise SystemExit("评测清单中没有 samples")

    transcriber = QwenRealtimeTranscriber(
        api_key=api_key,
        model=os.getenv("ESDS_QWEN_ASR_MODEL", "qwen3-asr-flash-realtime"),
        region=os.getenv("ESDS_QWEN_ASR_REGION", "beijing"),
        workspace_id=(
            os.getenv("ESDS_QWEN_ASR_WORKSPACE_ID")
            or os.getenv("QWEN_WORKSPACE_ID")
            or None
        ),
        language=os.getenv("ESDS_QWEN_ASR_LANGUAGE", "zh"),
        context=args.context,
    )
    await transcriber.warmup()
    latencies: list[float] = []
    error_rates: list[float] = []
    try:
        for index, sample in enumerate(samples, 1):
            wav = Path(sample["wav"])
            pcm, sample_rate = read_wav(wav)
            frame_bytes = sample_rate * 20 // 1000 * 2
            await transcriber.start_stream(sample_rate)
            for offset in range(0, len(pcm), frame_bytes):
                await transcriber.send_stream_audio(pcm[offset : offset + frame_bytes])
                if args.realtime:
                    await asyncio.sleep(0.02)
            result = await transcriber.finish_stream()
            reference = normalize_text(str(sample["text"]))
            hypothesis = normalize_text("" if result is None else result.text)
            cer = edit_distance(reference, hypothesis) / max(1, len(reference))
            latency = 0.0 if result is None else result.latency_ms
            error_rates.append(cer)
            latencies.append(latency)
            emotion = "" if result is None else result.event
            print(
                f"[{index:02d}] CER={cer:.1%} post_commit={latency:.1f}ms "
                f"emotion={emotion or '-'}\n"
                f"  参考：{sample['text']}\n"
                f"  结果：{'' if result is None else result.text}"
            )
    finally:
        await transcriber.close()

    print(
        "\n汇总："
        f"样本={len(samples)}，平均 CER={statistics.fmean(error_rates):.2%}，"
        f"延迟 P50={percentile(latencies, 0.5):.1f}ms，"
        f"P95={percentile(latencies, 0.95):.1f}ms"
    )


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
