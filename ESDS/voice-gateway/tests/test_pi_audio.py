import asyncio
import array
import json
import math
import unittest

from esds_voice.pi_audio import (
    FRAME_BYTES,
    CaptureAutoGain,
    PiAudioClient,
    PiAudioError,
    PiAudioSettings,
    capture_command,
    device_hello,
    parse_runtime_config,
    playback_command,
)


class FakeStdin:
    def __init__(self) -> None:
        self.data = bytearray()
        self.closed = False

    def write(self, data: bytes) -> None:
        self.data.extend(data)

    async def drain(self) -> None:
        return

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return


class FakeProcess:
    def __init__(self) -> None:
        self.stdin = FakeStdin()
        self.stderr = None
        self.returncode = None

    async def wait(self) -> int:
        self.returncode = 0
        return 0

    def terminate(self) -> None:
        self.returncode = 0

    def kill(self) -> None:
        self.returncode = -9


class FakeSocket:
    def __init__(self) -> None:
        self.sent: list[str | bytes] = []

    async def send(self, message: str | bytes) -> None:
        self.sent.append(message)


class TestPiAudioClient(PiAudioClient):
    async def _start_playback(self):
        return FakeProcess()


class PiAudioConfigTests(unittest.TestCase):
    def test_runtime_config_is_parsed(self) -> None:
        config = parse_runtime_config(
            'window.ESDS_CONFIG={"wsUrl":"ws://127.0.0.1:8765/v1/device",'
            '"deviceToken":"secret"};'
        )
        self.assertEqual(config.ws_url, "ws://127.0.0.1:8765/v1/device")
        self.assertEqual(config.device_token, "secret")

    def test_invalid_runtime_config_is_rejected(self) -> None:
        with self.assertRaises(PiAudioError):
            parse_runtime_config("window.OTHER={};")

    def test_alsa_commands_use_voice_protocol_format(self) -> None:
        for command in (capture_command("capture"), playback_command("playback")):
            self.assertIn("24000", command)
            self.assertIn("S16_LE", command)
            self.assertIn("1", command)
            self.assertIn("480", command)

    def test_device_hello_is_audio_only(self) -> None:
        hello = json.loads(device_hello("token"))
        self.assertEqual(hello["audio"]["sample_rate"], 24000)
        self.assertEqual(hello["audio"]["channels"], 1)
        self.assertEqual(hello["capabilities"], ["audio", "half_duplex"])
        self.assertNotIn("vision", json.dumps(hello))


class CaptureAutoGainTests(unittest.TestCase):
    @staticmethod
    def _tone(dbfs: float, frames: int = 480) -> bytes:
        amplitude = 32767 * 10 ** (dbfs / 20)
        samples = array.array(
            "h",
            (round(amplitude * math.sin(2 * math.pi * index / 48)) for index in range(frames)),
        )
        return samples.tobytes()

    @staticmethod
    def _rms_dbfs(pcm: bytes) -> float:
        samples = array.array("h", pcm)
        rms = math.sqrt(sum(value * value for value in samples) / len(samples))
        return 20 * math.log10(rms / 32768)

    def test_quiet_speech_is_raised(self) -> None:
        gain = CaptureAutoGain(max_gain_db=18, target_dbfs=-20)
        source = self._tone(-50)
        result = gain.process(source)
        self.assertGreater(self._rms_dbfs(result), self._rms_dbfs(source) + 16)

    def test_close_speech_is_not_boosted(self) -> None:
        gain = CaptureAutoGain(max_gain_db=18, target_dbfs=-20)
        source = self._tone(-8)
        self.assertEqual(gain.process(source), source)
        self.assertEqual(gain.gain_db, 0)

    def test_peak_headroom_prevents_clipping(self) -> None:
        gain = CaptureAutoGain(max_gain_db=18, target_dbfs=-10)
        samples = array.array("h", [100] * 479 + [30_000])
        result = array.array("h", gain.process(samples.tobytes()))
        self.assertLessEqual(max(result), 32_767)
        self.assertLess(gain.gain_db, 1)


class PiAudioPlaybackTests(unittest.IsolatedAsyncioTestCase):
    async def test_audio_done_waits_for_playback_and_reports_drained(self) -> None:
        socket = FakeSocket()
        client = TestPiAudioClient(PiAudioSettings(echo_guard_ms=450))
        client.session_ready = True
        client.state = "assistant_speaking"

        await client._handle_audio(bytes(FRAME_BYTES))
        self.assertFalse(client._uplink_allowed())
        await client._handle_control(
            socket,
            {"type": "audio.done", "status": "completed"},
        )

        event = json.loads(socket.sent[-1])
        self.assertEqual(event["type"], "playback.drained")
        self.assertEqual(event["played_ms"], 20)
        self.assertFalse(client._uplink_allowed())

    async def test_session_ready_enables_uplink(self) -> None:
        socket = FakeSocket()
        client = TestPiAudioClient(PiAudioSettings())
        await client._handle_control(
            socket,
            {"type": "session.ready", "state": "listening"},
        )
        self.assertTrue(client._uplink_allowed(now=client.mic_gate_until))
        settings = json.loads(socket.sent[-1])
        self.assertEqual(settings["type"], "client.audio_settings")
        self.assertFalse(settings["requested"]["autoGainControl"])


if __name__ == "__main__":
    unittest.main()
