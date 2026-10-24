"""Present saved artifacts without importing or executing retired lessons."""

from __future__ import annotations

import copy

# Labels are display metadata, not runnable teaching content.
_TITLES = {
    "lesson-3": "看见想法中的习惯",
    "lesson-4": "相反行为",
    "lesson-5": "行为激活 / 行为暴露",
    "lesson-6": "修正我的思维",
    "lesson-7": "睡眠 / 放松训练",
    "lesson-8": "预防复发",
}


def archived_course_payload(state: dict) -> dict:
    lesson_id = str(state.get("lesson_id", ""))
    record = state.get("confirmed_record") or {}
    fields = record.get("fields") or state.get("draft_record") or {}
    # Keep saved field identities and content; do not infer a new lesson schema.
    saved_labels = state.get("record_labels", {})
    return {
        "lesson": {
            "id": lesson_id,
            "number": (
                int(lesson_id.rsplit("-", 1)[-1]) if lesson_id.rsplit("-", 1)[-1].isdigit() else 0
            ),
            "title": _TITLES.get(lesson_id, "历史课程"),
            "available": False,
        },
        "lesson_version": state.get("lesson_version"),
        "current_step": "completed" if state.get("completed") else state.get("stage", "freeform"),
        "phase": "历史课程（只读）",
        "guided": False,
        "archived": True,
        "completed": bool(state.get("completed")),
        "paused": bool(state.get("paused")),
        "safety_paused": bool(state.get("safety_paused")),
        "revision": state.get("revision", 0),
        "progress_percent": 100 if state.get("completed") else 0,
        "stage_number": 0,
        "stages": [],
        "record": [
            {"field": key, "label": saved_labels.get(key, key), **copy.deepcopy(item)}
            for key, item in fields.items()
        ],
        "record_confirmed": bool(record),
        "record_kind": "历史学习记录",
        "practice_plan": copy.deepcopy(state.get("practice_plan", {})),
        "learning_evidence": copy.deepcopy(state.get("learning_evidence", [])),
        "reflection": copy.deepcopy(state.get("reflection", {})),
        "workflow": copy.deepcopy(state.get("workflow", {})),
        "practice_source": copy.deepcopy(state.get("practice_source", {"kind": "personal"})),
        "carryover": copy.deepcopy(state.get("carryover", {})),
        "domain_candidates": copy.deepcopy(state.get("domain_candidates", [])),
        "pattern_review": copy.deepcopy(state.get("pattern_review")),
        "pattern_required": False,
        "pattern_choices": {},
        "path": state.get("path"),
        "path_label": None,
        "path_choices": [],
        "needs_path_choice": False,
        "can_reuse_case": False,
        "preview_examples": {},
        "task_step_id": None,
        "show_practice_controls": False,
        "natural_feedback_enabled": False,
        "stage_focus": None,
        "personal_practice": None,
        "blueprint": None,
        "teacher_flow": None,
    }
