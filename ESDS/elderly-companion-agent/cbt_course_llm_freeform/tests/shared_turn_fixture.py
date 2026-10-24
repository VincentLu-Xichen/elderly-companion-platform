"""Isolate the shared turn protocol from either lesson's teaching controller.

Used only for infrastructure tests (stream projection, reflection, atomic retry).
Full lesson tests separately exercise the actual first/second lesson controllers.
"""
from cbt_course_llm_freeform.runtime import new_course_state


def shared_state(*, reflection_policy=None):
    state = new_course_state("lesson-1", reflection_policy=reflection_policy)
    for key in ("teacher_flow", "blueprint", "learning_check", "practice_flow", "navigation_version", "dialogue_policy"):
        state.pop(key, None)
    return state
