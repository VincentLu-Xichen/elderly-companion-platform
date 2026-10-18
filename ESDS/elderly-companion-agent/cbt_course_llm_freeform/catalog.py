from __future__ import annotations

from typing import Any


LESSON_1_ID = "lesson-1"
LESSON_1_VERSION = "7.1-feedback-review"
LESSON_2_ID = "lesson-2"
LESSON_2_VERSION = "5.1-interaction-memory"
LESSON_3_ID = "lesson-3"
LESSON_3_VERSION = "2.1-interaction-memory"
LESSON_VERSIONS = {"lesson-1": LESSON_1_VERSION, "lesson-2": LESSON_2_VERSION, "lesson-3": LESSON_3_VERSION,
                   **{f"lesson-{number}": "1.1-interaction-memory" for number in range(4, 9)}}

_COURSES = [
    ("认知行为三角", "围绕一件困扰学习四要素，回看认知行为模型，再辨认练习并制定课程目标。", "同例教学 · 两项评分 · 模型回顾与课程目标"),
    ("看见情境、想法和心情", "通过自然对话区分发生的事、脑中的想法和心情，完成一次三栏记录。", "生活例子 · 本人确认的三栏记录"),
    ("看见想法中的习惯", "区分已知信息与推断，尝试辨认思维习惯；可以保留不确定。", "辨认线索 · 本人核对解释"),
    ("相反行为", "看见情绪推动的做法，判断是否有帮助，再考虑可行的替代回应。", "检查做法 · 尊重边界的小步行动"),
    ("行为激活 / 行为暴露", "选择活动安排或逐步面对日常回避，整理本人愿意考虑的小步计划。", "本人选路径 · 计划与实际执行分开"),
    ("修正我的思维", "检查支持与不支持的信息，形成更平衡、允许不确定的说法。", "核对依据 · 本人形成新说法"),
    ("睡眠 / 放松训练", "选择梳理睡眠习惯或舒适放松，为自己安排一个可调整的小步骤。", "本人选路径 · 可以停下或调整"),
    ("预防复发", "回顾可用技能，整理再遇困难时的信号、应对步骤和支持安排。", "多课回顾 · 留下一份应对计划"),
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
