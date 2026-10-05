import asyncio
import unittest

from esds_voice.providers.local_companion import (
    LocalCompanionProvider,
    _extract_speakable_segments,
    _voice_style,
    sanitize_spoken_text,
)
from esds_voice.transcription import TranscriptionResult
from esds_voice.contracts import EmotionSnapshot


class FakeTranscriber:
    def __init__(self) -> None:
        self.warmed = False
        self.audio_bytes = 0

    def warmup(self) -> None:
        self.warmed = True

    def transcribe_pcm16(self, pcm: bytes, sample_rate: int):
        self.audio_bytes += len(pcm)
        return TranscriptionResult("我今天有点累", "zh", "Speech", 12.0)


class FakeStreamingTranscriber:
    def __init__(self) -> None:
        self.warmed = False
        self.started_rates = []
        self.audio_bytes = 0
        self.finished = 0
        self.closed = False

    async def warmup(self) -> None:
        self.warmed = True

    async def start_stream(self, sample_rate: int) -> None:
        self.started_rates.append(sample_rate)

    async def send_stream_audio(self, pcm: bytes) -> None:
        self.audio_bytes += len(pcm)

    async def finish_stream(self):
        self.finished += 1
        return TranscriptionResult("闺蜜镜你好", "zh", "happy", 88.0)

    async def close(self) -> None:
        self.closed = True


class FakeChatClient:
    def __init__(self) -> None:
        self.warmed = False
        self.messages = []

    async def warmup(self) -> None:
        self.warmed = True

    async def stream_reply(self, messages):
        self.messages = messages
        for token in ["听起来", "今天挺辛苦的。", "先歇一会儿吧。"]:
            yield token


class FakeSynthesizer:
    def __init__(self) -> None:
        self.sentences = []

    async def stream_pcm24k(self, text: str, *, instructions: str):
        self.sentences.append((text, instructions))
        yield b"\x01\x00" * 480


class LocalCompanionProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_per_turn_context_reaches_chat_without_leaking(self):
        class ContextChat(FakeChatClient):
            def __init__(self):
                super().__init__()
                self.hints = []
            async def stream_reply_with_emotion(self, messages, emotion):
                self.hints.append(emotion)
                yield "我在听。"
        chat = ContextChat()
        provider = LocalCompanionProvider(transcriber=FakeTranscriber(), chat_client=chat, synthesizer=FakeSynthesizer(), instructions="base")
        await provider.connect()
        events = provider.events()
        hint = EmotionSnapshot(0, 0, "low", .45, ("low_energy_words",))
        try:
            for context in (hint, None):
                await provider.send_audio(bytes(960))
                await provider.finish_audio_turn()
                await anext(events)
                if context is None:
                    await provider.create_response("base")
                else:
                    await provider.create_response_with_emotion("base", context)
                while (await asyncio.wait_for(anext(events), timeout=2)).type != "response.done":
                    pass
            self.assertEqual(chat.hints, [hint, None])
        finally:
            await provider.close()

    async def test_streaming_asr_receives_live_chunks_and_exposes_emotion(self) -> None:
        transcriber = FakeStreamingTranscriber()
        provider = LocalCompanionProvider(
            transcriber=transcriber,
            chat_client=FakeChatClient(),
            synthesizer=FakeSynthesizer(),
            instructions="base",
        )
        await provider.connect()
        await provider.send_audio(b"\x00\x00" * 480)
        await provider.send_audio(b"\x01\x00" * 480)
        await provider.finish_audio_turn()

        event = await anext(provider.events())
        self.assertTrue(transcriber.warmed)
        self.assertEqual(transcriber.started_rates, [24_000])
        self.assertEqual(transcriber.audio_bytes, 1_920)
        self.assertEqual(transcriber.finished, 1)
        self.assertEqual(event.text, "闺蜜镜你好")
        self.assertEqual(event.data["asr_emotion"], "happy")
        await provider.close()
        self.assertTrue(transcriber.closed)

    async def test_complete_local_turn_streams_transcript_text_and_audio(self) -> None:
        transcriber = FakeTranscriber()
        chat = FakeChatClient()
        tts = FakeSynthesizer()
        provider = LocalCompanionProvider(
            transcriber=transcriber,
            chat_client=chat,
            synthesizer=tts,
            instructions="base",
        )
        await provider.connect()
        self.assertTrue(transcriber.warmed)
        self.assertTrue(chat.warmed)

        await provider.send_audio(b"\x00\x00" * 960)
        await provider.finish_audio_turn()
        events = provider.events()
        transcript = await anext(events)
        self.assertEqual(transcript.type, "user.transcript")
        self.assertEqual(transcript.text, "我今天有点累")

        await provider.create_response("语速稍慢、句子短一些")
        received = []
        while True:
            event = await asyncio.wait_for(anext(events), timeout=1)
            received.append(event)
            if event.type == "response.done":
                break

        self.assertTrue(any(event.type == "audio.delta" for event in received))
        self.assertTrue(any(event.type == "assistant.transcript.done" for event in received))
        self.assertEqual(received[-1].data["status"], "completed")
        self.assertEqual(chat.messages[-1]["content"], "我今天有点累")
        self.assertEqual(
            [sentence for sentence, _ in tts.sentences],
            ["听起来今天挺辛苦的。", "先歇一会儿吧。"],
        )
        await provider.close()

    async def test_empty_create_response_does_not_cancel_in_flight_reply(self) -> None:
        class SlowChat(FakeChatClient):
            async def stream_reply(self, messages):
                yield "先接住你。"
                await asyncio.sleep(0.2)
                yield "再说一句。"

        tts = FakeSynthesizer()
        provider = LocalCompanionProvider(
            transcriber=FakeTranscriber(),
            chat_client=SlowChat(),
            synthesizer=tts,
            instructions="base",
        )
        await provider.connect()
        await provider.send_audio(b"\x00\x00" * 480)
        await provider.finish_audio_turn()
        events = provider.events()
        await anext(events)  # user.transcript
        await provider.create_response("base")
        # Stale second wait with empty pending text must not kill TTS.
        await provider.create_response("stale-wait")
        received = []
        while True:
            event = await asyncio.wait_for(anext(events), timeout=2)
            received.append(event)
            if event.type == "response.done":
                break
        self.assertEqual(received[-1].data["status"], "completed")
        self.assertFalse(
            any(
                event.type == "error"
                and event.data.get("code") == "local_missing_transcript"
                for event in received
            )
        )
        self.assertGreaterEqual(len(tts.sentences), 1)
        await provider.close()

    async def test_cancel_marks_active_response_cancelled(self) -> None:
        class SlowChat(FakeChatClient):
            async def stream_reply(self, messages):
                yield "我在听。"
                await asyncio.sleep(10)

        provider = LocalCompanionProvider(
            transcriber=FakeTranscriber(),
            chat_client=SlowChat(),
            synthesizer=FakeSynthesizer(),
            instructions="base",
        )
        await provider.connect()
        await provider.send_audio(b"\x00\x00" * 480)
        await provider.finish_audio_turn()
        events = provider.events()
        await anext(events)
        await provider.create_response("base")
        self.assertEqual((await anext(events)).type, "response.started")
        await provider.cancel(item_id=None, played_ms=0)
        statuses = []
        while True:
            event = await asyncio.wait_for(anext(events), timeout=1)
            if event.type == "response.done":
                statuses.append(event.data["status"])
                break
        self.assertEqual(statuses, ["cancelled"])
        await provider.close()

    async def test_scripted_scene_response_bypasses_llm_and_streams_tts(self) -> None:
        transcriber = FakeTranscriber()
        chat = FakeChatClient()
        tts = FakeSynthesizer()
        provider = LocalCompanionProvider(
            transcriber=transcriber,
            chat_client=chat,
            synthesizer=tts,
            instructions="base",
        )
        await provider.connect()
        await provider.create_scripted_response("麦克风已经关闭。", "隐私场景")
        events = provider.events()
        received = []
        while True:
            event = await asyncio.wait_for(anext(events), timeout=1)
            received.append(event)
            if event.type == "response.done":
                break
        self.assertEqual(chat.messages, [])
        self.assertEqual(provider._history, [])
        self.assertEqual([text for text, _ in tts.sentences], ["麦克风已经关闭。"])
        self.assertEqual(
            next(event.text for event in received if event.type == "assistant.transcript.done"),
            "麦克风已经关闭。",
        )
        await provider.close()

    async def test_proactive_script_is_remembered_for_the_users_answer(self) -> None:
        provider = LocalCompanionProvider(
            transcriber=FakeTranscriber(),
            chat_client=FakeChatClient(),
            synthesizer=FakeSynthesizer(),
            instructions="base",
        )
        await provider.connect()
        question = "最近在循环听什么歌？"
        await provider.create_scripted_response(
            question,
            "轻松好奇",
            remember=True,
        )
        events = provider.events()
        while True:
            event = await asyncio.wait_for(anext(events), timeout=1)
            if event.type == "response.done":
                break

        self.assertEqual(
            provider._history,
            [{"role": "assistant", "content": question}],
        )
        await provider.close()

    async def test_tts_failure_closes_response_instead_of_hanging(self) -> None:
        class FailingSynthesizer(FakeSynthesizer):
            async def stream_pcm24k(self, text: str, *, instructions: str):
                if False:
                    yield b""
                raise RuntimeError("tts unavailable")

        provider = LocalCompanionProvider(
            transcriber=FakeTranscriber(),
            chat_client=FakeChatClient(),
            synthesizer=FailingSynthesizer(),
            instructions="base",
        )
        await provider.connect()
        await provider.send_audio(b"\x00\x00" * 480)
        await provider.finish_audio_turn()
        events = provider.events()
        await anext(events)
        with self.assertLogs(
            "esds_voice.providers.local_companion", level="ERROR"
        ):
            await provider.create_response("base")
            received = []
            while True:
                event = await asyncio.wait_for(anext(events), timeout=1)
                received.append(event)
                if event.type == "response.done":
                    break
        self.assertTrue(any(event.type == "error" for event in received))
        self.assertEqual(received[-1].data["status"], "failed")
        await provider.close()

    async def test_prefetched_acknowledgement_is_first_audio(self) -> None:
        class PrefetchedSynthesizer(FakeSynthesizer):
            async def warmup(self) -> None:
                self.warmed = True

            async def acknowledgement(self, instructions: str):
                return "嗯，我在这儿。", b"\x02\x00" * 480

        tts = PrefetchedSynthesizer()
        provider = LocalCompanionProvider(
            transcriber=FakeTranscriber(),
            chat_client=FakeChatClient(),
            synthesizer=tts,
            instructions="base",
        )
        await provider.connect()
        self.assertTrue(tts.warmed)
        await provider.send_audio(b"\x00\x00" * 480)
        await provider.finish_audio_turn()
        events = provider.events()
        await anext(events)
        await provider.create_response("语速稍慢")
        seen = [await asyncio.wait_for(anext(events), timeout=1) for _ in range(4)]
        self.assertEqual(
            [event.type for event in seen],
            [
                "response.started",
                "response.item",
                "assistant.transcript.delta",
                "audio.delta",
            ],
        )
        self.assertTrue(seen[-1].data["prefetched"])
        await provider.close()


class LocalCompanionHelpersTests(unittest.TestCase):
    def test_sanitizes_emoji_and_markdown_before_tts(self) -> None:
        self.assertEqual(
            sanitize_spoken_text("真棒！😊 **慢慢说**`呀`"),
            "真棒！ 慢慢说呀",
        )

    def test_segments_early_at_chinese_punctuation(self) -> None:
        segments, remaining = _extract_speakable_segments("我明白你的意思。我们慢慢说")
        self.assertEqual(segments, ["我明白你的意思。"])
        self.assertEqual(remaining, "我们慢慢说")

    def test_emotion_instructions_adjust_voice_style(self) -> None:
        self.assertEqual(_voice_style("语速稍慢、句子短一些"), ("-8%", "-2Hz"))
        self.assertEqual(_voice_style("可以略带笑意回应"), ("+5%", "+2Hz"))
        self.assertEqual(_voice_style("保持自然"), ("+2%", "+1Hz"))


if __name__ == "__main__":
    unittest.main()
