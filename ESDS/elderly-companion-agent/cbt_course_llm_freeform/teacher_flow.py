"""Explicit source-blueprint teaching for lessons 1–2; never infer a weekly score."""

from __future__ import annotations

import copy
import re

VERSION = "teacher-flow/1"
MOOD_QUESTION = "在练习开始之前，请给自己上周整体的状态打一个1—10分：1分表示非常糟糕，10分表示非常好。这不是给自己的表现打成绩；不愿评分也可以直接说。"
INTRO = "这套练习以认知行为治疗（CBT）为理论基础，围绕认知结构调整和行为激活两大模块，学习基本方法来应对日常生活中的困扰。请先看看八次课程的内容，再开始本课。"
OVERVIEW = [
    ("认知行为三角", "区分情境、认知、情绪、行为；制定练习目标"),
    ("捕捉我的思维", "识别自动思维；学习记录三栏表"),
    ("识别歪曲思维", "识别歪曲的思维"),
    ("相反行为", "学习相反行为"),
    ("行为激活／行为暴露（二选一）", "回顾三栏表、相反行为；对应活动或暴露的难度等级排序"),
    ("修正我的思维", "苏格拉底提问；学习记录五栏表"),
    (
        "睡眠／放松训练（二选一）",
        "睡眠：睡眠日志、睡眠计划、心理教育。放松：心理教育、渐进式肌肉松弛、4–7–8深度呼吸",
    ),
    ("预防复发", "回顾练习进展；制定预防复发计划"),
]
EMOTIONS = "悲伤、低落、孤独、不悦；焦虑、担心、害怕、恐惧、紧张；愤怒、暴怒、恼怒、烦恼；羞耻、尴尬、羞辱；失望、内疚、受伤；嫉妒、羡慕、疑虑。也可以有平静、开心或混合感受，用自己的词表达即可。"
EXAM = "昨天，我在学校参加数学考试，最后一道难题没有做出来。我想到‘试题太难了，别人肯定做出来了，只有我不会，成绩肯定很糟’，感到心烦。"
CARDS = {
    "situation": dict(
        title="情境：具体发生了什么",
        definition="情境是特定时间、地点发生的具体事情，不包括随后对事情的评价。",
        example=EXAM,
        explanation="示例中的情境是：昨天在学校参加数学考试，最后一道题没做出来。",
        expression="可以先说时间、地点，以及实际看到、听到或发生的事。",
    ),
    "thought": dict(
        title="认知／自动思维：当时怎样解释",
        definition="想法也叫认知或自动思维，是面对情境时迅速出现的解释、判断、预测或画面。有时很清楚，有时还没留意就已经出现了。",
        example=EXAM,
        explanation="‘别人肯定做出来了，只有我不会，成绩肯定很糟’是示例中的想法；‘没做出最后一题’是情境。",
        expression="可以用‘我当时认为／觉得……’帮助回想，但不必套固定句式。情绪明显变化时，留意那一刻脑中闪过的话；‘我觉得’后面也可能是感受，要看具体含义。",
    ),
    "emotion": dict(
        title="情绪：当时有什么感受",
        definition="情绪是当时的主观感受，例如焦虑、紧张、害羞或生气，有时很难立刻找到合适的词。",
        example=EXAM,
        explanation="‘心烦’是示例中的情绪。‘我觉得成绩会很糟’则是对结果的预测。",
        expression="可以说‘我当时感到……’。不知道怎么形容时参考词汇，不需要勉强选一个。",
        vocabulary=EMOTIONS,
    ),
    "behavior": dict(
        title="行为：实际做了什么",
        definition="行为是实际发生的动作、行动，也包括没有采取某项行动；想做、打算做不等于已经做了。",
        example="紧张时有人在原地走动，有人低下头、减少目光接触，也有人仍坐在座位上。",
        explanation="走动、低头、坐着是动作。‘想和人说话’只表达愿望，还不能确定实际做了什么。",
        expression="可以用‘我当时做了……／没有……’描述实际情况。",
    ),
}
MODEL = "情境引出我们对事情的解读；想法、情绪与行为可能相互影响。模型用于一起理解经历，不代表每次都存在同一种循环。请结合您的记录核对，具体联系由您判断。"
AUTOMATIC = "三栏表分别记录情境、自动思维和情绪。自动思维往往很快出现，未必是刻意思考：可以回到情绪有变化的那一刻，留意脑中闪过的话或画面，再把它和实际发生的事分开。先学会捕捉，不要求现在改变想法。"
GOALS = [
    "觉察负面情绪",
    "用认知行为模型分析困扰",
    "识别自己的歪曲思维",
    "每周用三栏表记录一次事情",
    "每周记录一次五栏表，检查原来的想法",
    "每周尝试一次相反行为",
    "每月尝试一次行为暴露",
    "学习放松方法，并考虑每天练习一次",
    "一个月内有两周记录睡眠日记",
]
RAIN_HELP = {
    "emotion": "情绪是感受，例如小明失恋后可能伤心、难过。回到郊游被雨耽搁的情境，您可能有什么感受？可以参考："
    + EMOTIONS,
    "thought": "想法是面对事情时的解释或态度。例如小明和朋友约好见面，朋友迟到，他第一反应是‘朋友放我鸽子了’；迟到是发生的事，后一句是他的解释。回到郊游被雨耽搁的情境，那一刻您可能想到什么？",
}


def enabled(state):
    return state.get("teacher_flow", {}).get("version") == VERSION and (
        state["lesson_id"] != "lesson-1" or "blueprint" in state
    )


def new_flow(lesson_id):
    return dict(
        version=VERSION,
        overview_seen=lesson_id != "lesson-1",
        weekly_mood={"status": "pending"},
        cards=[],
        events=[],
    )


def card(state, field, *, help=False, source_message_id=None, activity="personal"):
    if not enabled(state) or field not in CARDS:
        return
    identity = f"{activity}:{field}:{'help' if help else 'teaching'}"
    flow = state["teacher_flow"]
    if any(
        item["id"] == identity
        or not help
        and not item["help"]
        and item["field"] == field
        and item["activity"] in {activity, "introduction"}
        for item in flow["cards"]
    ):
        return
    flow["cards"].append(
        dict(
            id=identity,
            field=field,
            help=help,
            activity=activity,
            source_message_id=source_message_id,
            **copy.deepcopy(CARDS[field]),
        )
    )


def after_lesson1(state, focus, accepted, latest):
    if not enabled(state):
        return
    for field in accepted:
        card(state, field, source_message_id=latest["id"])
    if focus in CARDS and focus not in accepted:
        card(state, focus, help=True, source_message_id=latest["id"])


def help_text(field):
    c = CARDS[field]
    return "\n".join(
        c[k] for k in ("definition", "example", "explanation", "expression", "vocabulary") if k in c
    )


def parse_weekly_score(text):
    # Accept a number or a clearly labelled weekly statement, not arbitrary
    # numbers in life stories, negated scores, or conflicting alternatives.
    value = text.strip().rstrip("。.!！")
    match = re.fullmatch(
        r"(?:(?:我)?(?:给自己)?(?:上周|这一周|最近一周|这周)(?:整体|的)?(?:状态|心情|过得|评分|打分|表现)?(?:是|打|给|大概|大约|还算|：|:|\s)*)?([0-9]+(?:\.[0-9]+)?|[一二三四五六七八九十])\s*(?:分|/10)?",
        value,
    )
    if not match:
        scores = list(
            re.finditer(r"(?<![\d.])([0-9]+(?:\.[0-9]+)?|[一二三四五六七八九十])\s*分", value)
        )
        if len(scores) != 1 or any(
            word in value
            for word in (
                "不是",
                "并非",
                "不打",
                "不给",
                "不想",
                "如果",
                "假如",
                "比如",
                "他说",
                "她说",
                "不确定",
                "？",
                "?",
                "今天",
                "昨天",
                "情绪强度",
                "相信程度",
            )
        ):
            return None
        match = scores[0]
    raw = match[1]
    number = "一二三四五六七八九十".index(raw) + 1 if raw in "一二三四五六七八九十" else float(raw)
    return number if 1 <= number <= 10 else None


def mood_feedback(number):
    band = "low" if number <= 3 else "middle" if number <= 6 else "high"
    text = {
        "low": "您给上周的状态打了较低的分，听起来这段时间可能不容易。谢谢您告诉我，我们按您的节奏来。",
        "middle": "谢谢您的评分。我先记下您对上周状态的评价；单凭这个分数，还不能知道这一周具体经历了什么。",
        "high": "谢谢您告诉我，您给上周状态的评价较高。之后也可以保留其中不轻松的时刻。",
    }[band]
    return band, text + "无论上一周如何，谢谢您来到这次练习。接下来开始今天的内容。"


def handle_checkin(runtime, state, latest, action):
    """Return None outside this subflow; run after safety/interaction handling."""
    if (
        not enabled(state)
        or state["stage"] != "check_in"
        or state.get("lesson2_flow", {}).get("step", "check_in") != "check_in"
    ):
        return None
    flow = state["teacher_flow"]
    text = latest.get("content", "").strip()
    if action == "start_mood_check" or (
        action == "chat" and text in {"已看完", "好的，已看完", "看完了", "开始评分"}
    ):
        flow["overview_seen"] = True
        flow["events"].append(dict(kind="overview_read", source_message_id=latest["id"]))
        return MOOD_QUESTION
    if action not in {"chat", "skip_checkin"}:
        return None
    declined = re.fullmatch(
        r"(?:我)?(?:不想|不愿意|不愿|暂时不想|暂时不|暂不|先不|不)(?:给自己)?(?:评分|打分|给分)[了吧。！!]*",
        text,
    )
    if action == "skip_checkin" or text == "跳过评分" or declined:
        flow["overview_seen"] = True
        flow["weekly_mood"] = dict(status="declined", source_message_id=latest["id"])
        feedback = "可以，这次不评分。"
    else:
        number = parse_weekly_score(text)
        if number is None:
            if not flow["overview_seen"]:
                return "请先查看八课内容，准备好后说‘已看完’。" + MOOD_QUESTION
            return "先不把这段描述换算成分数。" + MOOD_QUESTION
        flow["overview_seen"] = True
        band, feedback = mood_feedback(number)
        flow["weekly_mood"] = dict(
            status="provided",
            value=number,
            scale_min=1,
            scale_max=10,
            target="previous_week_overall_state",
            band=band,
            quote=text,
            source_message_id=latest["id"],
        )
        state["mood"] = dict(value=text, source_message_id=latest["id"])
    if state["lesson_id"] == "lesson-2":
        from cbt_course_llm_freeform import lesson2_flow

        return feedback + "\n" + lesson2_flow.enter_homework(state)
    state["stage"] = "learn"
    from cbt_course_llm_freeform.runtime import next_question

    return (
        feedback
        + "\n今天先学习认知行为模型的情境、认知、情绪和行为四个要素。"
        + next_question(state)
    )


def payload(state):
    if not enabled(state):
        return None
    flow = copy.deepcopy(state["teacher_flow"])
    flow["mood_question"] = MOOD_QUESTION
    flow["overview_pending"] = (
        state["lesson_id"] == "lesson-1"
        and state["stage"] == "check_in"
        and not flow["overview_seen"]
    )
    flow["overview"] = (
        [{"title": title, "practice": practice} for title, practice in OVERVIEW]
        if state["lesson_id"] == "lesson-1"
        else []
    )
    flow["model_explanation"] = MODEL
    flow["goal_examples"] = GOALS if state["lesson_id"] == "lesson-1" else []
    flow["automatic_thought_teaching"] = AUTOMATIC if state["lesson_id"] == "lesson-2" else None
    return flow
