"""Optional gateway speech enhancement before VAD / ASR.

Backends:
- rnnoise: pyrnnoise when importable (often blocked by audiolab/av conflicts)
- spectral: lightweight numpy spectral gate (always available with numpy)

Default create path tries rnnoise first, then spectral, so enhancement stays on
even when native RNNoise wheels are broken.
"""

from __future__ import annotations

import logging
from typing import Protocol

import numpy as np

logger = logging.getLogger(__name__)

_RNNOISE_RATE = 48_000


class SpeechEnhancer(Protocol):
    def process(self, pcm16: bytes) -> bytes: ...


class IdentityEnhancer:
    """No-op enhancer used when enhancement is unavailable."""

    def process(self, pcm16: bytes) -> bytes:
        return pcm16


class SpectralGateEnhancer:
    """Simple per-frame spectral noise gate (numpy only).

    Tracks a slow noise floor magnitude and attenuates bins near that floor.
    Good enough for fan / room hiss; not a substitute for speaker separation.
    """

    def __init__(self, *, sample_rate: int = 24_000) -> None:
        self._sample_rate = sample_rate
        self._noise_mag: np.ndarray | None = None
        self._warned = False

    def process(self, pcm16: bytes) -> bytes:
        if not pcm16:
            return pcm16
        try:
            mono = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32)
            if mono.size < 8:
                return pcm16
            # Hann window reduces spectral leakage for short 20 ms frames.
            window = np.hanning(mono.size).astype(np.float32)
            spectrum = np.fft.rfft(mono * window)
            mag = np.abs(spectrum)
            if self._noise_mag is None or self._noise_mag.shape != mag.shape:
                self._noise_mag = mag.copy()
            else:
                # Slow adapt toward quieter frames.
                alpha = 0.05 if float(np.mean(mag)) < float(np.mean(self._noise_mag)) * 1.35 else 0.01
                self._noise_mag = (1.0 - alpha) * self._noise_mag + alpha * mag
            # Soft mask: keep speech peaks, pull down near-noise bins.
            eps = 1e-6
            snr = mag / (self._noise_mag + eps)
            mask = np.clip((snr - 1.2) / 2.5, 0.15, 1.0)
            cleaned = np.fft.irfft(spectrum * mask, n=mono.size)
            # Match energy roughly so VAD thresholds stay stable.
            in_rms = float(np.sqrt(np.mean(mono * mono)) + eps)
            out_rms = float(np.sqrt(np.mean(cleaned * cleaned)) + eps)
            cleaned *= in_rms / out_rms
            return np.clip(cleaned, -32768, 32767).astype(np.int16).tobytes()
        except Exception as exc:
            if not self._warned:
                logger.warning(
                    "spectral enhance failed; falling back to raw PCM (%s: %s)",
                    type(exc).__name__,
                    exc,
                )
                self._warned = True
            return pcm16


class RnnoiseEnhancer:
    """Frame-wise RNNoise with soxr resample around 48 kHz."""

    def __init__(self, *, sample_rate: int = 24_000) -> None:
        import soxr
        from pyrnnoise import RNNoise

        self._sample_rate = sample_rate
        self._soxr = soxr
        self._denoiser = RNNoise(sample_rate=_RNNOISE_RATE)
        self._warned = False

    def process(self, pcm16: bytes) -> bytes:
        if not pcm16:
            return pcm16
        try:
            mono = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32)
            if mono.size == 0:
                return pcm16
            up = self._soxr.resample(mono, self._sample_rate, _RNNOISE_RATE)
            stacked = np.stack([up.astype(np.int16)], axis=0)
            out_parts: list[np.ndarray] = []
            for _prob, frame in self._denoiser.denoise_chunk(stacked):
                if frame is None:
                    continue
                channel = np.asarray(frame)
                if channel.ndim == 2:
                    channel = channel[0]
                out_parts.append(channel.astype(np.float32))
            if not out_parts:
                return pcm16
            denoised_48k = np.concatenate(out_parts)
            down = self._soxr.resample(denoised_48k, _RNNOISE_RATE, self._sample_rate)
            target = mono.size
            if down.size < target:
                down = np.pad(down, (0, target - down.size))
            elif down.size > target:
                down = down[:target]
            return np.clip(down, -32768, 32767).astype(np.int16).tobytes()
        except Exception as exc:
            if not self._warned:
                logger.warning(
                    "rnnoise enhance failed; falling back to raw PCM (%s: %s)",
                    type(exc).__name__,
                    exc,
                )
                self._warned = True
            return pcm16


def _try_rnnoise(sample_rate: int) -> SpeechEnhancer | None:
    try:
        return RnnoiseEnhancer(sample_rate=sample_rate)
    except Exception as exc:
        logger.info(
            "rnnoise unavailable (%s: %s); using spectral gate",
            type(exc).__name__,
            exc,
        )
        return None


def create_speech_enhancer(
    *,
    enabled: bool,
    backend: str = "rnnoise",
    sample_rate: int = 24_000,
) -> SpeechEnhancer | None:
    """Return an enhancer instance, or None when enhancement is off."""
    if not enabled or backend in {"", "none", "off", "identity"}:
        return None
    backend = (backend or "rnnoise").strip().lower()
    if backend == "spectral":
        logger.info("speech enhance enabled backend=spectral sample_rate=%s", sample_rate)
        return SpectralGateEnhancer(sample_rate=sample_rate)
    if backend == "rnnoise":
        enhancer = _try_rnnoise(sample_rate)
        if enhancer is not None:
            logger.info("speech enhance enabled backend=rnnoise sample_rate=%s", sample_rate)
            return enhancer
        logger.info("speech enhance enabled backend=spectral (rnnoise fallback)")
        return SpectralGateEnhancer(sample_rate=sample_rate)
    logger.warning("unknown speech enhance backend %r; disabled", backend)
    return None
