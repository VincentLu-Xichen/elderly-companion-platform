import unittest

from esds_voice.config import Settings
from esds_voice.protocol import DeviceHello
from esds_voice.providers.qwen_realtime import QwenRealtimeProvider
from esds_voice.providers.agent_bridge import AgentBridgeChatClient
from esds_voice.providers.local_companion import LocalCompanionProvider
from esds_voice.server import Gateway


class GatewayProviderTests(unittest.TestCase):
    def test_bailian_realtime_provider_remains_available(self) -> None:
        settings = Settings(
            runtime_provider="qwen_realtime",
            emotion_backend="heuristic",
            dashscope_api_key="test-key",
            qwen_realtime_workspace_id="workspace",
        )
        gateway = Gateway(settings)
        hello = DeviceHello.parse(
            '{"type":"device.hello","protocol":"companion-audio/1",'
            '"device_id":"pi","device_type":"raspberry_pi_audio",'
            '"audio":{"sample_rate":24000,"channels":1,'
            '"format":"pcm16","frame_ms":20},"capabilities":["audio"]}'
        )
        provider = gateway._provider_for(hello)
        self.assertIsInstance(provider, QwenRealtimeProvider)
        self.assertEqual(provider.workspace_id, "workspace")

    def test_agent_bridge_uses_modular_bailian_asr_and_tts(self) -> None:
        settings = Settings(
            runtime_provider="local",
            asr_provider="qwen",
            chat_provider="agent_bridge",
            tts_provider="qwen",
            emotion_backend="heuristic",
            dashscope_api_key="test-key",
            agent_bridge_token="bridge-token",
            agent_bridge_device_id="esds-pi-test",
        )
        gateway = Gateway(settings)
        hello = DeviceHello.parse(
            '{"type":"device.hello","protocol":"companion-audio/1",'
            '"device_id":"pi","device_type":"raspberry_pi_audio",'
            '"audio":{"sample_rate":24000,"channels":1,'
            '"format":"pcm16","frame_ms":20},"capabilities":["audio"]}'
        )
        provider = gateway._provider_for(hello)
        self.assertIsInstance(provider, LocalCompanionProvider)
        self.assertIsInstance(provider.chat_client, AgentBridgeChatClient)


if __name__ == "__main__":
    unittest.main()
