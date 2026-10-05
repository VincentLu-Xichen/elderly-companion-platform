import json
import unittest

from esds_voice.protocol import DeviceHello, ProtocolError, event_json


def hello_body(**overrides):
    body = {
        "type": "device.hello",
        "protocol": "companion-audio/1",
        "device_id": "mirror-01",
        "device_type": "girlfriend_mirror",
        "audio": {
            "sample_rate": 24000,
            "channels": 1,
            "format": "pcm16",
            "frame_ms": 20,
        },
        "capabilities": ["barge_in", "display"],
    }
    body.update(overrides)
    return json.dumps(body)


class ProtocolTests(unittest.TestCase):
    def test_valid_hello(self) -> None:
        hello = DeviceHello.parse(hello_body())
        self.assertEqual(hello.audio.frame_bytes, 960)
        self.assertEqual(hello.device_id, "mirror-01")

    def test_rejects_wrong_audio_format(self) -> None:
        with self.assertRaisesRegex(ProtocolError, "24000"):
            DeviceHello.parse(
                hello_body(
                    audio={
                        "sample_rate": 16000,
                        "channels": 1,
                        "format": "pcm16",
                        "frame_ms": 20,
                    }
                )
            )

    def test_rejects_non_string_token(self) -> None:
        with self.assertRaisesRegex(ProtocolError, "token must be a string"):
            DeviceHello.parse(hello_body(token=123))

    def test_event_is_compact_unicode_json(self) -> None:
        event = json.loads(event_json("state.changed", state="正在听"))
        self.assertEqual(event["state"], "正在听")
        self.assertIsInstance(event["timestamp_ms"], int)


if __name__ == "__main__":
    unittest.main()
