import base64
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from esds_voice.transcription import QwenRealtimeTranscriber, SenseVoiceTranscriber


class FakeStream:
    def __init__(self, result) -> None:
        self.result = result
        self.accepted_rate = None

    def accept_waveform(self, sample_rate, samples) -> None:
        self.accepted_rate = sample_rate


class FakeRecognizer:
    def __init__(self, result) -> None:
        self.stream = FakeStream(result)
        self.decode_count = 0

    def create_stream(self):
        return self.stream

    def decode_stream(self, stream) -> None:
        self.decode_count += 1


class SenseVoiceTranscriberTests(unittest.TestCase):
    def make_transcriber(self) -> SenseVoiceTranscriber:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / "model.int8.onnx").touch()
        (root / "tokens.txt").touch()
        return SenseVoiceTranscriber(root)

    def test_returns_text_even_when_emotion_is_unknown(self) -> None:
        transcriber = self.make_transcriber()
        fake = FakeRecognizer(
            SimpleNamespace(
                text="今天有点累。",
                lang="<|zh|>",
                event="<|Speech|>",
                emotion="<|EMO_UNKNOWN|>",
            )
        )
        transcriber._recognizer = fake
        result = transcriber.transcribe_pcm16(b"\x00\x00" * 480, 24_000)
        self.assertEqual(result.text, "今天有点累。")
        self.assertEqual(result.language, "zh")
        self.assertEqual(result.event, "Speech")
        self.assertEqual(fake.stream.accepted_rate, 24_000)
        self.assertEqual(fake.decode_count, 1)

    def test_rejects_invalid_pcm(self) -> None:
        transcriber = self.make_transcriber()
        self.assertIsNone(transcriber.transcribe_pcm16(b"\x00", 24_000))


class FakeQwenSocket:
    def __init__(self, events) -> None:
        self.events = list(events)
        self.sent = []
        self.closed = False

    async def send(self, value) -> None:
        self.sent.append(json.loads(value))

    async def recv(self):
        return json.dumps(self.events.pop(0))

    async def close(self) -> None:
        self.closed = True


class QwenRealtimeTranscriberTests(unittest.IsolatedAsyncioTestCase):
    async def test_streams_resampled_pcm_and_returns_emotion(self) -> None:
        socket = FakeQwenSocket(
            [
                {"type": "session.created"},
                {"type": "session.updated"},
                {
                    "type": "conversation.item.input_audio_transcription.text",
                    "text": "今天",
                    "stash": "有点累",
                },
                {
                    "type": "conversation.item.input_audio_transcription.completed",
                    "transcript": "今天有点累。",
                    "language": "zh",
                    "emotion": "sad",
                },
            ]
        )
        connection = {}

        async def connect(url, headers):
            connection["url"] = url
            connection["headers"] = headers
            return socket

        transcriber = QwenRealtimeTranscriber(
            api_key="secret",
            workspace_id="workspace-1",
            context="闺蜜镜 小精灵",
            connector=connect,
        )
        await transcriber.warmup()
        await transcriber.start_stream(24_000)
        await transcriber.send_stream_audio(b"\x00\x00" * 480)
        result = await transcriber.finish_stream()

        self.assertIn("workspace-1.cn-beijing.maas.aliyuncs.com", connection["url"])
        self.assertEqual(connection["headers"]["Authorization"], "Bearer secret")
        session = socket.sent[0]["session"]
        self.assertIsNone(session["turn_detection"])
        self.assertEqual(
            session["input_audio_transcription"]["corpus"]["text"],
            "闺蜜镜 小精灵",
        )
        audio = base64.b64decode(socket.sent[1]["audio"])
        self.assertGreater(len(audio), 600)
        self.assertLess(len(audio), 650)
        self.assertEqual(socket.sent[2]["type"], "input_audio_buffer.commit")
        self.assertEqual(result.text, "今天有点累。")
        self.assertEqual(result.language, "zh")
        self.assertEqual(result.event, "sad")

    async def test_server_failure_drops_connection(self) -> None:
        socket = FakeQwenSocket(
            [
                {"type": "session.created"},
                {"type": "session.updated"},
                {
                    "type": "conversation.item.input_audio_transcription.failed",
                    "error": {"code": "bad_audio", "message": "cannot decode"},
                },
            ]
        )

        async def connect(url, headers):
            return socket

        transcriber = QwenRealtimeTranscriber(
            api_key="secret",
            connector=connect,
        )
        await transcriber.start_stream(16_000)
        await transcriber.send_stream_audio(b"\x00\x00" * 320)
        with self.assertRaisesRegex(RuntimeError, "bad_audio"):
            await transcriber.finish_stream()
        self.assertTrue(socket.closed)


if __name__ == "__main__":
    unittest.main()
