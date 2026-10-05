from __future__ import annotations

import json
import threading
import time
import wave
from pathlib import Path
from typing import Any


class AsrDiagnostics:
    """Opt-in local ASR evidence capture. Never uploads or stores credentials."""

    def __init__(self, root: str | Path, session_id: str) -> None:
        self.directory = Path(root).expanduser().resolve() / session_id
        self.directory.mkdir(parents=True, exist_ok=True)
        self.events_path = self.directory / "events.jsonl"
        self._lock = threading.Lock()

    def event(self, event_type: str, **data: Any) -> None:
        payload = {
            "timestamp_ms": time.time_ns() // 1_000_000,
            "monotonic_ms": round(time.monotonic_ns() / 1_000_000, 3),
            "type": event_type,
            **data,
        }
        line = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            with self.events_path.open("a", encoding="utf-8") as stream:
                stream.write(line + "\n")

    def save_pcm16(
        self,
        *,
        turn: int,
        pcm: bytes,
        sample_rate: int,
    ) -> Path:
        path = self.directory / f"turn-{turn:04d}.wav"
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(sample_rate)
            output.writeframes(pcm)
        return path
