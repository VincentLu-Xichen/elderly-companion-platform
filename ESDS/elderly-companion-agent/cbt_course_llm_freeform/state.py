"""Initial course state and rules for reusing an authorized case."""

from __future__ import annotations

import uuid
from typing import Any

from cbt_course_llm_freeform import (
    boundaries,
    blueprint,
    dialogue,
    interaction,
    learning_check,
    lesson2_flow,
    navigation,
    practice_flow,
)
from cbt_course_llm_freeform.catalog import lesson_version, require_available_course
from cbt_course_llm_freeform.design import required_fields
from cbt_course_llm_freeform.feedback import new_workflow

IMPLEMENTATION = "guided_cbt_v3"


def new_course_state(lesson_id: str, *, reflection_policy: str | None = None) -> dict[str, Any]:
    require_available_course(lesson_id)
    from cbt_course_llm_freeform import teacher_flow

    return {
        "implementation": IMPLEMENTATION,
        "lesson_id": lesson_id,
        "lesson_version": lesson_version(lesson_id),
        "stage": "check_in",
        "revision": 0,
        "turn_count": 0,
        "completed": False,
        "paused": False,
        "case_id": str(uuid.uuid4()),
        "draft_record": {},
        "confirmed_record": None,
        "learning_evidence": [],
        "path": None,
        "domain_candidates": [],
        "pattern_review": None,
        "artifact": None,
        "practice_plan": {"status": "undecided", "text": ""},
        "carryover": {"status": "unavailable"},
        "reflection": {"status": "not_started"},
        "workflow": new_workflow(reflection_policy),
        "interaction_reflection_version": interaction.VERSION,
        "interaction_memories": [],
        **({"learning_check": learning_check.new_check()} if lesson_id == "lesson-1" else {}),
        **({"practice_flow": practice_flow.new_flow()} if lesson_id == "lesson-1" else {}),
        **({"privacy": boundaries.new_flow()} if lesson_id in {"lesson-1", "lesson-2"} else {}),
        **({"lesson2_flow": lesson2_flow.new_flow()} if lesson_id == "lesson-2" else {}),
        **({"navigation_version": navigation.VERSION} if lesson_id == "lesson-1" else {}),
        **({"dialogue_policy": dialogue.VERSION} if lesson_id == "lesson-1" else {}),
        **(
            {"interaction_response_version": interaction.RESPONSE_VERSION}
            if lesson_id in {"lesson-1", "lesson-2"}
            else {}
        ),
        **({"blueprint": blueprint.new_flow()} if lesson_id == "lesson-1" else {}),
        **(
            {"teacher_flow": teacher_flow.new_flow(lesson_id)}
            if lesson_id in {"lesson-1", "lesson-2"}
            else {}
        ),
    }


def reusable_fields(state: dict) -> list[str]:
    previous = state.get("carryover", {}).get("summary", {}).get("record", {})
    return [
        key
        for key in required_fields(state)
        if key in {"situation", "thought", "emotion", "behavior"} and key in previous
    ]


def can_reuse_case(state: dict) -> bool:
    if lesson2_flow.enabled(state):
        return state["lesson2_flow"]["step"] == "personal" and lesson2_flow.runtime_can_reuse(state)
    memory = state.get("carryover", {})
    return (
        not boundaries.blocked(state)
        and not boundaries.fictional(state)
        and state.get("stage") == "practice"
        and not state.get("draft_record")
        and memory.get("status") == "accepted"
        and bool(reusable_fields(state))
    )
