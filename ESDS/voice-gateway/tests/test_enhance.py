"""Speech enhancement unit tests."""

from __future__ import annotations

import unittest
from array import array

from esds_voice.enhance import (
    IdentityEnhancer,
    create_speech_enhancer,
)


def _pcm16_silence(samples: int = 480) -> bytes:
    return array("h", [0] * samples).tobytes()


def _pcm16_tone(samples: int = 480, amp: int = 4000) -> bytes:
    return array("h", [amp if i % 2 == 0 else -amp for i in range(samples)]).tobytes()


class EnhanceTests(unittest.TestCase):
    def test_disabled_returns_none(self) -> None:
        self.assertIsNone(
            create_speech_enhancer(enabled=False, backend="rnnoise", sample_rate=24_000)
        )

    def test_none_backend_returns_none(self) -> None:
        self.assertIsNone(
            create_speech_enhancer(enabled=True, backend="none", sample_rate=24_000)
        )

    def test_identity_preserves_bytes(self) -> None:
        pcm = _pcm16_tone()
        self.assertEqual(IdentityEnhancer().process(pcm), pcm)

    def test_create_enhancer_length_stable(self) -> None:
        enhancer = create_speech_enhancer(
            enabled=True, backend="rnnoise", sample_rate=24_000
        )
        self.assertIsNotNone(enhancer)
        pcm = _pcm16_silence(480)
        out = enhancer.process(pcm)
        self.assertEqual(len(out), len(pcm))
        tone = _pcm16_tone(480)
        out_tone = enhancer.process(tone)
        self.assertEqual(len(out_tone), len(tone))

    def test_spectral_backend_explicit(self) -> None:
        enhancer = create_speech_enhancer(
            enabled=True, backend="spectral", sample_rate=24_000
        )
        self.assertIsNotNone(enhancer)
        self.assertEqual(type(enhancer).__name__, "SpectralGateEnhancer")
        pcm = _pcm16_tone(480)
        self.assertEqual(len(enhancer.process(pcm)), len(pcm))


if __name__ == "__main__":
    unittest.main()
