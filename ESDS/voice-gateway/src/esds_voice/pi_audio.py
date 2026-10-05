from __future__ import annotations

import argparse
import asyncio
import array
import json
import logging
import math
import os
import re
import signal
import socket
import sys
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SAMPLE_RATE = 24_000
CHANNELS = 1
SAMPLE_WIDTH = 2
FRAME_MS = 20
FRAME_BYTES = SAMPLE_RATE * FRAME_MS // 1000 * SAMPLE_WIDTH
UPLINK_STATES = {"listening", "user_speaking"}


class PiAudioError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    ws_url: str
    device_token: str | None


@dataclass(frozen=True, slots=True)
class PiAudioSettings:
    config_url: str = "http://127.0.0.1:8080/runtime-config.js"
    capture_device: str = "plughw:CARD=Device,DEV=0"
    playback_device: str = "plughw:CARD=Device,DEV=0"
    mixer_card: str = "Device"
    capture_volume_control: str = "Mic Capture Volume"
    capture_switch_control: str = "Mic Capture Switch"
    capture_switch_value: str = "on"
    playback_volume_control: str = "Speaker Playback Volume"
    playback_switch_control: str = "Speaker Playback Switch"
    capture_gain: int = 128
    auto_gain_max_db: float = 18.0
    auto_gain_target_dbfs: float = -20.0
    playback_volume: int = 800
    reconnect_max_seconds: float = 15.0
    echo_guard_ms: int = 450


class CaptureAutoGain:
    """Raise distant speech while keeping close speech below clipping.

    The USB module's hardware gain alone cannot cover both normal-distance and
    close speech reliably.  This per-frame gain stage starts ready for quiet
    speech, immediately backs off for loud frames, and caps gain against both
    RMS and peak headroom.
    """

    def __init__(self, *, max_gain_db: float, target_dbfs: float) -> None:
        self.max_gain_db = max(0.0, max_gain_db)
        self.target_dbfs = target_dbfs
        self.gain_db = self.max_gain_db

    def process(self, pcm16: bytes) -> bytes:
        if not pcm16 or self.max_gain_db <= 0:
            self.gain_db = 0.0
            return pcm16
        samples = array.array("h")
        samples.frombytes(pcm16)
        if sys.byteorder != "little":
            samples.byteswap()
        if not samples:
            return pcm16

        square_sum = sum(sample * sample for sample in samples)
        rms = math.sqrt(square_sum / len(samples))
        peak = max(abs(sample) for sample in samples)
        rms_dbfs = 20.0 * math.log10(max(rms, 1.0) / 32768.0)
        peak_dbfs = 20.0 * math.log10(max(peak, 1) / 32768.0)
        desired_db = min(
            self.max_gain_db,
            max(0.0, self.target_dbfs - rms_dbfs),
            max(0.0, -1.0 - peak_dbfs),
        )
        # Back off immediately to protect close speech.  Restore at 2 dB per
        # 20 ms frame so quiet speech reaches useful level without a long ramp.
        if desired_db < self.gain_db:
            self.gain_db = desired_db
        else:
            self.gain_db = min(desired_db, self.gain_db + 2.0)

        factor = 10.0 ** (self.gain_db / 20.0)
        boosted = array.array(
            "h",
            (
                max(-32768, min(32767, round(sample * factor)))
                for sample in samples
            ),
        )
        if sys.byteorder != "little":
            boosted.byteswap()
        return boosted.tobytes()


def parse_runtime_config(script: str) -> RuntimeConfig:
    match = re.search(r"window\.ESDS_CONFIG\s*=\s*(\{.*\})\s*;", script, re.DOTALL)
    if match is None:
        raise PiAudioError("runtime-config.js does not contain window.ESDS_CONFIG")
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise PiAudioError("runtime-config.js contains invalid JSON") from exc
    ws_url = payload.get("wsUrl")
    token = payload.get("deviceToken")
    if not isinstance(ws_url, str) or not ws_url.startswith(("ws://", "wss://")):
        raise PiAudioError("runtime config does not contain a valid wsUrl")
    if token is not None and not isinstance(token, str):
        raise PiAudioError("runtime config deviceToken must be a string")
    return RuntimeConfig(ws_url=ws_url, device_token=token or None)


def capture_command(device: str) -> list[str]:
    return [
        "arecord",
        "-q",
        "-D",
        device,
        "-t",
        "raw",
        "-f",
        "S16_LE",
        "-c",
        str(CHANNELS),
        "-r",
        str(SAMPLE_RATE),
        "--period-size",
        str(SAMPLE_RATE * FRAME_MS // 1000),
        "--buffer-size",
        str(SAMPLE_RATE * FRAME_MS // 1000 * 4),
        "-",
    ]


def playback_command(device: str) -> list[str]:
    return [
        "aplay",
        "-q",
        "-D",
        device,
        "-t",
        "raw",
        "-f",
        "S16_LE",
        "-c",
        str(CHANNELS),
        "-r",
        str(SAMPLE_RATE),
        "--period-size",
        str(SAMPLE_RATE * FRAME_MS // 1000),
        "--buffer-size",
        str(SAMPLE_RATE * FRAME_MS // 1000 * 4),
        "-",
    ]


def device_id() -> str:
    machine_id_path = Path("/etc/machine-id")
    try:
        suffix = machine_id_path.read_text(encoding="ascii").strip()[:12]
    except OSError:
        suffix = socket.gethostname()
    return f"esds-pi-{suffix}"


def device_hello(token: str | None) -> str:
    payload: dict[str, Any] = {
        "type": "device.hello",
        "protocol": "companion-audio/1",
        "device_id": device_id(),
        "device_type": "raspberry_pi_alsa",
        "audio": {
            "sample_rate": SAMPLE_RATE,
            "channels": CHANNELS,
            "format": "pcm16",
            "frame_ms": FRAME_MS,
        },
        "capabilities": ["audio", "half_duplex"],
    }
    if token:
        payload["token"] = token
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class PiAudioClient:
    def __init__(self, settings: PiAudioSettings) -> None:
        self.settings = settings
        self._capture_auto_gain = CaptureAutoGain(
            max_gain_db=settings.auto_gain_max_db,
            target_dbfs=settings.auto_gain_target_dbfs,
        )
        self.session_ready = False
        self.state = "disconnected"
        self.mic_gate_until = 0.0
        self._playback_process: asyncio.subprocess.Process | Any | None = None
        self._playback_samples = 0
        self._playback_started_at = 0.0
        self._last_emotion_label: str | None = None
        self._last_emotion_log_at = 0.0

    async def run_forever(self) -> None:
        delay = 1.0
        while True:
            try:
                runtime = await self._fetch_runtime_config()
                await self._run_connection(runtime)
                delay = 1.0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.session_ready = False
                self.state = "disconnected"
                await self._flush_playback()
                logger.warning(
                    "audio client disconnected: %s; retrying in %.1fs",
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
                delay = min(self.settings.reconnect_max_seconds, delay * 2)

    async def _fetch_runtime_config(self) -> RuntimeConfig:
        def fetch() -> str:
            with urllib.request.urlopen(
                self.settings.config_url,
                timeout=3,
            ) as response:
                return response.read().decode("utf-8")

        script = await asyncio.to_thread(fetch)
        return parse_runtime_config(script)

    async def _run_connection(self, runtime: RuntimeConfig) -> None:
        try:
            from websockets.asyncio.client import connect
        except ImportError as exc:
            raise PiAudioError("websockets is not installed") from exc

        await self._configure_mixer()
        logger.info("connecting to ESDS gateway %s", runtime.ws_url)
        async with connect(
            runtime.ws_url,
            max_size=64_000,
            max_queue=4,
            compression=None,
            ping_interval=20,
            ping_timeout=20,
        ) as websocket:
            await websocket.send(device_hello(runtime.device_token))
            capture = await self._start_capture()
            capture_task = asyncio.create_task(
                self._capture_loop(websocket, capture),
                name="pi-audio-capture",
            )
            try:
                await self._receive_loop(websocket)
            finally:
                capture_task.cancel()
                await asyncio.gather(capture_task, return_exceptions=True)
                await self._stop_process(capture)
                await self._flush_playback()
                self.session_ready = False
                self.state = "disconnected"

    async def _configure_mixer(self) -> None:
        controls = (
            (self.settings.capture_volume_control, self.settings.capture_gain),
            (self.settings.capture_switch_control, self.settings.capture_switch_value),
            (self.settings.playback_volume_control, self.settings.playback_volume),
            (self.settings.playback_switch_control, "on"),
        )
        for name, value in controls:
            try:
                process = await asyncio.create_subprocess_exec(
                    "amixer",
                    "-q",
                    "-c",
                    self.settings.mixer_card,
                    "sset",
                    f"{name},0",
                    str(value),
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )
            except FileNotFoundError as exc:
                raise PiAudioError("amixer is not installed") from exc
            _, stderr = await process.communicate()
            if process.returncode:
                message = stderr.decode("utf-8", "replace").strip()
                raise PiAudioError(f"cannot configure {name}: {message}")
        logger.info(
            "mixer configured card=%s capture_gain=%s playback_volume=%s",
            self.settings.mixer_card,
            self.settings.capture_gain,
            self.settings.playback_volume,
        )

    async def _start_capture(self) -> asyncio.subprocess.Process:
        try:
            process = await asyncio.create_subprocess_exec(
                *capture_command(self.settings.capture_device),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise PiAudioError("arecord is not installed") from exc
        if process.stdout is None:
            raise PiAudioError("arecord stdout pipe was not created")
        await asyncio.sleep(0.1)
        if process.returncode is not None:
            stderr = await process.stderr.read() if process.stderr else b""
            raise PiAudioError(
                "arecord failed to start: "
                + stderr.decode("utf-8", "replace").strip()
            )
        logger.info("capture started device=%s", self.settings.capture_device)
        return process

    async def _capture_loop(self, websocket: Any, process: Any) -> None:
        assert process.stdout is not None
        buffer = bytearray()
        while True:
            chunk = await process.stdout.read(FRAME_BYTES - len(buffer))
            if not chunk:
                stderr = await process.stderr.read() if process.stderr else b""
                raise PiAudioError(
                    "arecord stopped: " + stderr.decode("utf-8", "replace").strip()
                )
            buffer.extend(chunk)
            if len(buffer) != FRAME_BYTES:
                continue
            if self._uplink_allowed():
                await websocket.send(self._capture_auto_gain.process(bytes(buffer)))
            buffer.clear()

    def _uplink_allowed(self, *, now: float | None = None) -> bool:
        current = asyncio.get_running_loop().time() if now is None else now
        return (
            self.session_ready
            and self.state in UPLINK_STATES
            and current >= self.mic_gate_until
            and self._playback_process is None
        )

    async def _receive_loop(self, websocket: Any) -> None:
        async for message in websocket:
            if isinstance(message, bytes):
                await self._handle_audio(message)
                continue
            try:
                event = json.loads(message)
            except json.JSONDecodeError:
                logger.warning("ignored invalid control message")
                continue
            if isinstance(event, dict):
                await self._handle_control(websocket, event)

    async def _handle_audio(self, pcm: bytes) -> None:
        if not pcm:
            return
        if self._playback_process is None:
            self._playback_process = await self._start_playback()
            self._playback_samples = 0
            self._playback_started_at = time.monotonic()
        stdin = self._playback_process.stdin
        if stdin is None:
            raise PiAudioError("aplay stdin pipe was not created")
        stdin.write(pcm)
        await stdin.drain()
        self._playback_samples += len(pcm) // SAMPLE_WIDTH

    async def _start_playback(self) -> asyncio.subprocess.Process:
        try:
            process = await asyncio.create_subprocess_exec(
                *playback_command(self.settings.playback_device),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise PiAudioError("aplay is not installed") from exc
        logger.info("playback started device=%s", self.settings.playback_device)
        return process

    async def _handle_control(self, websocket: Any, event: dict[str, Any]) -> None:
        event_type = event.get("type")
        if event_type == "session.ready":
            self.session_ready = True
            self.state = str(event.get("state") or "listening")
            await websocket.send(
                json.dumps(
                    {
                        "type": "client.audio_settings",
                        "requested": {
                            "echoCancellation": False,
                            "noiseSuppression": False,
                            "autoGainControl": False,
                        },
                        "settings": {
                            "capture_device": self.settings.capture_device,
                            "playback_device": self.settings.playback_device,
                            "capture_gain": self.settings.capture_gain,
                            "auto_gain_max_db": self.settings.auto_gain_max_db,
                            "auto_gain_target_dbfs": self.settings.auto_gain_target_dbfs,
                            "sample_rate": SAMPLE_RATE,
                        },
                        "client": "esds_pi_audio",
                    },
                    separators=(",", ":"),
                )
            )
            logger.info("voice session ready state=%s", self.state)
        elif event_type == "state.changed":
            self.state = str(event.get("state") or self.state)
            logger.info("voice state=%s", self.state)
        elif event_type == "audio.done":
            status = str(event.get("status") or "done")
            if status in {"cancelled", "canceled"}:
                await self._flush_playback()
            else:
                await self._finish_playback(websocket)
        elif event_type == "audio.flush":
            await self._flush_playback()
        elif event_type == "transcript.user" and event.get("final"):
            logger.info("user transcript: %s", event.get("text") or "")
        elif event_type == "transcript.assistant" and event.get("final"):
            logger.info("assistant transcript: %s", event.get("text") or "")
        elif event_type == "emotion.updated":
            emotion = event.get("emotion")
            if isinstance(emotion, dict):
                label = str(emotion.get("label") or "unknown")
                now = time.monotonic()
                if (
                    label != self._last_emotion_label
                    or now - self._last_emotion_log_at >= 5
                ):
                    logger.info(
                        "emotion=%s confidence=%.2f",
                        label,
                        float(emotion.get("confidence") or 0),
                    )
                    self._last_emotion_label = label
                    self._last_emotion_log_at = now
        elif event_type == "turn.ignored":
            logger.info("turn ignored reason=%s", event.get("reason"))
        elif event_type == "error":
            logger.error(
                "gateway error code=%s message=%s",
                event.get("code"),
                event.get("message"),
            )

    async def _finish_playback(self, websocket: Any) -> None:
        process = self._playback_process
        played_ms = round(self._playback_samples * 1000 / SAMPLE_RATE)
        if process is not None:
            stdin = process.stdin
            if stdin is not None:
                stdin.close()
                try:
                    await stdin.wait_closed()
                except (BrokenPipeError, ConnectionResetError):
                    pass
            timeout = max(5.0, played_ms / 1000 + 2.0)
            try:
                await asyncio.wait_for(process.wait(), timeout=timeout)
            except TimeoutError:
                process.terminate()
                await process.wait()
            if process.returncode:
                stderr = await process.stderr.read() if process.stderr else b""
                logger.warning(
                    "aplay exited code=%s error=%s",
                    process.returncode,
                    stderr.decode("utf-8", "replace").strip(),
                )
        self._playback_process = None
        self._playback_samples = 0
        self.mic_gate_until = (
            asyncio.get_running_loop().time()
            + self.settings.echo_guard_ms / 1000
        )
        await websocket.send(
            json.dumps(
                {
                    "type": "playback.drained",
                    "played_ms": played_ms,
                    "timestamp_ms": time.time_ns() // 1_000_000,
                },
                separators=(",", ":"),
            )
        )
        logger.info("playback drained played_ms=%s", played_ms)

    async def _flush_playback(self) -> None:
        process = self._playback_process
        self._playback_process = None
        self._playback_samples = 0
        if process is not None:
            await self._stop_process(process)

    @staticmethod
    async def _stop_process(process: Any) -> None:
        if process.returncode is not None:
            return
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=2)
        except TimeoutError:
            process.kill()
            await process.wait()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the native Raspberry Pi ALSA client for ESDS Voice"
    )
    parser.add_argument(
        "--config-url",
        default=os.getenv(
            "ESDS_PI_CONFIG_URL",
            "http://127.0.0.1:8080/runtime-config.js",
        ),
    )
    parser.add_argument(
        "--capture-device",
        default=os.getenv(
            "ESDS_PI_CAPTURE_DEVICE",
            "plughw:CARD=Device,DEV=0",
        ),
    )
    parser.add_argument(
        "--playback-device",
        default=os.getenv(
            "ESDS_PI_PLAYBACK_DEVICE",
            "plughw:CARD=Device,DEV=0",
        ),
    )
    parser.add_argument(
        "--mixer-card",
        default=os.getenv("ESDS_PI_MIXER_CARD", "Device"),
    )
    parser.add_argument(
        "--capture-volume-control",
        default=os.getenv(
            "ESDS_PI_CAPTURE_VOLUME_CONTROL",
            "Mic Capture Volume",
        ),
    )
    parser.add_argument(
        "--capture-switch-control",
        default=os.getenv(
            "ESDS_PI_CAPTURE_SWITCH_CONTROL",
            "Mic Capture Switch",
        ),
    )
    parser.add_argument(
        "--capture-switch-value",
        default=os.getenv("ESDS_PI_CAPTURE_SWITCH_VALUE", "on"),
    )
    parser.add_argument(
        "--playback-volume-control",
        default=os.getenv(
            "ESDS_PI_PLAYBACK_VOLUME_CONTROL",
            "Speaker Playback Volume",
        ),
    )
    parser.add_argument(
        "--playback-switch-control",
        default=os.getenv(
            "ESDS_PI_PLAYBACK_SWITCH_CONTROL",
            "Speaker Playback Switch",
        ),
    )
    parser.add_argument(
        "--capture-gain",
        type=int,
        default=int(os.getenv("ESDS_PI_CAPTURE_GAIN", "128")),
    )
    parser.add_argument(
        "--auto-gain-max-db",
        type=float,
        default=float(os.getenv("ESDS_PI_AUTO_GAIN_MAX_DB", "18")),
    )
    parser.add_argument(
        "--auto-gain-target-dbfs",
        type=float,
        default=float(os.getenv("ESDS_PI_AUTO_GAIN_TARGET_DBFS", "-20")),
    )
    parser.add_argument(
        "--playback-volume",
        type=int,
        default=int(os.getenv("ESDS_PI_PLAYBACK_VOLUME", "800")),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = PiAudioSettings(
        config_url=args.config_url,
        capture_device=args.capture_device,
        playback_device=args.playback_device,
        mixer_card=args.mixer_card,
        capture_volume_control=args.capture_volume_control,
        capture_switch_control=args.capture_switch_control,
        capture_switch_value=args.capture_switch_value,
        playback_volume_control=args.playback_volume_control,
        playback_switch_control=args.playback_switch_control,
        capture_gain=args.capture_gain,
        auto_gain_max_db=args.auto_gain_max_db,
        auto_gain_target_dbfs=args.auto_gain_target_dbfs,
        playback_volume=args.playback_volume,
    )
    if not 0 <= settings.capture_gain <= 496:
        raise SystemExit("--capture-gain must be between 0 and 496")
    if not 0 <= settings.auto_gain_max_db <= 30:
        raise SystemExit("--auto-gain-max-db must be between 0 and 30")
    if not -40 <= settings.auto_gain_target_dbfs <= -6:
        raise SystemExit("--auto-gain-target-dbfs must be between -40 and -6")
    if not 0 <= settings.playback_volume <= 1008:
        raise SystemExit("--playback-volume must be between 0 and 1008")
    logging.basicConfig(
        level=os.getenv("ESDS_LOG_LEVEL", "INFO"),
        format="%(asctime)s: %(message)s",
    )
    try:
        asyncio.run(_run_until_stopped(PiAudioClient(settings)))
    except KeyboardInterrupt:
        pass


async def _run_until_stopped(client: PiAudioClient) -> None:
    loop = asyncio.get_running_loop()
    stopped = asyncio.Event()
    installed_signals: list[signal.Signals] = []
    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signum, stopped.set)
            installed_signals.append(signum)
        except NotImplementedError:
            continue
    task = asyncio.create_task(client.run_forever(), name="pi-audio-client")
    stop_task = asyncio.create_task(stopped.wait(), name="pi-audio-stop")
    try:
        done, _ = await asyncio.wait(
            {task, stop_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if task in done:
            await task
    finally:
        task.cancel()
        stop_task.cancel()
        await asyncio.gather(task, stop_task, return_exceptions=True)
        for signum in installed_signals:
            loop.remove_signal_handler(signum)


if __name__ == "__main__":
    main()
