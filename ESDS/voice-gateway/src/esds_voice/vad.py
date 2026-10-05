from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .contracts import AudioFeatures


@dataclass(frozen=True, slots=True)
class VadEvent:
    type: str
    rms_dbfs: float


class EnergyVad:
    """Adaptive, noise-floor-aware utterance endpoint detector."""

    def __init__(
        self,
        *,
        start_dbfs: float = -43.0,
        stop_dbfs: float = -49.0,
        start_frames: int = 4,
        stop_frames: int = 18,
        start_snr_db: float = 14.0,
        stop_snr_db: float = 6.0,
        calibration_frames: int = 25,
        noise_window_frames: int = 150,
    ) -> None:
        self.start_dbfs = start_dbfs
        self.stop_dbfs = stop_dbfs
        self.start_frames = start_frames
        self.stop_frames = stop_frames
        self.start_snr_db = start_snr_db
        self.stop_snr_db = stop_snr_db
        self.speaking = False
        self._hot = 0
        self._cold = 0
        self._noise_floor = -60.0
        self._noise_levels: deque[float] = deque(maxlen=max(10, noise_window_frames))
        self._calibration_remaining = max(0, calibration_frames)

    @property
    def noise_floor_dbfs(self) -> float:
        return self._noise_floor

    @property
    def adaptive_start_dbfs(self) -> float:
        return max(self.start_dbfs, self._noise_floor + self.start_snr_db)

    @property
    def adaptive_stop_dbfs(self) -> float:
        return max(self.stop_dbfs, self._noise_floor + self.stop_snr_db)

    def update(self, features: AudioFeatures) -> VadEvent | None:
        level = features.rms_dbfs
        if self._calibration_remaining:
            self._record_noise(level)
            self._calibration_remaining -= 1
            self._hot = 0
            return None

        if not self.speaking:
            threshold = self.adaptive_start_dbfs
            self._hot = self._hot + 1 if level >= threshold else 0
            if level < threshold:
                self._record_noise(level)
            if self._hot >= self.start_frames:
                self.speaking = True
                self._hot = 0
                self._cold = 0
                return VadEvent("speech.started", level)
            return None

        self._cold = self._cold + 1 if level < self.adaptive_stop_dbfs else 0
        if self._cold >= self.stop_frames:
            self.speaking = False
            self._cold = 0
            return VadEvent("speech.stopped", level)
        return None

    def _record_noise(self, level: float) -> None:
        self._noise_levels.append(level)
        ordered = sorted(self._noise_levels)
        self._noise_floor = ordered[int((len(ordered) - 1) * 0.2)]
