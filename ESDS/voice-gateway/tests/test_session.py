import asyncio
import json
import unittest
from array import array

from esds_voice.config import Settings
from esds_voice.contracts import EmotionSnapshot
from esds_voice.protocol import DeviceHello
from esds_voice.providers.base import ProviderEvent
from esds_voice.providers.mock import MockRealtimeProvider
from esds_voice.session import DeviceSession, SessionState


class CaptureSocket:
    def __init__(self) -> None:
        self.sent: list[str | bytes] = []

    async def send(self, message: str | bytes) -> None:
        self.sent.append(message)


class ConnectionClosedError(Exception):
    def __init__(self, code: int) -> None:
        super().__init__(f"connection closed: {code}")
        self.code = code


class ClosingSocket(CaptureSocket):
    def __init__(self, code: int) -> None:
        super().__init__()
        self.error = ConnectionClosedError(code)

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise self.error


def hello() -> DeviceHello:
    return DeviceHello.parse(
        json.dumps(
            {
                "type": "device.hello",
                "protocol": "companion-audio/1",
                "device_id": "test-device",
                "device_type": "test",
                "audio": {
                    "sample_rate": 24000,
                    "channels": 1,
                    "format": "pcm16",
                    "frame_ms": 20,
                },
                "capabilities": ["audio"],
            }
        )
    )


def settings() -> Settings:
    return Settings(
        runtime_provider="mock",
        emotion_backend="heuristic",
        speech_enhance=False,
        vad_start_frames=1,
        vad_stop_frames=1,
        vad_calibration_ms=0,
        playback_echo_guard_ms=0,
    )


class VoiceOnlySessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_typed_emotion_hook_receives_current_transcript(self):
        captured = []
        async def create(instructions, emotion):
            captured.append(emotion)
        self.provider.create_response_with_emotion = create
        self.session._turn = 1
        await self.session._handle_provider_event(ProviderEvent("user.transcript", text="我很担心明天的事", data={"final": True}))
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0].label, "anxious")
        self.assertIn("anxious_words", captured[0].evidence)

    async def test_finished_model_task_does_not_overwrite_later_text_fusion(self):
        async def completed_model():
            return self.session.emotion.update_model("angry", source="emotion2vec", confidence=.9)
        self.session._emotion_task = asyncio.create_task(completed_model())
        await self.session._emotion_task
        current = self.session.emotion.update_text("我很开心")
        result = await self.session._wait_for_model_emotion(current)
        self.assertEqual(result.label, "uncertain")
        self.assertEqual(result, current)

    async def asyncSetUp(self) -> None:
        self.socket = CaptureSocket()
        self.provider = MockRealtimeProvider()
        self.session = DeviceSession(
            socket=self.socket,
            hello=hello(),
            provider=self.provider,
            settings=settings(),
        )

    async def test_vad_enters_speaking_then_processing(self) -> None:
        loud = array("h", [12000] * 480).tobytes()
        silence = bytes(960)
        await self.session._handle_audio(loud)
        self.assertEqual(self.session.state, SessionState.USER_SPEAKING)
        await self.session._handle_audio(silence)
        self.assertEqual(self.session.state, SessionState.PROCESSING)

    async def test_final_transcript_requests_one_response(self) -> None:
        self.session._turn = 1
        self.session.state = SessionState.PROCESSING
        await self.session._handle_provider_event(
            ProviderEvent(
                "user.transcript",
                text="今天有点累",
                data={"final": True, "language": "zh"},
            )
        )
        self.assertEqual(self.provider.response_count, 1)
        self.assertIn("语速稍慢", self.provider.instructions)

    async def test_unreliable_transcript_is_ignored(self) -> None:
        self.session._turn = 1
        self.session.state = SessionState.PROCESSING
        await self.session._handle_provider_event(
            ProviderEvent("user.transcript", text="嗯", data={"final": True})
        )
        self.assertEqual(self.provider.response_count, 0)
        self.assertEqual(self.session.state, SessionState.LISTENING)
        controls = [
            json.loads(item) for item in self.socket.sent if isinstance(item, str)
        ]
        self.assertTrue(any(item["type"] == "turn.ignored" for item in controls))

    async def test_provider_emotion_is_fused_without_local_model(self) -> None:
        self.session._turn = 1
        self.session.state = SessionState.PROCESSING
        await self.session._handle_provider_event(
            ProviderEvent(
                "user.transcript",
                text="这件事让我很生气",
                data={
                    "final": True,
                    "provider_emotion": "angry",
                    "language": "zh",
                },
            )
        )
        self.assertIn("不要争辩", self.provider.instructions)

    async def test_audio_is_chunked_and_waits_for_playback_drained(self) -> None:
        self.session.state = SessionState.PROCESSING
        await self.session._handle_provider_event(
            ProviderEvent("response.started", data={"response_id": "r1"})
        )
        await self.session._handle_provider_event(
            ProviderEvent(
                "audio.delta",
                audio=bytes(2400),
                item_id="a1",
                data={"response_id": "r1"},
            )
        )
        binary = [item for item in self.socket.sent if isinstance(item, bytes)]
        self.assertEqual([len(item) for item in binary], [960, 960, 480])
        await self.session._handle_provider_event(
            ProviderEvent(
                "response.done",
                data={"status": "completed", "response_id": "r1"},
            )
        )
        self.assertEqual(self.session.state, SessionState.ASSISTANT_SPEAKING)
        await self.session._handle_control(
            json.dumps({"type": "playback.drained", "played_ms": 50})
        )
        self.assertEqual(self.session.state, SessionState.LISTENING)

    async def test_visual_event_is_not_supported(self) -> None:
        await self.session._handle_control(
            json.dumps({"type": "vision.snapshot", "image": "ignored"})
        )
        response = json.loads(self.socket.sent[-1])
        self.assertEqual(response["code"], "unsupported_event")

    def test_qwen_emotion_aliases(self) -> None:
        self.assertEqual(
            self.session._normalize_provider_emotion("surprised"), "excited"
        )
        self.assertIsNone(self.session._normalize_provider_emotion("unknown"))

    async def test_manual_reconnect_is_a_normal_session_end(self) -> None:
        self.session.socket = ClosingSocket(4000)
        await self.session._device_reader()

    async def test_unexpected_connection_close_is_raised(self) -> None:
        self.session.socket = ClosingSocket(1006)
        with self.assertRaises(ConnectionClosedError):
            await self.session._device_reader()


if __name__ == "__main__":
    unittest.main()
