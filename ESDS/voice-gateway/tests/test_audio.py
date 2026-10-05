import math
import unittest
from array import array

from esds_voice.audio import pcm16_features, pcm16_silence


class AudioFeaturesTests(unittest.TestCase):
    def test_silence_has_floor_level(self) -> None:
        features = pcm16_features(pcm16_silence())
        self.assertEqual(features.rms_dbfs, -96.0)
        self.assertEqual(features.peak_dbfs, -96.0)
        self.assertEqual(features.sample_count, 480)

    def test_known_amplitude(self) -> None:
        pcm = array("h", [16_384, -16_384] * 240).tobytes()
        features = pcm16_features(pcm)
        self.assertTrue(math.isclose(features.rms_dbfs, -6.02, abs_tol=0.03))
        self.assertGreater(features.zero_crossing_rate, 0.99)

    def test_odd_bytes_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            pcm16_features(b"\x00")


if __name__ == "__main__":
    unittest.main()

