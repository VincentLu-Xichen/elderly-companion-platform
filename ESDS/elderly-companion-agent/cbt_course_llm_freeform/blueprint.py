"""Lesson-one content, sourced ratings and course goals; no model-owned consent."""

from __future__ import annotations

import copy
import re

VERSION = "lesson-1-blueprint/1"
FIELDS = ("situation", "thought", "thought_belief", "emotion", "emotion_intensity", "behavior")
RATINGS = {"thought_belief": "thought", "emotion_intensity": "emotion"}
LABELS = {
    "thought_belief": "对想法的相信程度",
    "emotion_intensity": "情绪强度",
    "relationship_note": "回看这件事后的想法",
}
CONCEPTS = {
    "situation": "情境是特定时间、地点发生的具体事情。例如，给朋友发了消息，暂时没有收到回复。",
    "thought": "想法，也叫认知或自动思维，是当时对事情的解释、判断或预测。例如，‘他是不是不愿理我’；它与‘还没有回复’这个事实不同。",
    "emotion": "情绪是当时的主观感受，例如失落、紧张、生气或害羞。可以参考这些词，也可以用自己的说法；‘我觉得他不理我’仍是在表达想法。",
    "behavior": "行为是当时实际做了什么或没有做什么。例如没有再联系、走开或继续交谈；想做和计划以后做，不等于已经做了。",
}
QUESTIONS = {
    "situation": "您选的这件事，当时具体发生了什么？",
    "thought": "在这件事里，您当时脑中出现了哪句话或什么画面？",
    "thought_belief": "对于刚才这条想法，您当时有多相信？0分是不相信，10分是非常相信，也可以暂不评分。",
    "emotion": "想到这里时，您当时有什么情绪或感受？",
    "emotion_intensity": "刚才这份情绪当时有多强烈？0分是不强烈，10分是非常强烈，也可以暂不评分。",
    "behavior": "带着当时的感受，您实际做了什么，或者没有做什么？",
}
GOAL_EXAMPLES = "原课程提供的参考方向有：觉察情绪、用认知行为模型分析事情、识别思维习惯、每周一次三栏记录、每周一次五栏记录并检查想法、每周一次相反行为、每月一次渐进面对回避、学习放松并按舒适程度练习、一个月内用两周记录睡眠。它们不是必须全部完成或保证改善；是否适合、频率和具体做法由您选择，相关方法会在后课学习，不要求现在执行。"


def new_flow():
    return {
        "version": VERSION,
        "ratings": {},
        "taught": [],
        "relationship": None,
        "case_options": [],
        "goal_direction": None,
        "goal_step": "direction",
    }


def enabled(state):
    return (
        state.get("lesson_id") == "lesson-1"
        and state.get("blueprint", {}).get("version") == VERSION
    )


def missing(state):
    flow = state["blueprint"]
    deferred = state["practice_flow"]["deferred"]
    return [
        key
        for key in FIELDS
        if key not in deferred
        and (key not in flow["ratings"] if key in RATINGS else key not in state["draft_record"])
    ]


def invalidate(state, changed):
    flow = state["blueprint"]
    for rating, base in RATINGS.items():
        if base in changed or "situation" in changed:
            flow["ratings"].pop(rating, None)
            state["practice_flow"]["deferred"].pop(rating, None)
    if changed:
        flow["relationship"] = None
        state["confirmed_record"] = None


def reset_case(state):
    old = state["blueprint"]
    state["blueprint"] = new_flow()
    state["blueprint"]["goal_direction"] = old.get("goal_direction")


def settle_fictional_ratings(state, latest):
    from cbt_course_llm_freeform import boundaries

    if not boundaries.fictional(state):
        return
    # Existing alternative materials contain no numerical ratings. Never ask the
    # learner to invent them or mislabel the learner's own rating as a character's.
    for key in RATINGS:
        state["practice_flow"]["deferred"][key] = {
            "status": "not_observed",
            "source_message_ids": [latest["id"]],
            "reason": "虚构材料未提供评分，不代角色猜测。",
        }


def parse_rating(quote):
    text = quote.strip()
    match = re.fullmatch(
        r"(?:(?:(?:我)?(?:对)?(?:这个|这条|该)?(?:想法|情绪)的)?(?:相信程度|相信|确信程度|情绪强度|强度|强烈程度)[：:\s]*(?:是|为)?\s*)?([0-9]+(?:\.[0-9]+)?|零|一|二|两|三|四|五|六|七|八|九|十)\s*(?:分|/10)?[。.!！]?",
        text,
    )
    if not match:
        return None
    raw = match[1]
    digits = {c: i for i, c in enumerate("零一二三四五六七八九十")}
    number = digits.get(raw, 2 if raw == "两" else None)
    if number is None:
        number = float(raw)
    if not 0 <= number <= 10:
        return None
    return int(number) if number == int(number) else number


def accept_rating(state, evidence, latest, focus):
    from cbt_course_llm_freeform import boundaries

    key, quote = evidence.field, evidence.value
    number = parse_rating(quote)
    # A bare number is meaningful only for the question actually asked.
    labelled = (
        bool(re.search("相信|确信", quote))
        if key == "thought_belief"
        else bool(re.search("情绪|强度|强烈", quote))
    )
    if number is None or (key != focus and not labelled):
        return False
    if boundaries.fictional(state):
        return False
    if RATINGS[key] not in state["draft_record"]:
        return False
    state["blueprint"]["ratings"][key] = {
        "value": number,
        "quote": quote,
        "source_message_id": latest["id"],
        "source_kind": "personal",
        "case_id": state["case_id"],
        "about": copy.deepcopy(state["draft_record"][RATINGS[key]]),
    }
    return True


def review_text(state, *, invite=True):
    from cbt_course_llm_freeform import boundaries
    from cbt_course_llm_freeform.case_review import fingerprint

    recap = state["blueprint"].get("case_review", {})
    anchor = state["draft_record"].get("situation", {}).get("value")
    lines = [
        (
            recap["summary"]
            if recap.get("status") == "ready" and recap.get("fingerprint") == fingerprint(state)
            else (
                "我们仍围绕“" + anchor + "”核对右侧记录。"
                if anchor
                else "我们一起回看右侧已整理的记录；您可以核对或修改。"
            )
        )
    ]
    if boundaries.fictional(state):
        lines.insert(0, "这里回看的是虚构人物的经历。")
    if (
        invite
        and state["blueprint"].get("review_invited_for") != fingerprint(state)
        and not state["practice_flow"].get("stop_probing")
        and state["blueprint"].get("relationship") is None
    ):
        lines.append(
            "这样回看，您对这件事有没有新的看法或想补充的感受？没有也没关系，也可以直接核对并确认记录。"
        )
    else:
        lines.append("请核对记录是否准确；可以修改，准确后再确认。")
    return "\n".join(lines)


def after_turn(state, focus, accepted, latest):
    flow = state["practice_flow"]
    for key in accepted:
        flow["deferred"].pop(key, None)
        flow["unanswered"].pop(key, None)
    if focus and focus not in accepted:
        attempts = flow["unanswered"].setdefault(focus, [])
        attempts.append(latest["id"])
        if len(attempts) >= 2:
            flow["deferred"][focus] = {
                "status": "not_observed",
                "source_message_ids": attempts[-2:],
            }
    settle_fictional_ratings(state, latest)
    if not missing(state):
        state["stage"] = "review"


def instruction(state):
    from cbt_course_llm_freeform import boundaries
    from cbt_course_llm_freeform import teacher_flow

    if state["stage"] == "learn":
        explanation = (
            teacher_flow.help_text("situation")
            if teacher_flow.enabled(state) and state["practice_flow"]["unanswered"].get("situation")
            else ""
        )
        return (
            explanation
            + "我们先选一件最近愿意分析的困扰；如果有几件，您想先看哪一件？也可以使用虚构案例，不必谈私事。"
        )
    if state["stage"] == "review":
        return review_text(state)
    focus = next(iter(missing(state)), None)
    if focus is None:
        return review_text(state)
    concept = CONCEPTS.get(focus, "")
    if (
        teacher_flow.enabled(state)
        and focus in teacher_flow.CARDS
        and state["practice_flow"]["unanswered"].get(focus)
    ):
        concept = "一时想不到也没关系，我们先看定义和示例。" + teacher_flow.help_text(focus)
    if boundaries.fictional(state):
        return (
            concept
            + "请从当前虚构材料中辨认“"
            + {"situation": "情境", "thought": "想法", "emotion": "情绪", "behavior": "行为"}.get(
                focus, focus
            )
            + "”。"
        )
    anchor = ""
    if focus in RATINGS and RATINGS[focus] in state["draft_record"]:
        anchor = (
            "刚才记录的"
            + ("想法" if focus == "thought_belief" else "情绪")
            + "是：“"
            + state["draft_record"][RATINGS[focus]]["value"]
            + "”。"
        )
    return concept + anchor + QUESTIONS[focus]


def payload(state):
    if not enabled(state):
        return None
    from cbt_course_llm_freeform import boundaries

    flow = state["blueprint"]
    return {
        "version": VERSION,
        "source_kind": boundaries.source(state)["kind"],
        "case_id": state["case_id"],
        "ratings": copy.deepcopy(flow["ratings"]),
        "relationship": copy.deepcopy(flow["relationship"]),
        "current_field": next(iter(missing(state)), None) if state["stage"] == "practice" else None,
        "concepts": [CONCEPTS[key] for key in CONCEPTS],
        "materials": [
            {"src": "/cbt-course-assets/lesson_1/thought-example.svg", "alt": "想法的概念与示例"},
            {"src": "/cbt-course-assets/lesson_1/emotion-vocabulary.svg", "alt": "情绪词汇参考表"},
        ],
        "case_options": copy.deepcopy(flow.get("case_options", [])),
        "relations": "情境 → 对情境的解读；想法 ↔ 情绪 ↔ 行为，想法 ↔ 行为。具体联系仍需本人核对。",
    }


def select_case(state, latest):
    options = state["blueprint"].get("case_options", [])
    compact = re.sub(r"[\s，,。.!！]", "", latest["content"])
    match = re.fullmatch(r"(?:我选|选|就|先看|先说)?第?([1-5一二三四五])(?:件|个)?", compact)
    if not options or not match:
        return False
    raw = match[1]
    index = int(raw) - 1 if raw.isdigit() else "一二三四五".index(raw)
    if index >= len(options):
        return False
    item = options[index]
    state["draft_record"]["situation"] = {
        "value": item["value"],
        "source_message_id": item["source_message_id"],
        "selection_message_id": latest["id"],
        "case_id": state["case_id"],
        "source_kind": "personal",
    }
    state["stage"] = "practice"
    state["blueprint"]["case_options"] = []
    from cbt_course_llm_freeform import teacher_flow

    teacher_flow.card(state, "situation", source_message_id=item["source_message_id"])
    return True


def goal_answer(state, latest, items, level="concrete"):
    if not items:
        return "您希望整套课程帮助生活中哪些方面？" + GOAL_EXAMPLES + "暂时没有目标也可以继续。"
    if len(set(items)) != len(items) or any(
        not item.strip() or len(item) > 500 or item not in latest["content"] for item in items
    ):
        raise ValueError("Course goals need distinct faithful current quotes")
    if len(items) > 5:
        state.pop("learning_goal", None)
        state.pop("learning_goal_draft", None)
        return "您提到的方向超过五项。可以先合并成一至五项最想关注的目标，其他内容仍保留在对话中。"
    if level == "direction":
        state["blueprint"]["goal_direction"] = {
            "items": list(items),
            "source_message_id": latest["id"],
        }
        state["blueprint"]["goal_step"] = "concrete"
        # Editing even the direction withdraws an earlier draft/confirmation.
        state.pop("learning_goal", None)
        state.pop("learning_goal_draft", None)
        return "这些是您希望改善的方向。课程结束时，您希望具体能做到什么？" + GOAL_EXAMPLES
    state.pop("learning_goal", None)
    state["learning_goal_draft"] = {
        "value": "；".join(items),
        "items": [{"value": item, "source_message_id": latest["id"]} for item in items],
        "source_message_id": latest["id"],
        "direction": copy.deepcopy(state["blueprint"].get("goal_direction")),
    }
    return (
        "先整理为以下整套课程目标，请核对或直接修改：\n"
        + "\n".join(f"{i + 1}. {item}" for i, item in enumerate(items))
        + "\n准确的话再确认；也可以暂不设置。"
    )


def revise_goals(state, latest, updates, base):
    """Retain unchanged items and their original evidence on explicit indexed edits."""
    if not base or len({item.index for item in updates}) != len(updates):
        raise ValueError("No unambiguous goals to revise")
    revised = copy.deepcopy(base)
    for item in updates:
        numeral = "一二三四五"[item.index - 1]
        if (
            item.index > len(base)
            or item.value not in latest["content"]
            or not re.search(rf"第(?:{item.index}|{numeral})[项个条]", latest["content"])
        ):
            raise ValueError("Goal edit lacks current index or faithful quote")
        revised[item.index - 1] = {"value": item.value, "source_message_id": latest["id"]}
    if len({item["value"] for item in revised}) != len(revised):
        raise ValueError("Goal edit duplicates another goal")
    state.pop("learning_goal", None)
    state["learning_goal_draft"] = {
        "items": revised,
        "value": "；".join(item["value"] for item in revised),
        "source_message_id": latest["id"],
        "direction": copy.deepcopy(state["blueprint"].get("goal_direction")),
    }
    return "已按您说的条目修改，其余目标保留。请重新核对确认：\n" + "\n".join(
        f"{i+1}. {item['value']}" for i, item in enumerate(revised)
    )
