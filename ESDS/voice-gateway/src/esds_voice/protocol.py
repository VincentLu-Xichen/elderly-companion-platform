from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

PROTOCOL_VERSION = "companion-audio/1"


class ProtocolError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AudioSpec:
    sample_rate: int
    channels: int
    format: str
    frame_ms: int

    @property
    def frame_bytes(self) -> int:
        return self.sample_rate * self.frame_ms // 1000 * self.channels * 2


@dataclass(frozen=True, slots=True)
class DeviceHello:
    device_id: str
    device_type: str
    audio: AudioSpec
    capabilities: tuple[str, ...]
    token: str | None = None

    @classmethod
    def parse(cls, raw: str | bytes) -> "DeviceHello":
        if isinstance(raw, bytes):
            raise ProtocolError("first message must be a JSON device.hello")
        try:
            body = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProtocolError("invalid JSON in device.hello") from exc
        if not isinstance(body, dict) or body.get("type") != "device.hello":
            raise ProtocolError("first event must be device.hello")
        if body.get("protocol") != PROTOCOL_VERSION:
            raise ProtocolError(f"unsupported protocol; expected {PROTOCOL_VERSION}")
        audio = body.get("audio")
        if not isinstance(audio, dict):
            raise ProtocolError("device.hello.audio is required")
        try:
            spec = AudioSpec(
                sample_rate=int(audio["sample_rate"]),
                channels=int(audio["channels"]),
                format=str(audio["format"]),
                frame_ms=int(audio["frame_ms"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProtocolError("invalid audio specification") from exc
        if (
            spec.sample_rate != 24_000
            or spec.channels != 1
            or spec.format != "pcm16"
            or spec.frame_ms not in {10, 20, 30}
        ):
            raise ProtocolError("v1 requires mono PCM16 at 24000 Hz and 10/20/30 ms")
        device_id = str(body.get("device_id", "")).strip()
        device_type = str(body.get("device_type", "")).strip()
        if not device_id or len(device_id) > 128:
            raise ProtocolError("device_id is required and must be <= 128 characters")
        if not device_type or len(device_type) > 64:
            raise ProtocolError("device_type is required and must be <= 64 characters")
        capabilities = body.get("capabilities", [])
        if not isinstance(capabilities, list) or not all(
            isinstance(item, str) for item in capabilities
        ):
            raise ProtocolError("capabilities must be an array of strings")
        token = body.get("token")
        if token is not None and not isinstance(token, str):
            raise ProtocolError("token must be a string")
        return cls(device_id, device_type, spec, tuple(capabilities), token)


def parse_control(raw: str) -> dict[str, Any]:
    try:
        body = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProtocolError("invalid control JSON") from exc
    if not isinstance(body, dict) or not isinstance(body.get("type"), str):
        raise ProtocolError("control event requires a string type")
    return body


def event_json(event_type: str, **payload: Any) -> str:
    return json.dumps(
        {"type": event_type, "timestamp_ms": time.time_ns() // 1_000_000, **payload},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def safe_error(code: str, message: str, *, retryable: bool = False) -> str:
    return event_json("error", code=code, message=message, retryable=retryable)
