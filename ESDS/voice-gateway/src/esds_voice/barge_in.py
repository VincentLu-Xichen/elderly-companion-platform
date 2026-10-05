from __future__ import annotations

import re
import unicodedata

# Standalone particles / backchannels that noisy rooms and weak ASR often emit.
# Keep this list narrow: greetings like 你好/喂 must NOT live here.
_DEFAULT_FILLERS = frozenset(
    {
        "嗯",
        "嗯嗯",
        "嗯哼",
        "啊",
        "啊啊",
        "哦",
        "噢",
        "喔",
        "呃",
        "额",
        "唔",
        "呵",
        "呵呵",
        "嘻",
        "哼",
        "哈",
        "哈哈",
        "欸",
        "诶",
        "呢",
        "吧",
        "呀",
        "哪",
        "哇",
        "好",
        "好的",
        "好吧",
        "行",
        "行吧",
        "对",
        "对的",
        "是",
        "是的",
        "是啊",
        "哦好",
        "嗯好",
        "okay",
        "ok",
        "oke",
        "yeah",
        "yea",
        "yep",
        "yup",
        "yes",
        "yah",
        "ya",
        "uh",
        "um",
        "umm",
        "huh",
        "hmm",
        "hm",
        "mhm",
        "mm",
        "mmm",
        "ah",
        "oh",
        "ooh",
        "wow",
        "right",
        "sure",
    }
)

# Always cut / always answer — short greetings and explicit stop commands.
_DEFAULT_FORCE_INTERRUPT = frozenset(
    {
        "你好",
        "您好",
        "哈喽",
        "哈啰",
        "喂",
        "嗨",
        "在吗",
        "在不在",
        "听得到吗",
        "听得到我吗",
        "可以听到吗",
        "可以听到我说话吗",
        "hello",
        "hi",
        "hey",
        "停下",
        "停一下",
        "你停一下",
        "先停",
        "别说了",
        "你别说了",
        "闭嘴",
        "暂停",
        "打断",
        "打断一下",
        "不要说了",
        "stop",
        "quiet",
        "silence",
    }
)


def normalize_utterance(text: str) -> str:
    """Lowercase and strip spaces/punctuation for barge-in decisions."""
    pieces: list[str] = []
    for character in text.casefold():
        category = unicodedata.category(character)
        if category.startswith(("P", "S", "Z")):
            continue
        pieces.append(character)
    return "".join(pieces)


def is_interrupt_worthy(
    text: str,
    *,
    duration_ms: float | None = None,
    min_chars: int = 2,
    min_duration_ms: float = 280.0,
    fillers: frozenset[str] | None = None,
    force_phrases: frozenset[str] | None = None,
) -> bool:
    """Return True when barge-in should cut assistant playback.

    Filters narrow backchannels ("嗯", "Yeah") and ultra-short noise bursts,
    while keeping greetings, stop commands, and real clauses.
    """
    normalized = normalize_utterance(text)
    if not normalized:
        return False

    force = force_phrases if force_phrases is not None else _DEFAULT_FORCE_INTERRUPT
    if any(phrase and phrase in normalized for phrase in force):
        return True

    filler_set = fillers if fillers is not None else _DEFAULT_FILLERS
    if normalized in filler_set:
        return False

    # Repeated particles: "嗯嗯嗯", "yeahyeah"
    for filler in filler_set:
        if len(filler) >= 1 and re.fullmatch(rf"(?:{re.escape(filler)})+", normalized):
            return False

    if duration_ms is not None and duration_ms < min_duration_ms:
        return False

    if len(normalized) < max(1, min_chars):
        return False

    return True
