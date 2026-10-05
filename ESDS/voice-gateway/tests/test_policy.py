import unittest

from esds_voice.contracts import EmotionSnapshot
from esds_voice.policy import decide_empathy, provider_instructions


class EmpathyPolicyTests(unittest.TestCase):
    def snapshot(self, label: str, confidence: float = 0.8) -> EmotionSnapshot:
        return EmotionSnapshot(0.0, 0.0, label, confidence, (), 0)

    def test_low_emotion_changes_content_and_delivery_independently(self) -> None:
        decision = decide_empathy(self.snapshot("low"))
        self.assertIn("不要说教", decision.content_instructions)
        self.assertIn("语速稍慢", decision.delivery_instructions)

    def test_low_confidence_falls_back_to_neutral(self) -> None:
        decision = decide_empathy(self.snapshot("angry", confidence=0.1))
        self.assertIn("自然、清楚", decision.content_instructions)
        self.assertNotIn("不要争辩", decision.content_instructions)

    def test_provider_bridge_contains_explicit_tts_delivery(self) -> None:
        instructions = provider_instructions(self.snapshot("anxious"))
        self.assertIn("<TTS_DELIVERY>", instructions)
        self.assertIn("低刺激", instructions)


if __name__ == "__main__":
    unittest.main()
