import unittest

from esds_voice.contracts import AudioFeatures, EmotionSnapshot
from esds_voice.emotion import EmotionTracker
from esds_voice.policy import decide_empathy


class EmotionRegressionTests(unittest.TestCase):
    def test_common_chinese_phrases(self):
        cases = {
            "我很开心": "happy", "我很难过": "low", "我有点担心": "anxious",
            "我很生气": "angry", "我今天很累": "low", "我不开心": "low",
            "我不难过": "neutral", "我没有生气": "neutral", "我不太担心": "neutral",
            "我没觉得很难过": "neutral", "他很难过": "neutral",
            "朋友说她很焦虑": "neutral", "我觉得他很生气": "neutral",
            "昨天我很难过，现在好多了": "neutral", "我喜欢开心果": "happy",
            "这是开心果": "neutral", "积累了很多知识": "neutral",
            "麻烦你说慢一点": "neutral", "我有困难想问你": "neutral",
            "她很难过，但我很高兴": "happy", "我为女儿担心": "anxious",
            "我不是不开心": "uncertain", "我开心才怪": "uncertain",
            "如果我很生气怎么办": "uncertain", "我又高兴又担心": "uncertain",
            "他说“我很生气”": "neutral", "glove": "neutral", "I am not sad": "neutral",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(EmotionTracker().update_text(text).label, expected)

    def test_correction_replaces_partial_transcript(self):
        tracker = EmotionTracker()
        tracker.update_text("我很生气")
        result = tracker.update_text("我没有生气")
        self.assertEqual(result.label, "neutral")
        self.assertNotIn("angry_words", result.evidence)

    def test_new_turn_clears_previous_audio_model_and_text(self):
        tracker = EmotionTracker()
        tracker.update_text("我很生气")
        tracker.update_model("angry", source="emotion2vec", confidence=.9)
        tracker.update_audio(AudioFeatures(-12, -1, .3, .05, 480))
        tracker.begin_turn()
        result = tracker.update_text("桌上有一杯水")
        self.assertEqual(result.label, "neutral")
        self.assertEqual(result.evidence, ())
        self.assertLess(result.confidence, .35)

    def test_conflicting_words_and_model_are_uncertain(self):
        for model_first in (True, False):
            tracker = EmotionTracker()
            if model_first:
                tracker.update_model("angry", source="emotion2vec", confidence=.9)
            tracker.update_text("我很开心")
            if not model_first:
                tracker.update_model("angry", source="emotion2vec", confidence=.9)
            self.assertEqual(tracker.snapshot().label, "uncertain")
            self.assertLess(tracker.snapshot().confidence, .35)

    def test_negation_has_priority_over_model(self):
        tracker = EmotionTracker()
        tracker.update_model("angry", source="emotion2vec", confidence=.9)
        result = tracker.update_text("我没有生气")
        self.assertEqual(result.label, "uncertain")
        self.assertLess(result.confidence, .35)

    def test_low_model_score_is_not_inflated(self):
        tracker = EmotionTracker()
        result = tracker.update_model("angry", source="emotion2vec", confidence=0)
        self.assertEqual(result.label, "neutral")
        self.assertLess(result.confidence, .35)
        for bad in (float("nan"), float("inf"), -1, 1.1):
            with self.assertRaises(ValueError):
                tracker.update_model("angry", source="emotion2vec", confidence=bad)

    def test_snapshot_preserves_evidence_without_changing_state(self):
        tracker = EmotionTracker()
        result = tracker.update_text("我很担心")
        for _ in range(20):
            self.assertEqual(result, tracker.snapshot())
        self.assertIn("anxious_words", tracker.snapshot().evidence)

    def test_loudness_alone_remains_weak(self):
        tracker = EmotionTracker()
        for _ in range(100):
            result = tracker.update_audio(AudioFeatures(-12, -1, .3, .05, 480))
        self.assertLess(result.confidence, .35)
        self.assertNotIn(result.label, {"angry", "happy", "low"})

    def test_low_confidence_policy_does_not_bypass_threshold_for_keywords(self):
        result = decide_empathy(EmotionSnapshot(0, 0, "angry", .3, ("angry_words",)))
        self.assertIn("自然、清楚", result.content_instructions)
