"""Conservative lexical hints, not a general sentiment classifier.

Negation, reported speech and tense have priority over keyword matches. Complex
or mixed language produces uncertainty instead of a confident invented mood.
"""

from __future__ import annotations

import re

_CLAUSE = re.compile(r"[，,。.!！？?；;\n]+|但是|不过|可是|而是")
_SUBJECT = re.compile(r"我|你|您|他们|她们|他|她|邻居|朋友|儿子|女儿|老伴|丈夫|妻子")
_NEGATION = re.compile(
    r"(?:不是|没有|不再|并不|不|没|别|不要|不用|无需|谈不上|说不上)"
    r"(?:(?:很|太|那么|这么|特别|真的|感到|觉得|再|会|是|怎么|一点|也|还))*$"
    r"|\b(?:not|never|no longer)(?:\s+(?:very|really|so|that|at all))*\s*$",
    re.IGNORECASE,
)
_COMPLEX = re.compile(r"不是不|没有不|不能不|不得不|并非不|不可能不|才怪|难道|会不会|是否|是不是")
_HYPOTHETICAL = re.compile(r"如果|假如|要是|希望|祝愿|祝你|祝您|别|不要|不用|无需")
_TIME = re.compile(r"以前|昨天|上周|刚才|那时候|曾经|原来|过去|现在|今天|此刻|已经|如今|后来")
_CURRENT = {"现在", "今天", "此刻", "已经", "如今", "后来"}
_QUOTED = re.compile(r'“[^”]*”|「[^」]*」|"[^"\n]*"|‘[^’]*’')


def lexical_signals(text: str, groups: dict[str, set[str]]) -> tuple[dict[str, int], tuple[str, ...]]:
    counts = dict.fromkeys(groups, 0)
    evidence: list[str] = []
    # Quotes may be examples or somebody else's speech. Leave attribution to
    # the language model rather than treating quoted emotion as self-report.
    if _QUOTED.search(text):
        evidence.append("reported_emotion")
        text = _QUOTED.sub(" ", text)
    for phrase in ("开心果", "积累", "累计", "累积", "困难", "困惑", "困扰", "困境", "麻烦你", "麻烦您"):
        text = text.replace(phrase, " ")

    subject = "self"
    for clause in _CLAUSE.split(text):
        if not clause.strip():
            continue
        subjects = list(_SUBJECT.finditer(clause))
        for category, words in groups.items():
            for word in words:
                pattern = re.escape(word)
                if word.isascii():
                    pattern = rf"(?<![a-z]){pattern}(?![a-z])"
                for match in re.finditer(pattern, clause, re.IGNORECASE):
                    prefix = clause[:match.start()]
                    earlier = [item for item in subjects if item.start() < match.start()]
                    speaker = ("self" if earlier[-1].group() == "我" else "other") if earlier else subject
                    if re.search(r"我(?:是)?(?:为|替|对|因|因为|由于)", prefix):
                        speaker = "self"
                    if speaker != "self":
                        evidence.append("reported_emotion")
                        continue
                    times = list(_TIME.finditer(prefix))
                    if times and times[-1].group() not in _CURRENT:
                        evidence.append("past_emotion")
                        continue
                    if _COMPLEX.search(clause) or _HYPOTHETICAL.search(prefix) or clause.rstrip().endswith(("吗", "么")):
                        evidence.append("ambiguous_words")
                        continue
                    if _NEGATION.search(prefix):
                        evidence.append("negated_emotion")
                        # Not happy is a negative hint; not sad does NOT prove
                        # happiness. Double negation was rejected above.
                        if category == "positive":
                            counts["negative"] += 1
                        continue
                    counts[category] += 1
        if subjects:
            subject = "self" if subjects[-1].group() == "我" else "other"
    if counts["positive"] and any(counts[key] for key in ("negative", "anxious", "angry", "tired")):
        evidence.append("mixed_emotions")
    return counts, tuple(dict.fromkeys(evidence))
