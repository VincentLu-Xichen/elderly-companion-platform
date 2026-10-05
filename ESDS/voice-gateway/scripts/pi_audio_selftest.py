#!/usr/bin/env python3
"""One-shot local protocol test for the Raspberry Pi ALSA client."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import secrets
import sys
import threading
from array import array
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class ConfigHandler(BaseHTTPRequestHandler):
    payload = ""

    def do_GET(self) -> None:
        if self.path.split("?", 1)[0] != "/runtime-config.js":
            self.send_error(404)
            return
        body = self.payload.encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/javascript; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def tone_pcm(*, seconds: float = 0.5, frequency: float = 660) -> bytes:
    samples = array(
        "h",
        (
            round(
                10_000
                * math.sin(2 * math.pi * frequency * index / 24_000)
                * min(1.0, index / 480, (seconds * 24_000 - index) / 480)
            )
            for index in range(round(seconds * 24_000))
        ),
    )
    if sys.byteorder != "little":
        samples.byteswap()
    return samples.tobytes()


async def run(args: argparse.Namespace) -> None:
    try:
        from websockets.asyncio.server import serve
    except ImportError as exc:
        raise SystemExit("websockets is not installed") from exc

    token = secrets.token_urlsafe(18)
    ConfigHandler.payload = (
        "window.ESDS_CONFIG="
        + json.dumps(
            {
                "wsUrl": f"ws://127.0.0.1:{args.gateway_port}/v1/device",
                "deviceToken": token,
            },
            separators=(",", ":"),
        )
        + ";\n"
    )
    httpd = ThreadingHTTPServer(
        ("127.0.0.1", args.ui_port),
        partial(ConfigHandler),
    )
    http_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    http_thread.start()
    loop = asyncio.get_running_loop()
    result: asyncio.Future[dict[str, object]] = loop.create_future()

    async def handle(websocket) -> None:
        binary_after_playback = 0
        try:
            raw = await asyncio.wait_for(websocket.recv(), timeout=5)
            hello = json.loads(raw)
            if hello.get("token") != token:
                raise RuntimeError("native client sent an invalid device token")
            if hello.get("device_type") != "raspberry_pi_alsa":
                raise RuntimeError("unexpected device type")
            await websocket.send(
                json.dumps(
                    {
                        "type": "session.ready",
                        "state": "listening",
                        "protocol": "companion-audio/1",
                        "interaction": {"duplex": "half", "visual_input": False},
                        "audio": {
                            "sample_rate": 24_000,
                            "channels": 1,
                            "format": "pcm16",
                            "frame_ms": 20,
                        },
                    },
                    separators=(",", ":"),
                )
            )

            frames: list[bytes] = []
            while len(frames) < 150:
                message = await asyncio.wait_for(websocket.recv(), timeout=8)
                if isinstance(message, bytes):
                    if len(message) != 960:
                        raise RuntimeError(
                            f"unexpected capture frame size {len(message)}"
                        )
                    frames.append(message)

            await websocket.send(
                '{"type":"state.changed","state":"processing"}'
            )
            await websocket.send(
                '{"type":"state.changed","state":"assistant_speaking"}'
            )
            tone = tone_pcm()
            for offset in range(0, len(tone), 960):
                await websocket.send(tone[offset : offset + 960])
            await websocket.send(
                '{"type":"audio.done","status":"completed"}'
            )

            drained: dict[str, object] | None = None
            while drained is None:
                message = await asyncio.wait_for(websocket.recv(), timeout=8)
                if isinstance(message, bytes):
                    binary_after_playback += 1
                    continue
                event = json.loads(message)
                if event.get("type") == "playback.drained":
                    drained = event

            values = array("h")
            values.frombytes(b"".join(frames))
            if sys.byteorder != "little":
                values.byteswap()
            peak = max(abs(value) for value in values)
            rms = math.sqrt(sum(value * value for value in values) / len(values))
            summary = {
                "capture_frames": len(frames),
                "capture_rms_dbfs": round(
                    20 * math.log10(max(rms, 1) / 32768),
                    1,
                ),
                "capture_peak_dbfs": round(
                    20 * math.log10(max(peak, 1) / 32768),
                    1,
                ),
                "played_ms": drained.get("played_ms"),
                "uplink_frames_during_playback": binary_after_playback,
            }
            if not result.done():
                result.set_result(summary)
            await websocket.close(code=1000, reason="self-test complete")
        except Exception as exc:
            if not result.done():
                result.set_exception(exc)

    try:
        async with serve(
            handle,
            "127.0.0.1",
            args.gateway_port,
            compression=None,
        ):
            summary = await asyncio.wait_for(result, timeout=90)
    finally:
        await asyncio.to_thread(httpd.shutdown)
        http_thread.join(timeout=2)
        httpd.server_close()

    print("pi_audio_selftest=ok")
    for key, value in summary.items():
        print(f"{key}={value}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gateway-port", type=int, default=18766)
    parser.add_argument("--ui-port", type=int, default=18081)
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
