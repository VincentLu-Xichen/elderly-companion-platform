import tempfile
import unittest
from pathlib import Path

from esds_voice.emotion_backends import (
    Emotion2VecAnalyzer,
    SenseVoiceEmotionAnalyzer,
    normalize_emotion2vec_label,
    normalize_sensevoice_emotion,
)


class EmotionBackendTests(unittest.TestCase):
    def test_normalizes_all_response_policy_labels(self) -> None:
        self.assertEqual(normalize_sensevoice_emotion("<|HAPPY|>"), "happy")
        self.assertEqual(normalize_sensevoice_emotion("SAD"), "low")
        self.assertEqual(normalize_sensevoice_emotion("ANGRY"), "angry")
        self.assertEqual(normalize_sensevoice_emotion("FEARFUL"), "anxious")
        self.assertEqual(normalize_sensevoice_emotion("SURPRISED"), "excited")
        self.assertIsNone(normalize_sensevoice_emotion("UNKNOWN"))

    def test_rejects_incomplete_model_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "tokens.txt").write_text("token", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "model.int8.onnx"):
                SenseVoiceEmotionAnalyzer(directory)

    def test_normalizes_emotion2vec_bilingual_labels(self) -> None:
        self.assertEqual(normalize_emotion2vec_label("生气/angry"), "angry")
        self.assertEqual(normalize_emotion2vec_label("难过/sad"), "low")
        self.assertEqual(normalize_emotion2vec_label("吃惊/surprised"), "excited")
        self.assertIsNone(normalize_emotion2vec_label("其他/other"))

    def test_rejects_incomplete_emotion2vec_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "model.pt"):
                Emotion2VecAnalyzer(directory)


if __name__ == "__main__":
    unittest.main()
