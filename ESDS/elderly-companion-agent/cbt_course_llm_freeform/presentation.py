"""Build page/API data from saved state, without advancing the conversation."""

from __future__ import annotations

import copy
import os
from typing import Any

from cbt_course_llm_freeform import (
    blueprint,
    boundaries,
    interaction,
    learning_check,
    lesson2_flow,
    practice_flow,
)
from cbt_course_llm_freeform.catalog import course_by_id, is_active_lesson
from cbt_course_llm_freeform.design import (
    FIELD_LABELS,
    STAGES,
    STAGE_LABELS,
    preview_examples,
    required_fields,
    task_step_id,
)
from cbt_course_llm_freeform.state import IMPLEMENTATION, can_reuse_case


def course_payload(state: dict[str, Any] | None) -> dict[str, Any]:
    if not state:
        return {}
    from cbt_course_llm_freeform import teacher_flow

    lesson_id = str(state.get("lesson_id") or "lesson-1")
    if not is_active_lesson(lesson_id):
        from cbt_course_llm_freeform.history import archived_course_payload

        return archived_course_payload(state)
    guided = state.get("implementation") == IMPLEMENTATION
    stage, completed = state.get("stage", "check_in"), bool(state.get("completed"))
    checked = learning_check.enabled(state)
    stages = learning_check.STAGES if checked else STAGES
    labels = {**STAGE_LABELS, **learning_check.LABELS}
    if blueprint.enabled(state):
        labels.update(
            check_in="课程介绍与心境检查",
            learn="选择困扰与情境",
            practice="逐步理解这件事",
            review="回看模型与核对",
            assessment="四要素辨认练习",
            learning_goal="整套课程目标",
        )
    if boundaries.fictional(state):
        labels.update(practice="用案例一起练习", review="核对案例练习")
    examples = preview_examples(state)
    if checked and not (
        os.getenv("CBT_PREVIEW_MODE") == "true" and os.getenv("CBT_COURSE_PROVIDER") == "preview"
    ):
        examples = {
            key: value
            for key, value in examples.items()
            if key not in {"assessment", "check_feedback"}
        }
    fields = (state.get("confirmed_record") or {}).get("fields") or state.get("draft_record", {})
    record = [
        {"field": key, "label": FIELD_LABELS[key], **fields[key]}
        for key in required_fields(state)
        if key in fields
    ]
    payload = {
        "lesson": course_by_id(lesson_id),
        "lesson_version": state.get("lesson_version"),
        "current_step": "completed" if completed else stage if guided else "freeform",
        "phase": (
            "历史课程（只读）"
            if not guided
            else (
                "课程已完成"
                if completed
                else (
                    "课程已安全暂停"
                    if state.get("safety_paused")
                    else (
                        "已暂停，可稍后继续"
                        if state.get("paused")
                        else labels.get(stage, "历史课程")
                    )
                )
            )
        ),
        "progress_percent": (
            100
            if completed
            else round(stages.index(stage) / len(stages) * 100) if guided and stage in stages else 0
        ),
        "stage_number": (
            len(stages) if completed else stages.index(stage) + 1 if stage in stages else 1
        ),
        "stages": [{"id": key, "label": labels[key]} for key in stages] if guided else [],
        "completed": completed,
        "paused": bool(state.get("paused")),
        "safety_paused": bool(state.get("safety_paused")),
        "revision": state.get("revision", 0),
        "guided": guided,
        "record": record,
        "record_confirmed": bool(state.get("confirmed_record")),
        "practice_plan": state.get("practice_plan", {}),
        "carryover": state.get("carryover", {}),
        "learning_evidence": state.get("learning_evidence", []),
        "reflection": state.get("reflection", {}),
        "domain_candidates": state.get("domain_candidates", []),
        "pattern_review": state.get("pattern_review"),
        "pattern_required": False,
        "pattern_choices": {},
        "path": state.get("path"),
        "path_label": None,
        "path_choices": [],
        "needs_path_choice": False,
        "record_kind": "学习记录",
        "can_reuse_case": can_reuse_case(state),
        "workflow": state.get("workflow", {}),
        "task_step_id": task_step_id(state) if guided else None,
        "preview_examples": examples,
        "learning_check": learning_check.payload(state) if checked else None,
        "stage_focus": practice_flow.stage_focus(state),
        "personal_practice": practice_flow.payload(state),
        "interaction_adaptation": copy.deepcopy(practice_flow.adaptation(state)),
        "natural_feedback_enabled": state.get("interaction_reflection_version")
        == interaction.VERSION,
        "practice_source": copy.deepcopy(boundaries.source(state)),
        "boundary_confirmation_pending": bool(state.get("privacy", {}).get("pending")),
        "practice_control_labels": practice_flow.control_labels(state),
        "show_practice_controls": state.get("interaction_response_version")
        != interaction.RESPONSE_VERSION,
        "personal_practice_scope": (
            practice_flow.scope(state) if practice_flow.enabled(state) else None
        ),
        "learning_goal": state.get("learning_goal")
        or (
            {"status": "draft", **state["learning_goal_draft"]}
            if state.get("learning_goal_draft")
            else None
        ),
        "application_status": "尚未收集生活中运用的反馈",
        "formulation": {},
        "quiz_results": {},
        "blueprint": blueprint.payload(state),
        "teacher_flow": teacher_flow.payload(state),
    }

    if lesson2_flow.enabled(state):
        second = lesson2_flow.payload(state)
        step = second["step"]
        payload.update(
            lesson2=second,
            current_step="completed" if completed else step,
            stages=second["stages"],
            stage_number=len(lesson2_flow.STEPS) if completed else second["step_number"],
            progress_percent=(
                100
                if completed
                else round((second["step_number"] - 1) / len(lesson2_flow.STEPS) * 100)
            ),
            stage_focus=(
                None
                if completed
                else {
                    "task": second["label"],
                    "purpose": lesson2_flow.PURPOSES[step],
                    "exit": lesson2_flow.question(state),
                }
            ),
            show_practice_controls=False,
            personal_practice=None,
            phase=(
                payload["phase"]
                if completed or state.get("paused") or state.get("safety_paused")
                else second["label"]
            ),
        )
    if (
        teacher_flow.enabled(state)
        and stage == "check_in"
        and state.get("lesson2_flow", {}).get("step", "check_in") == "check_in"
        and not completed
    ):
        overview = payload["teacher_flow"]["overview_pending"]
        payload["phase"] = "课程介绍与八课总览" if overview else "心境检查"
        payload["stage_focus"] = {
            "task": payload["phase"],
            "purpose": (
                "先了解课程安排，再记录您对上周整体状态的评价。"
                if overview
                else "了解您对上周状态的自评，与事件中的情绪评分分开。"
            ),
            "exit": "看完八课总览后，开始心境检查。" if overview else teacher_flow.MOOD_QUESTION,
        }
    return payload
