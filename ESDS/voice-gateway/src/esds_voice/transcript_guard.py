"""Reject short / hallucinated / non-Chinese ASR text before creating a reply."""

from __future__ import annotations

import re

from .barge_in import normalize_utterance

# Re-export barge-in tables so reply gating stays consistent with interrupt policy.
from .barge_in import _DEFAULT_FILLERS as _FILLERS
from .barge_in import _DEFAULT_FORCE_INTERRUPT as _FORCE_REPLY


# Exact / near-exact junk SenseVoice / Qwen emit on room noise or echo.
# Prefer exact match for short tokens so real sentences are not trapped.
_HALLUCINATION_EXACT = frozenset(
    {
        "字幕by",
        "字幕by索拉",
        "字幕byamara",
        "谢谢观看",
        "感谢观看",
        "请不吝点赞",
        "订阅",
        "打赏",
        "明镜与点点栏目",
        "优优独播剧场",
        "微博点赞抽奖",
        "将字幕移动到这边",
        "yeahyeahyeah",
        "lalala",
        "hahaha",
        "哦哦哦哦",
        "啊啊啊啊",
        "嗯嗯嗯嗯",
        "的的的的",
        "我我我我",
        "是是是是",
    }
)

_REPEAT_RUN = re.compile(r"(.)\1{3,}")
_REPEAT_TOKEN = re.compile(r"^(.{1,4})\1{2,}$")
# Latin letters (incl. common Latin Extended) — English and other Latin-script ASR.
_LATIN = re.compile(r"[A-Za-z\u00C0-\u024F\u1E00-\u1EFF]")
# Japanese kana (hiragana / katakana / small kana).
_KANA = re.compile(r"[\u3040-\u30FF\u31F0-\u31FF]")
# Korean Hangul syllables / jamo / compatibility jamo.
_HANGUL = re.compile(r"[\u1100-\u11FF\u3130-\u318F\uAC00-\uD7AF]")


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= character <= "\u9fff" for character in text)


def _has_non_chinese_script(text: str) -> bool:
    """True when Latin / Japanese kana / Hangul appear (product is Chinese-only)."""
    return bool(_LATIN.search(text) or _KANA.search(text) or _HANGUL.search(text))


def _is_hallucination(normalized: str) -> bool:
    if normalized in _HALLUCINATION_EXACT:
        return True
    # Longer canned phrases may appear with a trailing particle.
    for phrase in _HALLUCINATION_EXACT:
        if len(phrase) < 4:
            continue
        if phrase in normalized and len(normalized) <= len(phrase) + 2:
            return True
    return False


def unreliable_transcript_reason(
    text: str,
    *,
    min_chars: int = 2,
) -> str | None:
    """Return a rejection reason, or None when the transcript may be answered."""
    normalized = normalize_utterance(text)
    if not normalized:
        # Bare punctuation / symbols (e.g. "。") normalize away → no reply.
        return "empty"

    # Any single remaining character: 嗯 / 啊 / 喂 / "a" / …
    if len(normalized) == 1:
        return "single_char"

    # Non-Chinese languages or mixed foreign script → silence.
    if _has_non_chinese_script(normalized) or not _has_cjk(normalized):
        return "non_chinese"

    # Intentional short Chinese greetings / stop commands still deserve a reply
    # (must be ≥2 chars after the single_char gate above).
    if any(
        phrase and phrase in normalized
        for phrase in _FORCE_REPLY
        if _has_cjk(phrase) and len(normalize_utterance(phrase)) >= 2
    ):
        return None

    if normalized in _FILLERS:
        return "filler"

    for filler in _FILLERS:
        if len(filler) >= 1 and re.fullmatch(rf"(?:{re.escape(filler)})+", normalized):
            return "filler_repeat"

    if _is_hallucination(normalized):
        return "hallucination_phrase"

    if _REPEAT_RUN.search(normalized):
        return "char_run"

    if _REPEAT_TOKEN.fullmatch(normalized):
        return "token_repeat"

    # Dominated by one character (e.g. 我我我我我).
    if len(normalized) >= 4:
        top = max(normalized.count(ch) for ch in set(normalized))
        if top / len(normalized) >= 0.75:
            return "char_dominance"

    if len(normalized) < max(1, min_chars):
        return "too_short"

    return None


def should_skip_reply(text: str, *, min_chars: int = 2) -> bool:
    return unreliable_transcript_reason(text, min_chars=min_chars) is not None
