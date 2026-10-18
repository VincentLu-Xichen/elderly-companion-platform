"""Lesson-one learning checks. Reports separate attempts, help and learner facts."""
from __future__ import annotations

import copy

VERSION = "lesson-1-check-v2"
STAGES = ("check_in", "learn", "practice", "review", "assessment", "check_feedback", "learning_goal", "plan", "summary")
LABELS = {"assessment": "换个例子试一试", "check_feedback": "回看与补练", "learning_goal": "我的练习目标"}
STORY_A = "别人和我说话或者打招呼时，我一时没有想到合适的回应。我想到：‘要是自己不回应，对方就会觉得我不礼貌、对聊天没有兴趣，这样会影响我们的关系。’我感到紧张，接着不断找话题，和对方说话。"
STORY_B = "老李到图书馆借书，门口贴着‘今日临时闭馆’。他想到：‘我今天的安排全乱了。’他有些失望，随后转身回家。"
LEGACY_STORY_A = "在社区活动室，一位邻居走过来，对老陈说：‘早上好。’老陈心里冒出一句：‘他会不会觉得我没礼貌？’他有些紧张，低下头，没有回应。"
QUESTIONS = (
    {"field": "situation", "label": "事情", "prompt": "这段描述中，哪部分是在描述情境？", "expected": "别人说话或打招呼时，我一时没有想到合适的回应。", "hint": "找当时发生的具体情形，和对方可能怎样看我的解释分开。"},
    {"field": "thought", "label": "想法", "prompt": "哪部分是在描述当时的想法？", "expected": "担心不回应会被认为不礼貌、没兴趣，并影响关系。", "hint": "想法是对事情的解释、判断或预测。"},
    {"field": "emotion", "label": "心情", "prompt": "哪部分是在描述情绪？", "expected": "紧张。", "hint": "情绪是主观感受，请找故事中明确说出的感受。"},
    {"field": "behavior", "label": "做法", "prompt": "哪部分是在描述实际行为？", "expected": "不断找话题，接着和对方说话。", "hint": "找实际做出的动作，区分愿望、预测和行动。"},
)
RETRY_QUESTIONS = (
    {"field": "thought", "label": "想法", "prompt": "老李脑中出现了哪句话？", "expected": "我今天的安排全乱了。", "hint": QUESTIONS[1]["hint"]},
    {"field": "emotion", "label": "心情", "prompt": "故事明确说到，老李是什么心情？", "expected": "失望。", "hint": QUESTIONS[2]["hint"]},
)
LEGACY_QUESTIONS = (
    {"field": "situation", "label": "事情", "prompt": "这个例子里，老陈遇到了一件什么事？", "expected": "邻居走过来，对老陈说早上好。", "hint": "找故事中外部发生的事，先不猜别人怎么想。"},
    {"field": "thought", "label": "想法", "prompt": "老陈当时脑中冒出了什么想法？", "expected": "他会不会觉得我没礼貌？", "hint": "想法是脑中对事情的解释、判断或预测。"},
    {"field": "emotion", "label": "心情", "prompt": "故事里明确说到，老陈是什么心情？", "expected": "紧张。", "hint": "心情描述感受，例如开心或生气；请找故事中写出的感受。"},
    {"field": "behavior", "label": "做法", "prompt": "老陈随后实际做了什么，或者没有做什么？", "expected": "低下头，没有回应；指出其中一项实际做法也可以。", "hint": "找老陈实际做出的动作或没有做的事，区分愿望与行动。"},
)
VERDICTS = {"matches": "含义符合", "partial": "部分符合", "does_not_match": "需要再区分", "unclear": "仍需澄清", "not_observed": "未观察"}
CONTROL_LABELS = {"request_check_hint": "需要一点提示", "skip_check_question": "这题先跳过", "continue_after_check": "继续，设置练习目标", "start_check_retry": "换个例子再练一次", "finish_check_retry": "结束这次补练", "confirm_learning_goal": "确认这个目标", "skip_learning_goal": "暂不设置目标"}


def new_check():
    return {"version": VERSION, "status": "not_started", "index": 0, "answers": [], "hints": [], "retry": {"status": "not_started", "index": 0, "answers": [], "hints": []}}


def enabled(state):
    return state.get("lesson_id") == "lesson-1" and state.get("learning_check", {}).get("version") in {VERSION, "lesson-1-check-v1"}


def retrying(state):
    return state["stage"] == "check_feedback" and state["learning_check"]["retry"]["status"] == "active"


def current(state):
    retry = retrying(state)
    attempt = state["learning_check"]["retry"] if retry else state["learning_check"]
    legacy = state["learning_check"].get("version") == "lesson-1-check-v1"
    questions = RETRY_QUESTIONS if retry else LEGACY_QUESTIONS if legacy else QUESTIONS
    return attempt, questions, questions[min(attempt["index"], len(questions) - 1)], STORY_B if retry else LEGACY_STORY_A if legacy else STORY_A


def rows(attempt, questions):
    return [{**item, "label": questions[item["question_index"]]["label"], "question": questions[item["question_index"]]["prompt"],
             "verdict_label": VERDICTS[item["verdict"]], "help_label": "接受概念提示后作答" if item["assisted"] else "此前已获得逐题教学反馈" if item.get("prior_feedback") else "本轮未提供概念提示"}
            for item in attempt["answers"]]


def report(state):
    from cbt_course_llm_freeform import practice_flow
    check = state["learning_check"]
    legacy = check.get("version") == "lesson-1-check-v1"
    return {"status": check["status"], "first_attempt": rows(check, LEGACY_QUESTIONS if legacy else QUESTIONS),
            "stopped_by": copy.deepcopy(check.get("stopped_by")),
            "personal_practice_scope": practice_flow.scope(state) if practice_flow.enabled(state) else None,
            "interaction_feedback": copy.deepcopy(state.get("practice_flow", {}).get("interaction_feedback")),
            "retry_status": check["retry"]["status"], "retry_stopped_by": copy.deepcopy(check["retry"].get("stopped_by")), "retry_attempt": rows(check["retry"], RETRY_QUESTIONS),
            "scope": ("此案例此前已出现，不能当作首次陌生案例。" if check.get("prior_exposure") else "") + ("这是历史四题统一反馈记录。" if legacy else "逐题提供反馈，后续题可能受此前解释影响；这是教学练习记录，不是完全独立测量。") + "提示、补练和首次表现分别保留，实际生活使用尚待反馈。"}


def feedback_text(state):
    result = report(state)
    lines = ["这次练习的作答和未作答情况已保存，我们一起回看。"]
    for row in result["first_attempt"]:
        lines.append(f"{row['label']}：{row['verdict_label']}。")
        if row["verdict"] != "matches":
            lines.append("参考含义：" + QUESTIONS[row["question_index"]]["expected"])
    if result["retry_status"] in {"completed", "stopped"}:
        lines.append("新案例补练的回答也已单独保存，首次表现不会被覆盖。")
        for row in result["retry_attempt"]:
            lines.append(f"补练{row['label']}：{row['verdict_label']}。")
            if row["verdict"] != "matches":
                lines.append("参考含义：" + RETRY_QUESTIONS[row["question_index"]]["expected"])
        lines.append("这只说明本次辨认表现。接下来可以设置练习目标。")
    else:
        lines.append("这只说明本次辨认表现。您可以换个例子补练，也可以继续设置练习目标。")
    return "\n".join(lines)


def next_prompt(state):
    if state["stage"] == "learning_goal":
        from cbt_course_llm_freeform import blueprint
        if blueprint.enabled(state):
            return "您希望整套课程结束后，生活中哪些方面得到改善？" + blueprint.GOAL_EXAMPLES + "也可以暂不设置目标。"
        from cbt_course_llm_freeform import boundaries
        if boundaries.blocked(state) or boundaries.fictional(state):
            return "接下来的课程，您愿意先巩固哪一部分的辨认？可以用案例继续练，也可以暂不设置目标。"
        return "您希望接下来的课程，先帮助您在哪件生活小事上更容易应对一点？可以先说一项，也可以暂不设置。"
    if state["stage"] == "check_feedback" and not retrying(state):
        return feedback_text(state)
    attempt, questions, question, story = current(state)
    lead = ("换一个新例子补练，之前的回答仍保留。" if retrying(state) else "用另一段材料练习四要素，每题会给反馈，最后一起汇总。需要帮助或想跳过都可以。") if attempt["index"] == 0 else "接着看下一题。"
    return lead + ("\n" + story if attempt["index"] == 0 else "") + f"\n第 {attempt['index'] + 1}/{len(questions)} 题：" + question["prompt"]


def begin(state):
    state["learning_check"] = new_check()
    state["learning_check"]["prior_exposure"] = bool(state.get("previous_learning_checks"))
    state["learning_check"]["status"] = "active"
    state["stage"] = "assessment"
    return next_prompt(state)


def save_answer(state, latest, verdict, reason):
    attempt, questions, _, _ = current(state)
    index = attempt["index"]
    attempt["answers"].append({"question_index": index, "answer": latest["content"] if verdict != "not_observed" else "",
        "source_message_id": latest["id"], "verdict": verdict, "reason": reason,
        "prior_feedback": index > 0, "assisted": any(item["question_index"] <= index for item in attempt["hints"])})
    questions = RETRY_QUESTIONS if retrying(state) else QUESTIONS
    feedback = ("这题先跳过，不作为答错。" if verdict == "not_observed" else
        "这次含义符合。" if verdict == "matches" else "我们再区分一下。参考含义：" + questions[index]["expected"]) + "\n"
    attempt["index"] += 1
    if attempt["index"] == len(questions):
        attempt["status"] = "completed"
        state["stage"] = "check_feedback"
        state["learning_result"] = report(state)
        return feedback + feedback_text(state)
    return feedback + next_prompt(state)


def hint(state, latest):
    attempt, _, question, _ = current(state)
    attempt["hints"].append({"question_index": attempt["index"], "text": question["hint"], "requested_by_message_id": latest["id"]})
    return question["hint"] + "\n" + question["prompt"]


def answer(state, latest, agent):
    text = latest["content"].strip()
    if any(word in text for word in ("再读一遍", "再看一遍", "重复题目")):
        return current(state)[3] + "\n" + current(state)[2]["prompt"], None
    if text in {"不知道", "我不知道"} or any(word in text for word in ("没听懂", "不明白", "需要提示", "不知道怎么")):
        return hint(state, latest), None
    _, _, question, story = current(state)
    result = agent.evaluate_answer([latest], context={"story": story, "question": question["prompt"], "field": question["field"], "expected": question["expected"], "retry": retrying(state),
        "primary_interaction_decision": state.get("latest_interaction_event", {}).get("judgment")})
    decision = result.decision
    if decision.source_message_id != latest["id"]:
        raise RuntimeError("检验判读没有引用本轮本人回答，本轮进度未改变。")
    if getattr(decision, "interaction", None) is not None and (decision.interaction.verdict != "not_feedback" or decision.verdict == "unclear"):
        # Hand back the semantic feedback before recording an answer or hint.
        return decision.interaction, result.completion
    if any(word in decision.reason for word in ("人格", "智力", "诊断", "理解能力差")):
        raise RuntimeError("检验判读包含不支持的个人标签。")
    if decision.verdict == "needs_help":
        return hint(state, latest), result.completion
    if decision.verdict == "not_answer":
        return "明白，这轮先不计作答，题目和已有回答保持不变。", result.completion
    if decision.verdict == "unclear" and state.get("latest_interaction_event", {}).get("judgment"):
        return "这轮先不计作答，也不改变题目。您可以继续回答当前题，或直接说明想怎样调整。", result.completion
    return save_answer(state, latest, decision.verdict, decision.reason), result.completion


def stop_remaining(state, latest):
    """Preserve first answers; remaining items are unobserved, never wrong."""
    attempt, questions, _, _ = current(state)
    attempt["stopped_by"] = {"source_message_id": latest["id"], "quote": latest["content"], "reason": "learner_requested_stop"}
    while attempt["index"] < len(questions):
        save_answer(state, latest, "not_observed", "本人选择不继续本组题，未观察作答。")
    # save_answer stores a report after the final item. Keep the interruption as
    # a distinct provenance record rather than a learner answer.
    state["learning_result"] = report(state)


def control(state, latest, action):
    if action not in CONTROL_LABELS:
        return None
    checking = state["stage"] == "assessment" or retrying(state)
    if action == "request_check_hint" and checking:
        return hint(state, latest)
    if action == "skip_check_question" and checking:
        return save_answer(state, latest, "not_observed", "本人选择先跳过。")
    if action == "finish_check_retry" and retrying(state):
        state["learning_check"]["retry"]["status"] = "stopped"
        state["learning_result"] = report(state)
        return "这次补练已停下，已回答的部分仍保留。" + feedback_text(state)
    if action == "start_check_retry" and state["stage"] == "check_feedback" and state["learning_check"]["retry"]["status"] == "not_started":
        state["learning_check"]["retry"]["status"] = "active"
        return next_prompt(state)
    if action == "continue_after_check" and state["stage"] == "check_feedback" and not retrying(state):
        state["stage"] = "learning_goal"
        return next_prompt(state)
    if action == "skip_learning_goal" and state["stage"] == "learning_goal":
        state["learning_goal"] = {"status": "skipped", "source_message_id": latest["id"]}
        state["stage"] = "plan"
        return "已保留您暂不设置目标的选择。接下来选择是否安排一次课后观察。"
    if action == "confirm_learning_goal" and state["stage"] == "learning_goal" and state.get("learning_goal_draft"):
        state["learning_goal"] = {"status": "confirmed", **copy.deepcopy(state["learning_goal_draft"]), "confirmation_message_id": latest["id"]}
        state["stage"] = "plan"
        return "这个练习目标已按您的确认保存。接下来选择是否安排一次课后观察。"
    raise ValueError("当前阶段不能执行这个检验或目标操作。")


def goal_answer(state, latest):
    if len(latest["content"]) > 500:
        raise ValueError("请先用五百字以内说一项希望练习的方向。")
    if latest["content"].strip() in {"不知道", "我不知道", "没想好"}:
        return "可以暂时不决定，选择‘暂不设置目标’即可继续。"
    state["learning_goal_draft"] = {"value": latest["content"], "source_message_id": latest["id"]}
    return "我记下您希望练习的方向：" + latest["content"] + "\n请核对，您可以说‘确认这个目标’，也可以修改这句话、暂不设置，或使用旁边的操作。"


def payload(state):
    check = state["learning_check"]
    checking = state["stage"] == "assessment" or retrying(state)
    result = {"enabled": True, "checking": checking, "retrying": retrying(state), "first_completed": check["status"] == "completed",
              "can_retry": state["stage"] == "check_feedback" and check["retry"]["status"] == "not_started"}
    if checking:
        attempt, questions, question, story = current(state)
        result.update(story=story, question=question["prompt"], number=attempt["index"] + 1, total=len(questions))
    if check["status"] == "completed":
        result["result"] = report(state)
        if retrying(state):
            result["result"]["retry_attempt"] = []
    return result


def example_answer(state):
    if state["stage"] == "learning_goal":
        return "我希望等家人回复时，先分清发生的事情和自己的猜测。"
    if state["stage"] == "assessment" or retrying(state):
        _, _, question, _ = current(state)
        return question["expected"].split("；")[0]
    return ""
