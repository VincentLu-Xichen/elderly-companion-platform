import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class NoVisualInputTests(unittest.TestCase):
    def test_visual_runtime_assets_are_absent(self) -> None:
        forbidden = [
            ROOT / "web" / "praise-auto.js",
            ROOT / "web" / "yiyan",
            ROOT / "web" / "models" / "face-api",
            ROOT / "src" / "esds_voice" / "praise_vision.py",
            ROOT / "src" / "esds_voice" / "yiyan_bridge.py",
        ]
        self.assertTrue(all(not path.exists() for path in forbidden))

    def test_browser_requests_audio_only(self) -> None:
        source = (ROOT / "web" / "audio-client.js").read_text()
        self.assertIn("getUserMedia({ audio })", source)
        self.assertNotIn("video:", source)
        self.assertNotIn("vision.snapshot", source)


if __name__ == "__main__":
    unittest.main()
