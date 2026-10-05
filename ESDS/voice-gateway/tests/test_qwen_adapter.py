import base64
import json
import unittest
from array import array

from esds_voice.providers.qwen_realtime import (
    Pcm24kTo16k,
    QwenRealtimeProvider,
)


class CaptureWebSocket:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, payload: str) -> None:
        self.sent.append(payload)


class InvalidWorkspaceResponse:
    status_code = 400
    body = b'{"code":"BadRequest.IllegalEndpoint"}'


def provider() -> QwenRealtimeProvider:
    return QwenRealtimeProvider(
        api_key="test-key",
        workspace_id="ws-test",
        region="beijing",
        model="qwen3.5-omni-flash-realtime",
        voice="Tina",
        instructions="brief",
    )


class QwenAdapterTests(unittest.TestCase):
    def test_resamples_one_20ms_frame_to_16khz(self) -> None:
        source = array("h", range(480)).tobytes()
        converter = Pcm24kTo16k()
        converted = converter.process(source) + converter.process(b"", final=True)
        self.assertEqual(len(converted), 320 * 2)
        self.assertEqual(converter.quality, "soxr-HQ")

    def test_resampler_preserves_streaming_frame_count(self) -> None:
        converter = Pcm24kTo16k()
        frames = [array("h", [index] * 480).tobytes() for index in range(5)]
        converted = b"".join(converter.process(frame) for frame in frames)
        converted += converter.process(b"", final=True)
        self.assertEqual(len(converted), 5 * 320 * 2)

    def test_resampler_reset_discards_previous_stream_state(self) -> None:
        converter = Pcm24kTo16k()
        converter.process(array("h", [1000] * 480).tobytes())
        converter.reset()
        source = array("h", [2000] * 480).tobytes()
        converted = converter.process(source) + converter.process(b"", final=True)
        self.assertEqual(len(converted), 320 * 2)

    def test_session_disables_cloud_vad_for_local_emotion_fusion(self) -> None:
        event = provider()._session_update("brief", full=True)
        session = event["session"]
        self.assertIsNone(session["turn_detection"])
        self.assertEqual(session["input_audio_format"], "pcm")
        self.assertEqual(session["output_audio_format"], "pcm")

    def test_connection_uses_required_realtime_beta_header(self) -> None:
        headers = provider()._connection_headers()
        self.assertEqual(headers["Authorization"], "Bearer test-key")
        self.assertEqual(headers["OpenAI-Beta"], "realtime=v1")

    def test_endpoints_include_dedicated_and_official_compatibility_urls(self) -> None:
        dedicated, legacy = provider()._endpoint_urls()
        self.assertIn("ws-test.cn-beijing.maas.aliyuncs.com", dedicated)
        self.assertIn("dashscope.aliyuncs.com", legacy)
        self.assertIn("model=qwen3.5-omni-flash-realtime", dedicated)

    def test_only_illegal_workspace_endpoint_enables_fallback(self) -> None:
        self.assertTrue(
            provider()._is_invalid_workspace_response(InvalidWorkspaceResponse())
        )
        other = InvalidWorkspaceResponse()
        other.body = b'{"code":"InvalidApiKey"}'
        self.assertFalse(provider()._is_invalid_workspace_response(other))

    def test_maps_qwen_transcript_preview(self) -> None:
        event = QwenRealtimeProvider._map_event(
            {
                "type": "conversation.item.input_audio_transcription.delta",
                "item_id": "user-1",
                "text": "今天",
                "stash": "有点累",
                "emotion": "sad",
                "language": "zh",
            }
        )
        self.assertEqual(event.type, "user.transcript")
        self.assertEqual(event.text, "今天有点累")
        self.assertFalse(event.data["final"])
        self.assertEqual(event.data["provider_emotion"], "sad")

    def test_maps_qwen_audio_delta(self) -> None:
        payload = b"\x01\x02\x03\x04"
        event = QwenRealtimeProvider._map_event(
            {
                "type": "response.audio.delta",
                "delta": base64.b64encode(payload).decode(),
                "item_id": "answer-1",
                "response_id": "response-1",
            }
        )
        self.assertEqual(event.type, "audio.delta")
        self.assertEqual(event.audio, payload)
        self.assertEqual(event.data["response_id"], "response-1")

    def test_completed_transcript_keeps_cloud_emotion(self) -> None:
        event = QwenRealtimeProvider._map_event(
            {
                "type": "conversation.item.input_audio_transcription.completed",
                "item_id": "user-1",
                "transcript": "我现在有点担心",
                "emotion": "fearful",
                "language": "zh",
            }
        )
        self.assertTrue(event.data["final"])
        self.assertEqual(event.data["provider_emotion"], "fearful")


class QwenAdapterAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_audio_is_resampled_then_committed(self) -> None:
        adapter = provider()
        socket = CaptureWebSocket()
        adapter._socket = socket
        await adapter.send_audio(array("h", [1000] * 480).tobytes())
        await adapter.finish_audio_turn()

        events = [json.loads(item) for item in socket.sent]
        self.assertEqual(events[0]["type"], "input_audio_buffer.append")
        self.assertEqual(len(base64.b64decode(events[0]["audio"])), 320 * 2)
        self.assertEqual(events[-1]["type"], "input_audio_buffer.commit")

    async def test_instruction_update_precedes_bare_response_create(self) -> None:
        adapter = provider()
        socket = CaptureWebSocket()
        adapter._socket = socket
        await adapter.update_instructions("empathetic")
        await adapter.create_response("empathetic")

        events = [json.loads(item) for item in socket.sent]
        self.assertEqual(events[0]["type"], "session.update")
        self.assertEqual(events[0]["session"]["instructions"], "empathetic")
        self.assertEqual(events[1], {"type": "response.create"})


if __name__ == "__main__":
    unittest.main()
