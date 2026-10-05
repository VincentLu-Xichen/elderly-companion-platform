from __future__ import annotations

from typing import Any


LESSON_1_ID = "lesson-1"
LESSON_1_VERSION = "1.0-xmind-2023-10-18"


COURSE_CATALOG: list[dict[str, Any]] = [
    {
        "id": LESSON_1_ID,
        "number": 1,
        "title": "认知行为三角",
        "summary": "认识情境、想法、情绪和行为，完成一次个人案例梳理。",
        "practice": "区分四要素 · 建立练习目标",
        "available": True,
        "duration": "约 25 分钟",
    },
    {
        "id": "lesson-2",
        "number": 2,
        "title": "捕捉我的思维",
        "summary": "识别自动思维，学习记录三栏表。",
        "practice": "识别自动思维 · 三栏表",
        "available": False,
        "duration": "待上线",
    },
    {
        "id": "lesson-3",
        "number": 3,
        "title": "识别歪曲思维",
        "summary": "认识常见的思维偏差，并在自己的记录中辨认它们。",
        "practice": "识别被歪曲的想法",
        "available": False,
        "duration": "待上线",
    },
    {
        "id": "lesson-4",
        "number": 4,
        "title": "相反行为",
        "summary": "理解情绪推动的行为，并练习选择不同的回应。",
        "practice": "学习相反行为",
        "available": False,
        "duration": "待上线",
    },
    {
        "id": "lesson-5",
        "number": 5,
        "title": "行为激活 / 行为暴露",
        "summary": "根据需要选择行为激活或行为暴露。",
        "practice": "两条学习路径 · 二选一",
        "available": False,
        "duration": "待上线",
    },
    {
        "id": "lesson-6",
        "number": 6,
        "title": "修正我的思维",
        "summary": "用苏格拉底提问检查想法，并继续练习三栏表。",
        "practice": "苏格拉底提问 · 三栏表",
        "available": False,
        "duration": "待上线",
    },
    {
        "id": "lesson-7",
        "number": 7,
        "title": "睡眠 / 放松训练",
        "summary": "根据需要选择睡眠训练或放松训练。",
        "practice": "两条学习路径 · 二选一",
        "available": False,
        "duration": "待上线",
    },
    {
        "id": "lesson-8",
        "number": 8,
        "title": "预防复发",
        "summary": "回顾练习进展，制定可以继续使用的预防复发计划。",
        "practice": "回顾进展 · 制定计划",
        "available": False,
        "duration": "待上线",
    },
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
