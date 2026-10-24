"""Teaching definitions shared by the two active lessons."""

from __future__ import annotations


STAGES = ('check_in', 'learn', 'practice', 'review', 'plan', 'summary')

STAGE_LABELS = {
    'check_in': '近况与回顾',
    'learn': '一起看个例子',
    'practice': '试试自己的经历',
    'review': '核对学习记录',
    'plan': '选择课后安排',
    'summary': '回顾本课收获',
}

FIELD_LABELS = {
    'thought_belief': '对想法的相信程度',
    'emotion_intensity': '情绪强度',
    'relationship_note': '回看后的想法',
    'mood': '最近的状态',
    'learning_response': '示例中的回答',
    'situation': '发生的事情',
    'thought': '当时的想法',
    'emotion': '当时的心情',
    'behavior': '当时的做法',
    'goal': '希望练习的方向',
    'feedback': '本人的课后反馈',
}

REQUIRED_FIELDS = {
    'lesson-1': ('situation', 'thought', 'emotion', 'behavior'),
    'lesson-2': ('situation', 'thought', 'emotion'),
}

PRACTICE_PLANS = {
    'lesson-1': '这周愿意时，留意一件小事，分开记下事情、想法、心情和做法；只在心里回想也可以。',
    'lesson-2': '这周愿意时，留意一件小事，分开记下事情、想法和心情；只在心里回想也可以。',
}

LESSON_1_DEMONSTRATION = '先看一个示范：朋友没有回电话，小林想到‘他是不是不愿理我’，感到失落，于是没有再联系。没有回电话是发生的事，‘他是不是不愿理我’是想法，失落是心情，没有再联系是做法。这几部分可能相互影响。'

LESSON_1_GUIDED_EXAMPLE = {
    'story': '小周买菜时，发现常去的摊位今天没开。他心里冒出一句：‘今天买不到想要的菜了。’他有些失望，随后去旁边的摊位看看。',
    'focus_quote': '今天买不到想要的菜了',
    'question': '这里‘今天买不到想要的菜了’属于事情、想法、心情、做法中的哪一部分？',
}

EXAMPLES = {
    'lesson-1': '先看一个示范：朋友没有回电话，小林想到‘他是不是不愿理我’，感到失落，于是没有再联系。没有回电话是发生的事，‘他是不是不愿理我’是想法，失落是心情，没有再联系是做法。这几部分可能相互影响。\n'
    '\n'
    '再换个小例子，一起练一下：小周买菜时，发现常去的摊位今天没开。他心里冒出一句：‘今天买不到想要的菜了。’他有些失望，随后去旁边的摊位看看。\n'
    '\n'
    '这里‘今天买不到想要的菜了’属于事情、想法、心情、做法中的哪一部分？可以用日常说法回答，不确定也没关系。',
    'lesson-2': '您和老朋友约好去公园，临出门下雨，安排取消了。有人想‘难得约一次又去不成’，有人想‘下次再约也行’。同一件事，这两种想法可能带来什么不同的心情？',
}

SKILLS = {'lesson-1': '辨认事情、想法、心情与做法', 'lesson-2': '辨认事情、想法与心情'}

PREDECESSORS = {'lesson-1': (), 'lesson-2': ('lesson-1',)}

MODEL_TOKEN_LIMITS = {'lesson-1': 1200, 'lesson-2': 900}

PREVIEW_EXAMPLES = {
    'lesson-1': {
        'learn': '昨晚女儿没有回电话，我想分析这一件事。',
        'practice': '事情：女儿昨晚没有回电话；想法：她是不是不在乎我；相信程度：6分；心情：有些失落；情绪强度：5分；做法：我没有再打电话',
    },
    'lesson-2': {
        'learn': '一个可能失落，另一个可能平静，因为想法不同。',
        'practice': '事情：女儿昨晚没有回电话；想法：她肯定不在乎我；心情：有些失落',
    },
}

INPUT_LABELS = {'situation': '事情', 'thought': '想法', 'emotion': '心情', 'behavior': '做法'}

QUESTIONS = {
    'situation': '当时具体发生了什么？',
    'thought': '当时脑中最先出现的是哪句话？',
    'emotion': '当时心里是什么感受？',
    'behavior': '带着这份心情，您当时做了什么，或没有做什么？',
}


def required_fields(state: dict) -> tuple[str, ...]:
    return REQUIRED_FIELDS.get(state["lesson_id"], ())


def lesson_example(state: dict) -> str:
    return EXAMPLES[state["lesson_id"]]


def preview_examples(state: dict) -> dict:
    lesson = state["lesson_id"]
    examples = dict(PREVIEW_EXAMPLES.get(lesson, {}))
    if state.get("draft_record") and lesson in PREVIEW_EXAMPLES:
        labels = {label: field for field, label in INPUT_LABELS.items()}
        examples["practice"] = "；".join(
            part
            for part in examples["practice"].split("；")
            if labels.get(part.split("：")[0]) not in state["draft_record"]
        )
    from cbt_course_llm_freeform import learning_check
    from cbt_course_llm_freeform import blueprint

    if blueprint.enabled(state) and state["stage"] == "practice":
        focus = next(iter(blueprint.missing(state)), None)
        if focus in blueprint.RATINGS:
            examples["practice"] = "6分"
    if learning_check.enabled(state):
        examples["learning_goal"] = "我希望等家人回复时，先分清发生的事情和自己的猜测。"
        if state["stage"] == "assessment" or learning_check.retrying(state):
            examples[state["stage"]] = learning_check.example_answer(state)
    return {
        **examples,
        "check_in": "这一周还算平稳，大概六分。",
        "summary": "生活里的例子更容易懂，术语有些没听懂，希望慢一点。",
    }


def task_step_id(state: dict) -> str:
    """A subtask may span several turns. This identifier is assigned by code."""
    from cbt_course_llm_freeform import lesson2_flow

    if lesson2_flow.enabled(state):
        f = state["lesson2_flow"]
        return f"lesson2:{f['step']}:{lesson2_flow.focus(state) or f['quiz']['index']}"
    stage = state["stage"]
    from cbt_course_llm_freeform import learning_check

    if learning_check.enabled(state) and (stage == "assessment" or learning_check.retrying(state)):
        attempt, _, question, _ = learning_check.current(state)
        return f"{stage}:{'retry:' if learning_check.retrying(state) else ''}{question['field']}:{attempt['index']}"
    path = state.get("path")
    if stage == "practice":
        from cbt_course_llm_freeform.practice_flow import current_field

        missing = current_field(state) or "record"
        return f"practice:{path + ':' if path else ''}{missing}"
    if path:
        return f"{stage}:{path}"
    return {
        "check_in": "check_in:recent_state",
        "learn": "learn:example",
        "review": "review:record",
        "plan": "plan:choice",
        "summary": "summary:feedback",
        "check_feedback": "check_feedback:review",
        "learning_goal": "learning_goal:confirm",
    }[stage]


def stage_intro(lesson_id: str, stage: str, *, path: str | None = None) -> str:
    if stage == "check_in":
        return (
            "我们先聊聊最近一周。您可以用几句话说说，也可以用一到十分表示心情；不想评分也没关系。"
        )
    if stage == "learn":
        return lesson_example({"lesson_id": lesson_id, "path": path})
    if stage == "practice":
        if lesson_id == "lesson-1":
            return "接下来用同一件小事练习区分事情、想法、心情和做法，不需要分析得很深。想不起或不愿谈的部分可以先留空，最后一起核对。最近有没有一件愿意聊的小事？先说具体发生了什么就好。"
        return "现在试试您自己的例子。最近有没有一件愿意聊的小事？先说当时具体发生了什么就好。"
    if stage == "review":
        return "我把您的原话整理成了学习记录。请看看是否准确；可以直接告诉我哪里要改。" + (
            "确认后，我们换个例子做四道小题。"
            if lesson_id == "lesson-1"
            else "确认后再选课后安排。"
        )
    if stage == "plan":
        return (
            "记录已按您的确认保存。"
            + PRACTICE_PLANS[lesson_id]
            + "您愿意试一次，还是这次不安排？两种选择都可以。"
        )
    if stage == "summary":
        return "今天我们一起完成了一次练习，这代表本次尝试，不代表已经完全掌握。您可以说说哪里有帮助、哪里难懂，也可以直接完成本课。"
    return "本课已结束，您可以在这里回看自己的记录与课后安排。"
