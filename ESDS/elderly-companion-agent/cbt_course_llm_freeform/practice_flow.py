"""Lesson-one teaching boundaries. Missing information never becomes learner facts."""

from __future__ import annotations

import re

from cbt_course_llm_freeform.design import FIELD_LABELS, QUESTIONS, required_fields

VERSION = "lesson-1-practice-v1"
MAX_UNANSWERED = 2  # Initial answer plus one clarification; not a learner score.
CONTROL_LABELS = {
    "defer_practice_field": "这一项暂时想不起",
    "decline_practice_field": "这一项先不谈",
}
FEEDBACK_CONTROLS = {
    "request_less_probing": "我想少解释一点",
    "show_brief_explanation": "直接看解释",
    "continue_practice_dialogue": "继续聊",
}
CONTROL_LABELS.update(FEEDBACK_CONTROLS)
BRIEF_EXPLANATIONS = {
    "situation": "事情是当时实际发生、您看到或听到的内容，不需要先解释原因。",
    "thought": "想法是当时脑中出现的解释、判断或预测。想不起清楚的念头也可以，不用补一个。",
    "emotion": "心情是当时的感受，可以用自己的日常说法表达，不必找标准词。",
    "behavior": "做法是后来实际做了什么，或没有做什么；和准备以后做的计划分开看。",
}
STATUS_LABELS = {
    "not_recalled": "暂时想不起",
    "withheld": "本人选择先不谈",
    "not_observed": "本次暂未整理清楚",
}
FOCUS = {
    "check_in": (
        "了解近况，准备开始",
        "让练习按您愿意的节奏进行。",
        "简单说说近况，或直接选择先看例子。",
    ),
    "learn": (
        "分清事情、想法、心情和做法",
        "先看示范，再辨认一个新例子。",
        "回应当前例子后，进入自己的经历练习；需要帮助也可以说。",
    ),
    "practice": (
        "用同一件小事练习区分四部分",
        "留意发生了什么、想到什么、感到什么、做了什么。",
        "每项表达或暂留后一起核对，不需要分析得很深。",
    ),
    "review": (
        "核对自己的说法和暂留项",
        "保证记录准确表达您的意思。",
        "确认后换一个新案例；也可以先修改或补充。",
    ),
    "assessment": (
        "换个案例，自己辨认四部分",
        "看看减少提示后，哪些内容已经讲清楚。",
        "四题回答或跳过后统一回看；需要帮助可选提示。",
    ),
    "check_feedback": (
        "回看这次辨认，选择是否补练",
        "分清已理解的内容和还需帮助的地方。",
        "可以用新例子再练一次，也可以继续设置目标。",
    ),
    "learning_goal": (
        "选一个自己愿意练习的方向",
        "让后续练习贴近您的需要。",
        "确认一项目标，或选择暂不设置。",
    ),
    "plan": (
        "选择生活中的一次小练习",
        "给今天学到的方法一次尝试机会。",
        "选择愿意尝试或这次不安排，都可以继续。",
    ),
    "summary": (
        "回顾收获和仍不清楚的地方",
        "为之后怎样指导保留依据。",
        "可以反馈，也可以直接完成本课；完成不等于已经熟练掌握。",
    ),
}
CLARIFICATIONS = {
    "situation": "这一步只看当时发生的事：您实际看到或听到了什么？",
    "thought": "这一步只看当时脑中的解释或判断：您记得自己想到什么吗？",
    "emotion": "这一步只看当时的感受：您会怎样形容自己的心情？",
    "behavior": "这一步只看实际做法：后来您做了什么，或者没有做什么？",
}


def new_flow():
    return {"version": VERSION, "unanswered": {}, "deferred": {}}


def stop_and_review(state, latest):
    """A missing answer is uncollected, never a fabricated answer or low score."""
    if not enabled(state) or state["stage"] not in {"practice", "review"}:
        return
    for field in missing(state):
        state["practice_flow"]["deferred"][field] = {
            "status": "not_observed",
            "source_message_ids": [latest["id"]],
        }
    state["practice_flow"]["stop_probing"] = True
    state["stage"] = "review"


def control_labels(state):
    from cbt_course_llm_freeform import boundaries

    if boundaries.fictional(state):
        return {"defer_practice_field": "这一项还分不清", "decline_practice_field": "先跳过这一项"}
    return {key: CONTROL_LABELS[key] for key in ("defer_practice_field", "decline_practice_field")}


def status_label(state, status):
    from cbt_course_llm_freeform import boundaries

    if boundaries.fictional(state):
        return {
            "not_recalled": "本次暂未辨认清楚",
            "withheld": "本人选择先跳过",
            "not_observed": "本次暂未辨认清楚",
        }[status]
    return STATUS_LABELS[status]


def enabled(state):
    return (
        state.get("lesson_id") == "lesson-1"
        and state.get("practice_flow", {}).get("version") == VERSION
    )


def missing(state):
    from cbt_course_llm_freeform import blueprint

    if blueprint.enabled(state):
        return blueprint.missing(state)
    deferred = state.get("practice_flow", {}).get("deferred", {}) if enabled(state) else {}
    return [
        key
        for key in required_fields(state)
        if key not in state["draft_record"] and key not in deferred
    ]


def current_field(state):
    return next(iter(missing(state)), None)


def ready(state):
    return not missing(state)


def confirmed_ready(state, record):
    fields = record.get("fields", {})
    if not enabled(state):
        return all(key in fields for key in required_fields(state))
    deferred = record.get("deferred_fields", {})
    from cbt_course_llm_freeform import blueprint

    allowed = blueprint.FIELDS if blueprint.enabled(state) else required_fields(state)
    if set(fields) & set(deferred) or not set(deferred).issubset(allowed):
        return False
    return all(
        key in fields
        or (
            key in deferred
            and deferred[key].get("status") in STATUS_LABELS
            and bool(deferred[key].get("source_message_ids"))
        )
        for key in required_fields(state)
    )


def stage_focus(state):
    if not enabled(state) or state.get("completed"):
        return None
    task, purpose, exit_text = FOCUS[state["stage"]]
    from cbt_course_llm_freeform import blueprint

    if blueprint.enabled(state):
        task, purpose, exit_text = {
            "learn": (
                "选择一件愿意分析的困扰",
                "在同一件事中逐步学习认知行为模型。",
                "可选择真实经历或使用虚构案例。",
            ),
            "practice": (
                "同例学习情境、想法、情绪与行为",
                "记录两项本人评分，不替您猜测。",
                "每项可暂留，已表达的不重复问。",
            ),
            "review": (
                "回看认知行为模型与相互影响",
                "具体联系由您核对，不预设因果循环。",
                "可分享新看法、修改或确认。",
            ),
            "assessment": (
                "用原场景练习四要素辨认",
                "每题反馈，保留作答与帮助过程。",
                "四题后汇总，也可跳题。",
            ),
            "learning_goal": (
                "形成整套课程的具体目标",
                "从改善方向到愿意做到的具体事情。",
                "核对一至五项目标，也可暂不设。",
            ),
        }.get(state["stage"], (task, purpose, exit_text))
    from cbt_course_llm_freeform import boundaries

    if boundaries.fictional(state) and state["stage"] in {"practice", "review"}:
        return {
            "task": (
                "辨认虚构案例中的四部分" if state["stage"] == "practice" else "核对案例练习记录"
            ),
            "purpose": "练习区分内容，不需要提供个人经历。",
            "exit": "核对练习记录后，用新案例独立试一试。",
        }
    if (
        state["stage"] == "check_feedback"
        and state["learning_check"]["retry"]["status"] == "active"
    ):
        task, purpose, exit_text = (
            "用新案例再练想法与心情",
            "根据刚才的反馈再试一次，首次表现仍保留。",
            "两题回答或跳过后回看，也可以提前结束补练。",
        )
    return {"task": task, "purpose": purpose, "exit": exit_text}


def payload(state):
    if not enabled(state):
        return None
    field = current_field(state) if state["stage"] == "practice" else None
    return {
        "current_field": field,
        "current_label": FIELD_LABELS.get(field),
        "deferred": [
            {
                "field": key,
                "label": FIELD_LABELS[key],
                "status_label": (
                    "材料未提供，不要求评分"
                    if item.get("reason") == "虚构材料未提供评分，不代角色猜测。"
                    else status_label(state, item["status"])
                ),
                **item,
            }
            for key, item in state["practice_flow"]["deferred"].items()
        ],
        "unanswered_count": len(state["practice_flow"]["unanswered"].get(field, [])),
    }


def feedback_action(text):
    compact = re.sub(r"[，,。！!？?\s]", "", text)
    if compact in {
        "一直让我解释感觉像审问",
        "你一直让我解释感觉像审问",
        "感觉像审问",
        "别一直追问了",
        "不要一直追问了",
        "我不想一直解释",
        "解释太多了",
        "你解释太多了",
        "我想少解释一点",
    }:
        return "request_less_probing"
    return None


def adaptation(state):
    note = state.get("practice_flow", {}).get("interaction_feedback")
    if (
        not enabled(state)
        or state["stage"] != "practice"
        or not note
        or note["case_id"] != state["case_id"]
    ):
        return None
    return note


def control(state, latest, action):
    if action not in FEEDBACK_CONTROLS:
        return defer(state, latest, action)
    field = current_field(state)
    if not enabled(state) or state["stage"] != "practice" or field is None:
        raise ValueError("当前不能调整个人练习的交流方式。")
    if action == "request_less_probing":
        state["practice_flow"]["interaction_feedback"] = {
            "kind": "rule_based_feedback_note",
            "source_message_id": latest["id"],
            "quote": latest["content"],
            "case_id": state["case_id"],
            "scope": "current_personal_practice",
            "status": "awaiting_choice",
            "hypothesis": "本次追问或解释方式可能造成负担，具体原因仍待核对。",
            "alternative_explanation": "也可能是题目表述或本次不愿展开，并非长期偏好。",
            "parameters": {"reply_length": "short", "follow_up": "offer_choice"},
            "choice": None,
            "effect": "not_measured",
        }
        return "我会少追问、说简短些。您可以直接看解释，也可以继续聊。"
    note = adaptation(state)
    if not note:
        raise ValueError("请先选择是否调整当前练习的交流方式。")
    note["choice"] = {"action": action, "source_message_id": latest["id"]}
    if action == "show_brief_explanation":
        note["status"] = "explanation_shown"
        return BRIEF_EXPLANATIONS[field] + "这项也可以先保留，或选择继续聊。"
    note["status"] = "continued"
    note["parameters"]["follow_up"] = "one_question"
    return reply(state)


def explicit_action(text):
    # Only unambiguous whole replies. Sentences containing other facts still go to the model.
    cleaned = text.strip().rstrip("。.!！")
    if cleaned in {
        "暂时想不起",
        "想不起来",
        "我想不起来",
        "暂时想不起来",
        "这一项还分不清",
        CONTROL_LABELS["defer_practice_field"],
    }:
        return "defer_practice_field"
    if cleaned in {
        "暂不评分",
        "先不评分",
        "这一项不想回答",
        "这项先不谈",
        "先跳过这一项",
        CONTROL_LABELS["decline_practice_field"],
    }:
        return "decline_practice_field"
    return None


def defer(state, latest, action):
    field = current_field(state)
    if not enabled(state) or state["stage"] != "practice" or field is None:
        raise ValueError("当前没有可以暂留的个人练习项。")
    status = "not_recalled" if action == "defer_practice_field" else "withheld"
    state["practice_flow"]["deferred"][field] = {
        "status": status,
        "source_message_ids": [latest["id"]],
    }
    note = adaptation(state)
    if note and note["status"] in {"awaiting_choice", "explanation_shown"}:
        note["status"] = "continued"
        note["parameters"]["follow_up"] = "one_question"
        note["choice"] = {"action": action, "source_message_id": latest["id"]}
    if ready(state):
        state["stage"] = "review"
    if state["stage"] == "review":
        return f"“{FIELD_LABELS[field]}”这一项先留空。" + reply(state)
    return (
        f"“{FIELD_LABELS[field]}”这一项先留空，核对时可以补充。接下来看看“{FIELD_LABELS[current_field(state)]}”。"
        + reply(state)
    )


def update(state, focus_before, accepted, latest):
    flow = state["practice_flow"]
    note = adaptation(state)
    if note and note["status"] in {"awaiting_choice", "explanation_shown"}:
        note["status"] = "continued"
        note["parameters"]["follow_up"] = "one_question"
        note["choice"] = {"action": "continued_by_answer", "source_message_id": latest["id"]}
    for field in accepted:
        flow["deferred"].pop(field, None)
        flow["unanswered"].pop(field, None)
    deferred_now = None
    if focus_before and focus_before not in accepted:
        attempts = flow["unanswered"].setdefault(focus_before, [])
        attempts.append(latest["id"])
        if len(attempts) >= MAX_UNANSWERED:
            flow["deferred"][focus_before] = {
                "status": "not_observed",
                "source_message_ids": attempts[-MAX_UNANSWERED:],
            }
            deferred_now = focus_before
    if ready(state):
        state["stage"] = "review"
    lead = ""
    if accepted:
        lead = (
            "已记下。"
            if note
            else "已记下您关于" + "、".join(FIELD_LABELS[key] for key in accepted) + "的说法。"
        )
    if deferred_now:
        lead += f"{FIELD_LABELS[deferred_now]}这一项这次先留空，核对时仍可以补充。"
    return lead + reply(state)


def reply(state):
    from cbt_course_llm_freeform import blueprint

    if blueprint.enabled(state):
        return blueprint.instruction(state)
    if state["stage"] == "review":
        lines = ["这次先整理到这里。请一起核对已记录的原话和暂留项："]
        for key in required_fields(state):
            item = state["draft_record"].get(key)
            text = (
                item["value"]
                if item
                else status_label(state, state["practice_flow"]["deferred"][key]["status"])
            )
            lines.append(f"{FIELD_LABELS[key]}：{text}")
        from cbt_course_llm_freeform import boundaries

        if boundaries.fictional(state):
            lines[0] = "我们核对一下这次虚构案例的练习回答："
        return (
            "\n".join(lines)
            + "\n准确的话，请确认这份练习记录；也可以先修改或补充。确认后我们换个例子做四道小题。"
        )
    field = current_field(state)
    if field is None:
        return "请告诉我哪一项需要修改，以及您希望保留的说法。"
    from cbt_course_llm_freeform import boundaries

    if boundaries.fictional(state):
        return "接着从案例里辨认“" + FIELD_LABELS[field] + "”的内容。"
    from cbt_course_llm_freeform.interaction import guidance

    learned = guidance(state)
    if learned and learned["follow_up"] == "reduce":
        return BRIEF_EXPLANATIONS[field] + "您可以只说记得的部分，不必解释原因。"
    if learned and learned["reply_length"] == "short":
        return QUESTIONS[field]
    note = adaptation(state)
    if note:
        if note["status"] == "awaiting_choice":
            return "我会少追问、说简短些。您可以直接看解释，也可以继续聊。"
        if note["status"] == "explanation_shown":
            return BRIEF_EXPLANATIONS[field] + "这项也可以先保留，或选择继续聊。"
        return QUESTIONS[field]
    attempts = state["practice_flow"]["unanswered"].get(field, [])
    question = CLARIFICATIONS[field] if attempts else QUESTIONS[field]
    return question + "暂时想不起或不愿谈，可以选择这一项先保留。"


def scope(state):
    deferred = state.get("practice_flow", {}).get("deferred", {})
    count = len(state.get("draft_record", {}))
    complete = all(key in state.get("draft_record", {}) for key in required_fields(state))
    from cbt_course_llm_freeform import boundaries

    if boundaries.fictional(state):
        return {
            "status": "guided_example",
            "source_kind": "fictional",
            "recorded_fields": list(state.get("draft_record", {})),
            "deferred_fields": list(deferred),
            "description": "本次为虚构案例辨认练习，不是个人经历；独立检验另行记录。",
        }
    return {
        "status": "complete_record" if complete else "partial_record" if count else "not_observed",
        "source_kind": "personal",
        "recorded_fields": list(state.get("draft_record", {})),
        "deferred_fields": list(deferred),
        "description": (
            "已整理四部分原话；独立运用尚待观察。"
            if complete
            else (
                "本次保留了部分原话与尚未获得的信息，尚未观察到完整四部分整理。"
                if count
                else "本次尚未记录个人经历的四部分原话；暂留项另行标明。"
            )
        ),
    }
