#!/usr/bin/env python3
"""Evaluate Cherry Qwen realtime TTS latency, intelligibility, and diversity.

The script intentionally uses one shared probe sentence for every emotion.  This
allows the acoustic-diversity summary to compare delivery styles without text
content being the main source of variation.  It does not claim to estimate MOS;
the generated WAV files are the source material for a listening test.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import statistics
import sys
import time
import unicodedata
import wave
from array import array
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from esds_voice.providers.qwen_tts import QwenRealtimeTtsSynthesizer
from esds_voice.transcription import SenseVoiceTranscriber


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_RATE = 24_000
BYTES_PER_SECOND = SAMPLE_RATE * 2
SHARED_PROBE = "我在这里，愿意认真听你说完。"

# The key phrases deliberately exercise every branch in voice_instruction_for().
CASES: dict[str, dict[str, Any]] = {
    "neutral": {
        "instructions": "保持轻松自然，像熟悉的伙伴在近距离聊天。",
        "texts": [SHARED_PROBE, "今天想和我聊点什么？我们慢慢来。"],
    },
    "happy": {
        "instructions": "回应时略带笑意，明亮轻快，但不要夸张。",
        "texts": [SHARED_PROBE, "听到这个好消息，我也跟着开心起来啦！"],
    },
    "low": {
        "instructions": "语速稍慢，温暖轻柔，给对方充分的停顿空间。",
        "texts": [SHARED_PROBE, "累了也没关系，先靠一会儿，我陪着你。"],
    },
    "anxious": {
        "instructions": "降低信息密度，语气安稳确定，不制造紧张感。",
        "texts": [SHARED_PROBE, "先不用一次想完，我们一次只处理一件事。"],
    },
    "angry": {
        "instructions": "不要争辩，保持平稳克制、坚定而不冷淡。",
        "texts": [SHARED_PROBE, "我知道你现在很生气，这件事确实让人难受。"],
    },
    "excited": {
        "instructions": "承接积极情绪，灵动开心，语调上扬但不要大喊。",
        "texts": [SHARED_PROBE, "太棒啦！快告诉我，最让你兴奋的是哪一刻？"],
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="评估阿里百炼 Qwen3-TTS Realtime Cherry 的延时与音色表现"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "artifacts" / "qwen_tts_evaluation",
        help="WAV 和 JSON 报告目录",
    )
    parser.add_argument(
        "--model",
        default="qwen3-tts-instruct-flash-realtime",
    )
    parser.add_argument("--voice", default="Cherry")
    parser.add_argument(
        "--region",
        choices=("beijing", "singapore"),
        default=os.environ.get("ESDS_QWEN_TTS_REGION", "beijing"),
    )
    parser.add_argument(
        "--workspace-id",
        default=os.environ.get("ESDS_QWEN_TTS_WORKSPACE_ID") or None,
    )
    parser.add_argument(
        "--asr-model",
        type=Path,
        default=Path(
            os.environ.get(
                "ESDS_SENSEVOICE_MODEL_DIR",
                PROJECT_ROOT
                / ".models"
                / "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17",
            )
        ),
    )
    parser.add_argument("--no-asr", action="store_true", help="跳过 SenseVoice 回灌")
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="每条 TTS 的最大等待秒数",
    )
    parser.add_argument(
        "--optimize-instructions",
        action="store_true",
        help="开启语气指令语义增强；可能提升表现力，但会显著增加新会话首句延时",
    )
    return parser.parse_args()


def write_wav(path: Path, pcm: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(SAMPLE_RATE)
        target.writeframes(pcm)


def _pcm_samples(pcm: bytes) -> array[int]:
    if len(pcm) % 2:
        raise ValueError("TTS returned an odd number of PCM16 bytes")
    samples = array("h")
    samples.frombytes(pcm)
    if sys.byteorder != "little":
        samples.byteswap()
    return samples


def _dbfs(value: float) -> float:
    return round(20.0 * math.log10(max(value, 1.0) / 32768.0), 2)


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def _pitch_features(samples: array[int]) -> dict[str, float | None]:
    """Return a coarse autocorrelation F0 summary using only the stdlib."""
    frame_size = 960  # 40 ms
    hop = 1_920  # sample every 80 ms; sufficient for an evaluation summary
    min_lag = SAMPLE_RATE // 400
    max_lag = SAMPLE_RATE // 75
    pitches: list[float] = []
    for start in range(0, len(samples) - frame_size + 1, hop):
        raw = samples[start : start + frame_size : 2]
        mean = sum(raw) / len(raw)
        frame = [float(value) - mean for value in raw]
        energy = sum(value * value for value in frame)
        if energy / len(frame) < 180.0**2:
            continue
        best_lag = 0
        best_correlation = 0.0
        for source_lag in range(min_lag, max_lag + 1, 2):
            lag = max(1, source_lag // 2)
            left = frame[:-lag]
            right = frame[lag:]
            numerator = sum(a * b for a, b in zip(left, right))
            left_energy = sum(value * value for value in left)
            right_energy = sum(value * value for value in right)
            denominator = math.sqrt(left_energy * right_energy)
            correlation = numerator / denominator if denominator else 0.0
            if correlation > best_correlation:
                best_correlation = correlation
                best_lag = lag
        if best_lag and best_correlation >= 0.35:
            pitches.append((SAMPLE_RATE / 2) / best_lag)
    if not pitches:
        return {"f0_median_hz": None, "f0_p10_hz": None, "f0_p90_hz": None}
    return {
        "f0_median_hz": round(statistics.median(pitches), 1),
        "f0_p10_hz": round(float(_percentile(pitches, 0.1)), 1),
        "f0_p90_hz": round(float(_percentile(pitches, 0.9)), 1),
    }


def acoustic_features(pcm: bytes, text: str) -> dict[str, float | None]:
    samples = _pcm_samples(pcm)
    if not samples:
        raise ValueError("TTS returned empty audio")
    squares = sum(int(value) * int(value) for value in samples)
    rms = math.sqrt(squares / len(samples))
    peak = max(abs(value) for value in samples)
    clipping = sum(abs(value) >= 32_760 for value in samples) / len(samples)
    crossings = sum(
        (left < 0 <= right) or (right < 0 <= left)
        for left, right in zip(samples, samples[1:])
        if abs(left) > 64 or abs(right) > 64
    )
    frame_size = 480  # 20 ms
    frame_rms: list[float] = []
    for start in range(0, len(samples), frame_size):
        frame = samples[start : start + frame_size]
        if not frame:
            continue
        frame_rms.append(
            math.sqrt(sum(int(value) * int(value) for value in frame) / len(frame))
        )
    silence_threshold = 32768.0 * 10 ** (-42.0 / 20.0)
    silence_ratio = sum(value < silence_threshold for value in frame_rms) / max(
        1, len(frame_rms)
    )
    active_db = [_dbfs(value) for value in frame_rms if value >= silence_threshold]
    energy_variation = statistics.pstdev(active_db) if len(active_db) > 1 else 0.0
    duration = len(samples) / SAMPLE_RATE
    visible_chars = len(normalize_text(text))
    result: dict[str, float | None] = {
        "duration_seconds": round(duration, 3),
        "characters_per_second": round(visible_chars / duration, 2),
        "rms_dbfs": _dbfs(rms),
        "peak_dbfs": _dbfs(float(peak)),
        "clipping_ratio": round(clipping, 6),
        "silence_ratio": round(silence_ratio, 4),
        "zero_crossings_per_second": round(crossings / duration, 1),
        "energy_variation_db": round(energy_variation, 2),
    }
    result.update(_pitch_features(samples))
    return result


def normalize_text(text: str) -> str:
    return "".join(
        character.casefold()
        for character in unicodedata.normalize("NFKC", text)
        if unicodedata.category(character)[0] in {"L", "N"}
    )


def character_error_rate(reference: str, hypothesis: str) -> float:
    expected = normalize_text(reference)
    actual = normalize_text(hypothesis)
    if not expected:
        return 0.0 if not actual else 1.0
    previous = list(range(len(actual) + 1))
    for row, expected_char in enumerate(expected, start=1):
        current = [row]
        for column, actual_char in enumerate(actual, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[column] + 1,
                    previous[column - 1] + (expected_char != actual_char),
                )
            )
        previous = current
    return previous[-1] / len(expected)


def load_asr(args: argparse.Namespace) -> tuple[SenseVoiceTranscriber | None, str | None]:
    if args.no_asr:
        return None, "disabled by --no-asr"
    root = args.asr_model.expanduser().resolve()
    model_exists = (root / "model.int8.onnx").is_file() or (
        root / "model.onnx"
    ).is_file()
    if not model_exists or not (root / "tokens.txt").is_file():
        return None, f"SenseVoice model not found at {root}"
    try:
        transcriber = SenseVoiceTranscriber(root, num_threads=2)
        transcriber.warmup()
        return transcriber, None
    except (ImportError, RuntimeError, ValueError) as exc:
        return None, f"SenseVoice unavailable: {exc}"


def _mean(values: list[float]) -> float | None:
    return None if not values else round(statistics.fmean(values), 3)


def metric_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    fields = ("connection_ms", "ttfa_ms", "total_ms", "rtf")
    summary: dict[str, Any] = {}
    for field in fields:
        values = [float(item[field]) for item in results if item.get(field) is not None]
        summary[field] = {
            "mean": _mean(values),
            "p50": None if not values else round(float(_percentile(values, 0.5)), 3),
            "p95": None if not values else round(float(_percentile(values, 0.95)), 3),
            "max": None if not values else round(max(values), 3),
        }
    cer_values = [float(item["cer"]) for item in results if item.get("cer") is not None]
    summary["cer"] = {
        "mean": _mean(cer_values),
        "p95": None if not cer_values else round(float(_percentile(cer_values, 0.95)), 4),
    }
    summary["quality_gate"] = {
        "no_clipping": all(
            item["acoustics"]["clipping_ratio"] <= 0.001 for item in results
        ),
        "no_excessive_silence": all(
            item["acoustics"]["silence_ratio"] <= 0.55 for item in results
        ),
        "asr_mean_cer_le_0_15": None
        if not cer_values
        else statistics.fmean(cer_values) <= 0.15,
    }
    return summary


def diversity_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    probes = [item for item in results if item["probe"] == "shared"]
    dimensions = (
        "characters_per_second",
        "rms_dbfs",
        "energy_variation_db",
        "zero_crossings_per_second",
        "f0_median_hz",
        "f0_p90_hz",
    )
    profiles = {
        item["emotion"]: {
            name: item["acoustics"].get(name) for name in dimensions
        }
        for item in probes
    }
    usable = [
        name
        for name in dimensions
        if all(profile.get(name) is not None for profile in profiles.values())
        and statistics.pstdev(float(profile[name]) for profile in profiles.values()) > 0
    ]
    standardized: dict[str, list[float]] = {}
    for emotion, profile in profiles.items():
        vector: list[float] = []
        for name in usable:
            values = [float(candidate[name]) for candidate in profiles.values()]
            vector.append(
                (float(profile[name]) - statistics.fmean(values))
                / statistics.pstdev(values)
            )
        standardized[emotion] = vector
    distances: list[float] = []
    names = list(standardized)
    for left_index, left_name in enumerate(names):
        for right_name in names[left_index + 1 :]:
            left = standardized[left_name]
            right = standardized[right_name]
            if left:
                distances.append(
                    math.sqrt(
                        sum((a - b) ** 2 for a, b in zip(left, right)) / len(left)
                    )
                )
    return {
        "method": (
            "相同文案跨情绪的标准化声学特征距离；仅衡量可区分度，不等同于主观自然度/MOS"
        ),
        "features": usable,
        "emotion_profiles": profiles,
        "mean_pairwise_distance": _mean(distances),
        "minimum_pairwise_distance": None
        if not distances
        else round(min(distances), 3),
    }


async def render_one(
    synthesizer: QwenRealtimeTtsSynthesizer,
    *,
    emotion: str,
    sample_index: int,
    text: str,
    instructions: str,
    output_dir: Path,
    timeout: float,
    transcriber: SenseVoiceTranscriber | None,
) -> dict[str, Any]:
    await asyncio.wait_for(synthesizer.prepare(instructions), timeout=timeout)

    async def collect() -> bytes:
        chunks = [
            chunk
            async for chunk in synthesizer.stream_pcm24k(
                text,
                instructions=instructions,
            )
            if chunk
        ]
        return b"".join(chunks)

    pcm = await asyncio.wait_for(collect(), timeout=timeout)
    if not pcm:
        raise RuntimeError(f"{emotion}-{sample_index}: Qwen TTS returned no audio")
    metrics = synthesizer.last_metrics
    if metrics is None:
        raise RuntimeError(f"{emotion}-{sample_index}: TTS metrics were not recorded")
    filename = f"{emotion}_{sample_index:02d}_{'shared' if sample_index == 1 else 'response'}.wav"
    wav_path = output_dir / filename
    write_wav(wav_path, pcm)
    acoustics = acoustic_features(pcm, text)
    audio_seconds = len(pcm) / BYTES_PER_SECOND
    result: dict[str, Any] = {
        "emotion": emotion,
        "sample_index": sample_index,
        "probe": "shared" if sample_index == 1 else "response",
        "text": text,
        "instructions": instructions,
        "wav": str(wav_path.resolve()),
        **asdict(metrics),
        "audio_seconds": round(audio_seconds, 3),
        "rtf": round((metrics.total_ms / 1000.0) / audio_seconds, 4),
        "bytes": len(pcm),
        "acoustics": acoustics,
        "asr_text": None,
        "asr_latency_ms": None,
        "cer": None,
    }
    if transcriber is not None:
        asr_started = time.perf_counter()
        transcription = await asyncio.to_thread(
            transcriber.transcribe_pcm16,
            pcm,
            SAMPLE_RATE,
        )
        result["asr_latency_ms"] = round(
            (time.perf_counter() - asr_started) * 1000,
            1,
        )
        hypothesis = "" if transcription is None else transcription.text
        result["asr_text"] = hypothesis
        result["cer"] = round(character_error_rate(text, hypothesis), 4)
    return result


async def evaluate(args: argparse.Namespace, api_key: str) -> dict[str, Any]:
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    transcriber, asr_note = load_asr(args)
    synthesizer = QwenRealtimeTtsSynthesizer(
        api_key=api_key,
        model=args.model,
        voice=args.voice,
        region=args.region,
        workspace_id=args.workspace_id,
        optimize_instructions=args.optimize_instructions,
    )
    results: list[dict[str, Any]] = []
    started = time.perf_counter()
    try:
        for emotion, case in CASES.items():
            for sample_index, text in enumerate(case["texts"], start=1):
                item = await render_one(
                    synthesizer,
                    emotion=emotion,
                    sample_index=sample_index,
                    text=text,
                    instructions=case["instructions"],
                    output_dir=output_dir,
                    timeout=args.timeout,
                    transcriber=transcriber,
                )
                results.append(item)
                print(json.dumps({"sample": item}, ensure_ascii=False), flush=True)
    finally:
        await synthesizer.close()
    report = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model": args.model,
        "voice": args.voice,
        "region": args.region,
        "optimize_instructions": args.optimize_instructions,
        "sample_rate_hz": SAMPLE_RATE,
        "format": "PCM16 mono WAV",
        "sample_count": len(results),
        "wall_time_seconds": round(time.perf_counter() - started, 3),
        "asr": {
            "enabled": transcriber is not None,
            "model_dir": str(args.asr_model.expanduser().resolve()),
            "note": asr_note,
        },
        "summary": metric_summary(results),
        "diversity": diversity_summary(results),
        "samples": results,
        "interpretation": {
            "ttfa": "提交文本到收到首个 PCM 音频块，不含用户录音和上游 ASR/LLM",
            "connection_ms": "首次连接或因情绪指令改变而重建 WebSocket 会话的时间",
            "rtf": "TTS 总生成时间 / 输出音频时长；小于 1 表示快于实时播放",
            "quality": "CER/削波/静音为自动指标；自然度与角色贴合度仍需对 WAV 做盲听",
        },
    }
    report_path = output_dir / "report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "report": str(report_path),
                "summary": report["summary"],
                "diversity": report["diversity"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return report


def main() -> None:
    args = parse_args()
    api_key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    if not api_key:
        raise SystemExit(
            "缺少 DASHSCOPE_API_KEY。请先执行：\n"
            "  export DASHSCOPE_API_KEY='你的阿里百炼 API Key'\n"
            "然后重新运行本评估脚本；API Key 不会写入报告。"
        )
    try:
        asyncio.run(evaluate(args, api_key))
    except KeyboardInterrupt:
        raise SystemExit("评估已由用户中止。") from None
    except Exception as exc:
        raise SystemExit(f"Qwen TTS 评估失败：{exc}") from exc


if __name__ == "__main__":
    main()
