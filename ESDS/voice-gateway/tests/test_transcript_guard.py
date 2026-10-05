import unittest

from esds_voice.transcript_guard import (
    should_skip_reply,
    unreliable_transcript_reason,
)


class TranscriptGuardTests(unittest.TestCase):
    def test_allows_real_utterances_and_greetings(self) -> None:
        for text in (
            "今天有点累，想和你聊聊天",
            "你好",
            "可以听到我说话吗？",
            "提醒我明天下午改路演稿",
        ):
            with self.subTest(text=text):
                self.assertIsNone(unreliable_transcript_reason(text))

    def test_rejects_single_hanzi_and_fillers(self) -> None:
        for text, reason in (
            ("嗯", "single_char"),
            ("啊", "single_char"),
            ("喂", "single_char"),
            ("忙", "single_char"),
            ("好", "single_char"),
        ):
            with self.subTest(text=text):
                self.assertEqual(unreliable_transcript_reason(text), reason)

    def test_rejects_single_punctuation_and_symbols(self) -> None:
        for text in ("。", "！", "?", "…", "·", "."):
            with self.subTest(text=text):
                self.assertEqual(unreliable_transcript_reason(text), "empty")

    def test_rejects_non_chinese_languages(self) -> None:
        for text in (
            "Yeah.",
            "Yeah",
            "OK",
            "okay",
            "hello",
            "Hi!",
            "yes",
            "hmm",
            "こんにちは",
            "ありがとう",
            "안녕하세요",
            "감사합니다",
            "hello你好",
            "OK吗",
        ):
            with self.subTest(text=text):
                self.assertEqual(unreliable_transcript_reason(text), "non_chinese")

    def test_rejects_hallucinations(self) -> None:
        self.assertEqual(unreliable_transcript_reason("我我我我我"), "hallucination_phrase")
        self.assertEqual(unreliable_transcript_reason("谢谢观看"), "hallucination_phrase")
        self.assertEqual(unreliable_transcript_reason("哒哒哒哒哒"), "char_run")
        self.assertTrue(should_skip_reply("的的的的"))
        self.assertTrue(should_skip_reply("hahahahaha"))
        # Must not trap normal Chinese that merely contains a short junk token.
        self.assertIsNone(unreliable_transcript_reason("我想订阅这个频道吗"))


if __name__ == "__main__":
    unittest.main()
