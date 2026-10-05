from __future__ import annotations

from typing import Any


LESSON_1_ID = "lesson-1"
LESSON_1_VERSION = "1.0-xmind-2023-10-18-llm-freeform"
LESSON_2_ID = "lesson-2"
LESSON_2_VERSION = "2.7-spoken-dialogue"

_COURSES = [
    ("认知行为三角", "认识情境、想法、情绪和行为，完成一次个人案例梳理。", "区分四要素 · 建立练习目标"),
    ("看见情境、想法和心情", "通过自然对话区分发生的事、脑中的想法和心情，完成一次三栏记录。", "LLM 自由带领 · 三栏记录"),
    ("识别歪曲思维", "认识常见的思维偏差，并在自己的记录中辨认它们。", "识别被歪曲的想法"),
    ("相反行为", "理解情绪推动的行为，并练习选择不同的回应。", "学习相反行为"),
    ("行为激活 / 行为暴露", "根据需要选择行为激活或行为暴露。", "两条学习路径 · 二选一"),
    ("修正我的思维", "用苏格拉底提问检查想法，并继续练习三栏表。", "苏格拉底提问 · 三栏表"),
    ("睡眠 / 放松训练", "根据需要选择睡眠训练或放松训练。", "两条学习路径 · 二选一"),
    ("预防复发", "回顾练习进展，制定可以继续使用的预防复发计划。", "回顾进展 · 制定计划"),
]

COURSE_CATALOG: list[dict[str, Any]] = [
    {
        "id": f"lesson-{number}",
        "number": number,
        "title": title,
        "summary": summary,
        "practice": practice,
        "available": number in {1, 2},
        "duration": "约 25 分钟" if number == 1 else ("约 15 分钟" if number == 2 else "待上线"),
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
    if lesson_id == LESSON_1_ID:
        return LESSON_1_VERSION
    if lesson_id == LESSON_2_ID:
        return LESSON_2_VERSION
    raise ValueError("课程不存在。")
