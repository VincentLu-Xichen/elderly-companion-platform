from __future__ import annotations

from typing import Any


LESSON_1_ID = "lesson-1"
LESSON_1_VERSION = "7.9.3-deferred-rating-scale"
LESSON_2_ID = "lesson-2"
LESSON_2_VERSION = "6.2-contrast-reply"
LESSON_VERSIONS = {LESSON_1_ID: LESSON_1_VERSION, LESSON_2_ID: LESSON_2_VERSION}

_COURSES = [
    (
        "认知行为三角",
        "围绕一件困扰学习四要素，回看认知行为模型，再辨认练习并制定课程目标。",
        "同例教学 · 两项评分 · 模型回顾与课程目标",
    ),
    (
        "捕捉我的思维",
        "回顾课后尝试，复习三个概念，在雨天教学对照中学习捕捉自动思维，再练习三栏记录。",
        "三题复习 · 自动思维 · 三栏与情绪强度",
    ),
]

COURSE_CATALOG: list[dict[str, Any]] = [
    {
        "id": f"lesson-{number}",
        "number": number,
        "title": title,
        "summary": summary,
        "practice": practice,
        "available": True,
        "duration": "按自己的节奏",
    }
    for number, (title, summary, practice) in enumerate(_COURSES, start=1)
]


def course_by_id(lesson_id: str) -> dict[str, Any] | None:
    return next((course for course in COURSE_CATALOG if course["id"] == lesson_id), None)


def require_available_course(lesson_id: str) -> dict[str, Any]:
    course = course_by_id(lesson_id)
    if course is None:
        raise ValueError("课程不存在。")
    if not course["available"]:
        raise ValueError("这节课尚未上线。")
    return course


def lesson_version(lesson_id: str) -> str:
    try:
        return LESSON_VERSIONS[lesson_id]
    except KeyError as exc:
        raise ValueError("课程不存在。") from exc


def is_active_lesson(lesson_id: str | None) -> bool:
    return lesson_id in LESSON_VERSIONS
