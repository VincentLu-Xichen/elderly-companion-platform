"""Lesson-one learning checks. Reports separate attempts, help and learner facts."""
from __future__ import annotations

import copy

VERSION = "lesson-1-check-v1"
STAGES = ("check_in", "learn", "practice", "review", "assessment", "check_feedback", "learning_goal", "plan", "summary")
LABELS = {"assessment": "换个例子试一试", "check_feedback": "回看与补练", "learning_goal": "我的练习目标"}
STORY_A = "在社区活动室，一位邻居走过来，对老陈说：‘早上好。’老陈心里冒出一句：‘他会不会觉得我没礼貌？’他有些紧张，低下头，没有回应。"
STORY_B = "老李到图书馆借书，门口贴着‘今日临时闭馆’。他想到：‘我今天的安排全乱了。’他有些失望，随后转身回家。"
QUESTIONS = (
    {"field": "situation", "label": "事情", "prompt": "这个例子里，老陈遇到了一件什么事？", "expected": "邻居走过来，对老陈说早上好。", "hint": "找故事中外部发生的事，先不猜别人怎么想。"},
    {"field": "thought", "label": "想法", "prompt": "老陈当时脑中冒出了什么想法？", "expected": "他会不会觉得我没礼貌？", "hint": "想法是脑中对事情的解释、判断或预测。"},
    {"field": "emotion", "label": "心情", "prompt": "故事里明确说到，老陈是什么心情？", "expected": "紧张。", "hint": "心情描述感受，例如开心或生气；请找故事中写出的感受。"},
    {"field": "behavior", "label": "做法", "prompt": "老陈随后实际做了什么，或者没有做什么？", "expected": "低下头，没有回应；指出其中一项实际做法也可以。", "hint": "找老陈实际做出的动作或没有做的事，区分愿望与行动。"},
)
RETRY_QUESTIONS = (
    {"field": "thought", "label": "想法", "prompt": "老李脑中出现了哪句话？", "expected": "我今天的安排全乱了。", "hint": QUESTIONS[1]["hint"]},
    {"field": "emotion", "label": "心情", "prompt": "故事明确说到，老李是什么心情？", "expected": "失望。", "hint": QUESTIONS[2]["hint"]},
)
VERDICTS = {"matches": "含义符合", "partial": "部分符合", "does_not_match": "需要再区分", "unclear": "仍需澄清", "not_observed": "未观察"}
CONTROL_LABELS = {"request_check_hint": "需要一点提示", "skip_check_question": "这题先跳过", "continue_after_check": "继续，设置练习目标", "start_check_retry": "换个例子再练一次", "finish_check_retry": "结束这次补练", "confirm_learning_goal": "确认这个目标", "skip_learning_goal": "暂不设置目标"}


def new_check():
    return {"version": VERSION, "status": "not_started", "index": 0, "answers": [], "hints": [], "retry": {"status": "not_started", "index": 0, "answers": [], "hints": []}}


def enabled(state):
    return state.get("lesson_id") == "lesson-1" and state.get("learning_check", {}).get("version") == VERSION


def retrying(state):
    return state["stage"] == "check_feedback" and state["learning_check"]["retry"]["status"] == "active"


def current(state):
    retry = retrying(state)
    attempt = state["learning_check"]["retry"] if retry else state["learning_check"]
    questions = RETRY_QUESTIONS if retry else QUESTIONS
    return attempt, questions, questions[min(attempt["index"], len(questions) - 1)], STORY_B if retry else STORY_A


def rows(attempt, questions):
    return [{**item, "label": questions[item["question_index"]]["label"], "question": questions[item["question_index"]]["prompt"],
             "verdict_label": VERDICTS[item["verdict"]], "help_label": "接受概念提示后作答" if item["assisted"] else "本轮未提供概念提示"}
            for item in attempt["answers"]]


def report(state):
    from cbt_course_llm_freeform import practice_flow
    check = state["learning_check"]
    return {"status": check["status"], "first_attempt": rows(check, QUESTIONS),
            "personal_practice_scope": practice_flow.scope(state) if practice_flow.enabled(state) else None,
            "interaction_feedback": copy.deepcopy(state.get("practice_flow", {}).get("interaction_feedback")),
            "retry_status": check["retry"]["status"], "retry_attempt": rows(check["retry"], RETRY_QUESTIONS),
            "scope": ("此案例此前已出现，不能当作首次陌生案例。" if check.get("prior_exposure") else "") + "这是本次任务的判读记录；提示、补练和首次表现分别保留，实际生活使用尚待反馈。"}


def feedback_text(state):
    result = report(state)
    lines = ["四题的首次回答已保存，我们一起回看。"]
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
        from cbt_course_llm_freeform import boundaries
        if boundaries.blocked(state) or boundaries.fictional(state):
            return "接下来的课程，您愿意先巩固哪一部分的辨认？可以用案例继续练，也可以暂不设置目标。"
        return "您希望接下来的课程，先帮助您在哪件生活小事上更容易应对一点？可以先说一项，也可以暂不设置。"
    if state["stage"] == "check_feedback" and not retrying(state):
        return feedback_text(state)
    attempt, questions, question, story = current(state)
    lead = ("换一个新例子补练，之前的回答仍保留。" if retrying(state) else "换个例子看看刚才有没有讲清楚。四题答完后一起回看，需要帮助或想跳过都可以。") if attempt["index"] == 0 else "已记下您的回答，接着看下一题。"
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
        "assisted": any(item["question_index"] <= index for item in attempt["hints"])})
    attempt["index"] += 1
    if attempt["index"] == len(questions):
        attempt["status"] = "completed"
        state["stage"] = "check_feedback"
        state["learning_result"] = report(state)
        return feedback_text(state)
    return next_prompt(state)


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
    result = agent.evaluate_answer([latest], context={"story": story, "question": question["prompt"], "field": question["field"], "expected": question["expected"], "retry": retrying(state)})
    decision = result.decision
    if decision.source_message_id != latest["id"]:
        raise RuntimeError("检验判读没有引用本轮本人回答，本轮进度未改变。")
    if any(word in decision.reason for word in ("人格", "智力", "诊断", "理解能力差")):
        raise RuntimeError("检验判读包含不支持的个人标签。")
    if decision.verdict == "needs_help":
        return hint(state, latest), result.completion
    return save_answer(state, latest, decision.verdict, decision.reason), result.completion


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
