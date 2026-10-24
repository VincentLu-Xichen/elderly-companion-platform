"""Lesson-one output policy; state transitions remain owned by runtime."""

import re

VERSION = "lesson1-natural/1"


def enabled(state):
    return (
        state.get("lesson_id") == "lesson-1"
        and "blueprint" in state
        and state.get("dialogue_policy") == VERSION
    )


def confirms_record(state, text):
    # Only an answer to the current record check, never general authorization.
    return (
        enabled(state)
        and state.get("stage") == "review"
        and bool(
            re.fullmatch(
                r"(?:准确|准确的|是准确的|没问题|没有问题|核对无误|记录准确|记录无误|确认这份记录)[。.!！\s]*",
                text.strip(),
            )
        )
    )


def navigation_reply(text, receipt):
    # The model acknowledges intentions before execution; only the receipt may
    # report a completed write/control. Preserve the receipt on unsafe claims.
    if not text or any(
        word in text
        for word in (
            "已保存",
            "已确认",
            "已完成",
            "已修改",
            "已经保存",
            "已经确认",
            "已经完成",
            "已经修改",
            "本课结束",
        )
    ):
        return receipt
    return text.strip() + "\n" + receipt
