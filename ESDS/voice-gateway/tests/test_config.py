import os
import unittest
from unittest import mock

from esds_voice.config import Settings


class SettingsTests(unittest.TestCase):
    def test_local_modular_profile_accepts_bailian_asr_and_tts(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "ESDS_RUNTIME_PROVIDER": "local",
                "ESDS_ASR_PROVIDER": "qwen",
                "ESDS_EMOTION_BACKEND": "heuristic",
                "ESDS_TTS_PROVIDER": "qwen",
                "DASHSCOPE_API_KEY": "test-key",
            },
            clear=True,
        ):
            settings = Settings.from_env()
        self.assertEqual(settings.runtime_provider, "local")
        self.assertEqual(settings.asr_provider, "qwen")
        self.assertEqual(settings.tts_provider, "qwen")

    def test_qwen_realtime_profile_requires_workspace(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "ESDS_RUNTIME_PROVIDER": "qwen_realtime",
                "ESDS_EMOTION_BACKEND": "heuristic",
                "DASHSCOPE_API_KEY": "test-key",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "WORKSPACE_ID"):
                Settings.from_env()

    def test_agent_bridge_profile_requires_device_credentials(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "ESDS_RUNTIME_PROVIDER": "local",
                "ESDS_ASR_PROVIDER": "qwen",
                "ESDS_CHAT_PROVIDER": "agent_bridge",
                "ESDS_EMOTION_BACKEND": "heuristic",
                "ESDS_TTS_PROVIDER": "qwen",
                "DASHSCOPE_API_KEY": "test-key",
                "ESDS_AGENT_BRIDGE_TOKEN": "bridge-token",
                "ESDS_AGENT_BRIDGE_DEVICE_ID": "esds-pi-test",
            },
            clear=True,
        ):
            settings = Settings.from_env()
        self.assertEqual(settings.chat_provider, "agent_bridge")
        self.assertEqual(settings.agent_bridge_device_id, "esds-pi-test")

    def test_qwen_realtime_profile_is_valid_for_lightweight_gateway(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "ESDS_RUNTIME_PROVIDER": "qwen_realtime",
                "ESDS_EMOTION_BACKEND": "heuristic",
                "DASHSCOPE_API_KEY": "test-key",
                "ESDS_QWEN_REALTIME_WORKSPACE_ID": "workspace",
            },
            clear=True,
        ):
            settings = Settings.from_env()
        self.assertEqual(settings.runtime_provider, "qwen_realtime")
        self.assertEqual(settings.emotion_backend, "heuristic")


if __name__ == "__main__":
    unittest.main()
