"""Pure trigger rules. Importance is a decision signal, not elapsed time."""

from __future__ import annotations

import os


POLICIES = ("none", "per_turn", "per_task_step", "event_driven")
POLICY_VERSION = "feedback-events-v1"
POLICY_LABELS = {
    "none": "不使用任务反思（互动反馈仍判断）",
    "per_turn": "每轮任务反思",
    "per_task_step": "子任务结束时反思",
    "event_driven": "按任务反馈事件反思（试用规则）",
}
STRATEGY_INSTRUCTIONS = {
    "continue_current": "沿当前目标继续，不重复索取仍有效的记录。",
    "clarify_missing_field": "只问当前缺少的一项信息，回应已有回答。",
    "rephrase_plainly": "先用生活中的说法重新解释，再只问一个具体问题，减少术语。",
    "ask_concrete_fact": "询问一个具体的依据或已知信息，允许暂时不确定。",
    "acknowledge_correction": "先承认本人的纠正，按新说法核对，不复活旧推测。",
    "summarize_for_confirmation": "简短整理当前记录，邀请本人核对，不代替确认。",
}


def answer_needs_help(text: str) -> bool:
    """Uncertainty about someone else's thoughts is a valid answer, not confusion."""
    return text.strip("。！! ") in {"不知道", "我不知道", "不知道怎么回答"} or any(
        word in text for word in ("没听懂", "不明白", "不懂这个", "不想回答")
    )


def new_workflow(policy: str | None = None) -> dict:
    selected = policy if policy is not None else os.getenv("CBT_REFLECTION_POLICY", "none")
    if selected not in POLICIES:
        raise ValueError("未知反思策略，请检查 CBT_REFLECTION_POLICY。")
    return {
        "policy": selected,
        "policy_version": POLICY_VERSION,
        "ordinary_turns": 0,
        "no_progress_count": 0,
        "last_trigger": {"triggered": False, "reason_codes": ["not_evaluated"]},
        "reflections": [],
        "active_reflection": None,
        "last_reflection_message_id": None,
    }


def decide_trigger(
    workflow: dict,
    *,
    task_before: str,
    task_after: str,
    signals: list[dict],
    changed_fields: list[str],
    stage_before: str,
    answer_attempt: bool = True,
) -> dict:
    """Inputs are validated by runtime; this function never reads a clock or calls a model."""
    policy = workflow["policy"]
    workflow["ordinary_turns"] += 1
    no_progress = stage_before == "practice" and task_before == task_after and not changed_fields
    if answer_attempt:
        workflow["no_progress_count"] = workflow["no_progress_count"] + 1 if no_progress else 0
    elif changed_fields or task_before != task_after:
        workflow["no_progress_count"] = 0
    events = []
    for signal in signals:
        kind = signal["kind"]
        if kind in {"confusion", "correction"}:
            events.append(kind)
        elif kind == "potential_conflict" and signal.get("comparable_context"):
            events.append("comparable_conflict")
        elif kind == "new_evidence" and signal.get("replaces_existing"):
            events.append("changed_existing_evidence")
    if answer_attempt and workflow["no_progress_count"] >= 2:
        events.append("repeated_no_progress")
    reasons = []
    if policy == "per_turn":
        reasons = ["every_ordinary_turn"]
    elif policy == "per_task_step" and task_before != task_after:
        reasons = ["task_step_finished"]
    elif policy == "event_driven":
        reasons = list(dict.fromkeys(events))
    return {
        "policy": policy,
        "policy_version": workflow["policy_version"],
        "triggered": bool(reasons),
        "reason_codes": reasons or ["policy_none" if policy == "none" else "no_selected_event"],
        "observed_events": list(dict.fromkeys(events)),
        "task_before": task_before,
        "task_after": task_after,
        "no_progress_count": workflow["no_progress_count"],
        "rule_threshold": 2,
    }


def allowed_strategies(state: dict) -> list[str]:
    from cbt_course_llm_freeform.practice_flow import missing

    strategies = [
        key
        for key in STRATEGY_INSTRUCTIONS
        if key not in {"clarify_missing_field", "summarize_for_confirmation"}
    ]
    if state["stage"] == "practice" and missing(state):
        strategies.append("clarify_missing_field")
    if state["stage"] == "review":
        strategies.append("summarize_for_confirmation")
    return strategies


def active_guidance(state: dict) -> dict | None:
    """Old reflection is context, never a fact patch or perpetual instruction."""
    note = state.get("workflow", {}).get("active_reflection")
    if (
        not note
        or note.get("stage") != state["stage"]
        or note.get("case_id") != state.get("case_id")
        or note.get("path") != state.get("path")
    ):
        return None
    if state["workflow"]["ordinary_turns"] - note.get("ordinary_turn", 0) > 3:
        return None
    strategy, focus = note.get("strategy"), note.get("focus_field")
    if strategy not in allowed_strategies(state):
        return None
    from cbt_course_llm_freeform.practice_flow import missing

    if strategy == "clarify_missing_field" and focus not in missing(state):
        return None
    return {
        "strategy": strategy,
        "focus_field": focus,
        "instruction": STRATEGY_INSTRUCTIONS[strategy],
        "reflection_id": note["id"],
    }
