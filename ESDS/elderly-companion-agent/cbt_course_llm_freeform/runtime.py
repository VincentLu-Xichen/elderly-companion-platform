from __future__ import annotations

import copy
import re
from typing import Any

from cbt_course_llm_freeform.agent import FreeformCourseAgent
from cbt_course_llm_freeform.catalog import LESSON_1_ID, LESSON_2_ID, course_by_id, lesson_version, require_available_course
from cbt_course_llm_freeform.lesson_1 import COMPLETION_MARKER, STATIC_ATTACHMENTS
from cbt_course_llm_freeform.lesson_2 import HARD_SAFETY_SIGNALS, SAFETY_MESSAGE
from cbt_course_llm_freeform.prompt import prompt_for_lesson
from cbt_course_llm_freeform.schemas import TurnResult


ATTACHMENT_PATTERN = re.compile(r"\[\[CBT_ATTACHMENT:([^\]\r\n]+)\]\]")


def new_course_state(lesson_id: str) -> dict[str, Any]:
    require_available_course(lesson_id)
    return {
        "implementation": "cbt_course_llm_freeform",
        "lesson_id": lesson_id,
        "lesson_version": lesson_version(lesson_id),
        "turn_count": 0,
        "completed": False,
    }


def course_payload(state: dict[str, Any] | None) -> dict[str, Any]:
    if not state:
        return {}
    completed = bool(state.get("completed"))
    lesson_id = str(state.get("lesson_id") or LESSON_1_ID)
    return {
        "lesson": course_by_id(lesson_id) or course_by_id(LESSON_1_ID),
        "lesson_version": state.get("lesson_version"),
        "current_step": "completed" if completed else "freeform",
        "phase": "课程已完成" if completed else "LLM 自由引导",
        "progress_percent": 100 if completed else 0,
        "completed": completed,
        "formulation": {},
        "quiz_results": {},
    }


def parse_control_markers(raw_reply: str, lesson_id: str = LESSON_1_ID) -> tuple[str, dict[str, Any], bool, str | None]:
    completed = COMPLETION_MARKER in raw_reply
    selected_key = None
    for match in ATTACHMENT_PATTERN.finditer(raw_reply):
        candidate = match.group(1).strip()
        if lesson_id == LESSON_1_ID and selected_key is None and candidate in STATIC_ATTACHMENTS and candidate != "course_overview":
            selected_key = candidate
    cleaned = raw_reply.replace(COMPLETION_MARKER, "")
    cleaned = ATTACHMENT_PATTERN.sub("", cleaned).strip()
    if not cleaned:
        raise RuntimeError("自由课程模型只返回了控制标记，没有可展示的回复。")
    attachment = dict(STATIC_ATTACHMENTS[selected_key]) if selected_key else {}
    return cleaned, attachment, completed, selected_key


class FreeformCourseRuntime:
    def __init__(self, *, agent: FreeformCourseAgent | None = None):
        self.agent = agent

    def process(self, state: dict[str, Any], history: list[dict[str, str]]) -> TurnResult:
        next_state = copy.deepcopy(state)
        if next_state.get("implementation") != "cbt_course_llm_freeform":
            raise ValueError("该课程状态不属于自由 LLM 实现。")
        if next_state.get("completed"):
            raise ValueError("本课已经完成，仅支持查看。")
        lesson_id = str(next_state.get("lesson_id") or "")
        require_available_course(lesson_id)
        latest_learner_text = next(
            (str(item.get("content") or "") for item in reversed(history) if item.get("role") == "learner"),
            "",
        )
        if lesson_id == LESSON_2_ID and any(signal in latest_learner_text for signal in HARD_SAFETY_SIGNALS):
            next_state["safety_paused"] = True
            return TurnResult(
                reply=SAFETY_MESSAGE,
                state=next_state,
                trace={
                    "implementation": "cbt_course_llm_freeform",
                    "lesson_id": lesson_id,
                    "lesson_version": lesson_version(lesson_id),
                    "turn_count": int(next_state.get("turn_count") or 0),
                    "completed": False,
                    "model_called": False,
                },
                safety_event="local_self_harm",
            )
        if next_state.get("safety_paused"):
            raise ValueError("本课已暂停，请先寻求现实帮助。")
        if self.agent is None:
            self.agent = FreeformCourseAgent(
                system_prompt=prompt_for_lesson(lesson_id),
                max_completion_tokens=600 if lesson_id == LESSON_2_ID else 1200,
            )
        result = self.agent.reply(history)
        reply, attachment, completed, attachment_key = parse_control_markers(result.reply, lesson_id)
        next_state["turn_count"] = int(next_state.get("turn_count") or 0) + 1
        next_state["completed"] = completed
        return TurnResult(
            reply=reply,
            state=next_state,
            trace={
                "implementation": "cbt_course_llm_freeform",
                "lesson_id": lesson_id,
                "lesson_version": lesson_version(lesson_id),
                "turn_count": next_state["turn_count"],
                "completed": completed,
                "attachment_key": attachment_key,
            },
            attachment=attachment,
            completion=result.completion,
        )
