import asyncio
import base64
import json
import unittest
from collections import deque

from esds_voice.providers.qwen_tts import (
    QwenRealtimeTtsSynthesizer,
    voice_instruction_for,
)


class FakeSocket:
    def __init__(self, events):
        self.events = deque(json.dumps(event) for event in events)
        self.sent = []
        self.closed = False

    async def send(self, payload: str) -> None:
        self.sent.append(json.loads(payload))

    async def recv(self) -> str:
        await asyncio.sleep(0)
        return self.events.popleft()

    async def close(self) -> None:
        self.closed = True


class QwenTtsInstructionTests(unittest.TestCase):
    def test_emotions_keep_same_voice_identity(self) -> None:
        gentle = voice_instruction_for("语速稍慢、句子短一些")
        happy = voice_instruction_for("可以略带笑意回应")
        angry = voice_instruction_for("不要争辩或自我辩护")
        self.assertIn("自然亲近", gentle)
        self.assertIn("自然亲近", happy)
        self.assertIn("自然亲近", angry)
        self.assertIn("温暖轻柔", gentle)
        self.assertIn("自然笑意", happy)
        self.assertIn("平稳克制", angry)
        self.assertNotEqual(gentle, happy)

    def test_explicit_scenario_delivery_is_used_without_llm_content(self) -> None:
        instruction = (
            "场景行为：不要把这段内容送入声音指令。"
            "<TTS_DELIVERY>声音轻柔，结尾自然。</TTS_DELIVERY>"
        )
        voice = voice_instruction_for(instruction)
        self.assertIn("声音轻柔，结尾自然", voice)
        self.assertNotIn("场景行为", voice)


class QwenTtsAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_commit_mode_streams_pcm_and_reuses_session(self) -> None:
        audio_one = b"\x01\x00" * 480
        audio_two = b"\x02\x00" * 240
        socket = FakeSocket(
            [
                {"type": "session.created"},
                {"type": "session.updated"},
                {
                    "type": "response.audio.delta",
                    "delta": base64.b64encode(audio_one).decode(),
                },
                {
                    "type": "response.done",
                    "response": {
                        "status": "completed",
                        "usage": {"characters": 5},
                    },
                },
                {
                    "type": "response.audio.delta",
                    "delta": base64.b64encode(audio_two).decode(),
                },
                {
                    "type": "response.done",
                    "response": {
                        "status": "completed",
                        "usage": {"characters": 4},
                    },
                },
                {"type": "session.finished"},
            ]
        )
        calls = []

        async def connector(url, headers):
            calls.append((url, headers))
            return socket

        tts = QwenRealtimeTtsSynthesizer(
            api_key="test-key",
            optimize_instructions=True,
            connector=connector,
        )
        instructions = "可以略带笑意回应"
        await tts.prepare(instructions)
        first = b"".join(
            [chunk async for chunk in tts.stream_pcm24k("你好呀。", instructions=instructions)]
        )
        second = b"".join(
            [chunk async for chunk in tts.stream_pcm24k("回来啦。", instructions=instructions)]
        )

        self.assertEqual(first, audio_one)
        self.assertEqual(second, audio_two)
        self.assertEqual(len(calls), 1)
        self.assertIn("model=qwen3-tts-instruct-flash-realtime", calls[0][0])
        self.assertEqual(calls[0][1]["Authorization"], "Bearer test-key")
        types = [event["type"] for event in socket.sent]
        self.assertEqual(
            types[:5],
            [
                "session.update",
                "input_text_buffer.append",
                "input_text_buffer.commit",
                "input_text_buffer.append",
                "input_text_buffer.commit",
            ],
        )
        session = socket.sent[0]["session"]
        self.assertEqual(session["voice"], "Cherry")
        self.assertEqual(session["mode"], "commit")
        self.assertEqual(session["sample_rate"], 24_000)
        self.assertTrue(session["optimize_instructions"])
        self.assertEqual(tts.last_metrics.characters, 4)
        self.assertEqual(tts.last_metrics.audio_seconds, 0.01)
        await tts.close()
        self.assertTrue(socket.closed)

    async def test_server_error_is_exposed_and_socket_is_closed(self) -> None:
        socket = FakeSocket(
            [
                {"type": "session.created"},
                {
                    "type": "error",
                    "error": {"code": "invalid_value", "message": "bad voice"},
                },
            ]
        )

        async def connector(url, headers):
            return socket

        tts = QwenRealtimeTtsSynthesizer(
            api_key="test-key",
            connector=connector,
        )
        with self.assertRaisesRegex(RuntimeError, "bad voice"):
            await tts.prepare("保持自然")
        self.assertTrue(socket.closed)


if __name__ == "__main__":
    unittest.main()
