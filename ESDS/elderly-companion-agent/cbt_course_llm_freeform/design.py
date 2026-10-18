"""Versioned lesson definitions. Progress is a teaching stage, not mastery."""
from __future__ import annotations

STAGES = ("check_in", "learn", "practice", "review", "plan", "summary")
STAGE_LABELS = dict(zip(STAGES, ("近况与回顾", "一起看个例子", "试试自己的经历", "核对学习记录", "选择课后安排", "回顾本课收获")))
FIELD_LABELS = {
    "thought_belief": "对想法的相信程度", "emotion_intensity": "情绪强度", "relationship_note": "回看后的想法",
    "mood": "最近的状态", "learning_response": "示例中的回答",
    "situation": "发生的事情", "thought": "当时的想法", "emotion": "当时的心情",
    "behavior": "当时的做法", "goal": "希望练习的方向", "feedback": "本人的课后反馈",
    "awareness_note": "我怎样理解这条想法的依据",
    "action_fit": "原来的做法对我是否有帮助", "alternative_action": "我可以考虑的替代做法",
    "safety_note": "我的边界与调整条件", "activity_goal": "这件活动对我的意义",
    "first_step": "我愿意考虑的第一小步", "when_where": "何时、在哪里尝试",
    "barrier_plan": "遇到阻碍时如何调整", "feared_prediction": "我担心会发生什么",
    "graded_steps": "由容易到困难的小台阶", "evidence_for": "支持原想法的信息",
    "evidence_against": "不同的信息或尚未核实之处", "balanced_thought": "我现在更平衡的说法",
    "next_step": "下一步如何核对或应对", "sleep_pattern": "我注意到的睡眠情况",
    "sleep_habit": "我想留意的睡前习惯", "stress_cue": "我想放松时的信号",
    "relax_method": "我选择的舒适放松方式", "early_signal": "再遇困难时的早期信号",
    "helpful_skill": "我愿意继续使用的技能", "response_plan": "看到信号后先做什么",
    "support_plan": "需要时怎样获得支持", "review_plan": "何时回看并调整计划",
}
REQUIRED_FIELDS = {
    "lesson-1": ("situation", "thought", "emotion", "behavior"),
    "lesson-2": ("situation", "thought", "emotion"),
    "lesson-3": ("situation", "thought", "emotion", "awareness_note"),
    "lesson-4": ("situation", "emotion", "behavior", "action_fit", "alternative_action", "safety_note"),
    "lesson-5": ("situation", "first_step", "when_where", "barrier_plan", "safety_note"),
    "lesson-6": ("situation", "thought", "emotion", "evidence_for", "evidence_against", "balanced_thought", "next_step"),
    "lesson-7": ("first_step", "when_where", "safety_note"),
    "lesson-8": ("early_signal", "helpful_skill", "response_plan", "support_plan", "review_plan"),
}
PRACTICE_PLANS = {
    "lesson-1": "这周愿意时，留意一件小事，分开记下事情、想法、心情和做法；只在心里回想也可以。",
    "lesson-2": "这周愿意时，留意一件小事，分开记下事情、想法和心情；只在心里回想也可以。",
    "lesson-3": "这周愿意时，留意一次想法，分开想想哪些是已知信息、哪些还是猜测；暂时不确定也可以。",
    "lesson-4": "愿意时，按记录中的边界考虑一次替代回应，也可以先观察原做法，不急着行动。",
    "lesson-5": "愿意时，只考虑记录中的第一小步，遇到阻碍可以缩小、暂停或调整；本课没有记录您已执行。",
    "lesson-6": "愿意时，用记录中的依据和新说法回看一次类似想法，仍不确定的地方继续保留。",
    "lesson-7": "愿意时，按自己的舒适程度考虑记录中的小步骤，不舒服可以停下，也可以暂不安排。",
    "lesson-8": "愿意时，在自己约定的时间回看这份计划，保留适用部分，再按实际反馈调整。",
}
LESSON_1_DEMONSTRATION = "先看一个示范：朋友没有回电话，小林想到‘他是不是不愿理我’，感到失落，于是没有再联系。没有回电话是发生的事，‘他是不是不愿理我’是想法，失落是心情，没有再联系是做法。这几部分可能相互影响。"
LESSON_1_GUIDED_EXAMPLE = {
    "story": "小周买菜时，发现常去的摊位今天没开。他心里冒出一句：‘今天买不到想要的菜了。’他有些失望，随后去旁边的摊位看看。",
    "focus_quote": "今天买不到想要的菜了",
    "question": "这里‘今天买不到想要的菜了’属于事情、想法、心情、做法中的哪一部分？",
}
EXAMPLES = {
    "lesson-1": LESSON_1_DEMONSTRATION + "\n\n再换个小例子，一起练一下：" + LESSON_1_GUIDED_EXAMPLE["story"] + "\n\n" + LESSON_1_GUIDED_EXAMPLE["question"] + "可以用日常说法回答，不确定也没关系。",
    "lesson-2": "您和老朋友约好去公园，临出门下雨，安排取消了。有人想‘难得约一次又去不成’，有人想‘下次再约也行’。同一件事，这两种想法可能带来什么不同的心情？",
    "lesson-3": "朋友一天没有回复消息，小林想到‘他肯定嫌我烦’。‘没有回复’是目前知道的事；‘肯定嫌我烦’还需要更多信息。这两句话里，哪句是在推测对方的想法？",
    "lesson-4": "小林因朋友没回消息而失落，想一直不再联系。这样暂时避开尴尬，却也可能失去联系机会。若没有现实危险，他可以先发一句不催促的问候，也可以等合适的时候。考虑替代做法前，需要先看什么？",
    "lesson-5": "请先选择本课想探索的路径：安排一件有意义的小活动，或逐步面对一个没有现实危险的日常回避。可以只整理计划，不必现在执行。",
    "lesson-6": "朋友一天没回复，小林想‘他肯定嫌我烦’。没有回复是已知信息，但之前对方也有忙碌后再回复的情况。‘他可能在忙，我还不知道原因’保留了哪些信息与不确定？",
    "lesson-7": "请先选择梳理一个睡眠习惯，或探索一种让自己舒服的放松方式。可以只讨论、随时调整，不必立即练习。",
    "lesson-8": "小林注意到自己又开始不回消息、取消活动。他不把这当成前功尽弃，而是回看一项可用技能，先做小步骤，需要时找支持。这样一份计划可以包含什么？",
}

SKILLS = {
    "lesson-1": "辨认事情、想法、心情与做法",
    "lesson-2": "辨认事情、想法与心情",
    "lesson-3": "尝试区分已知信息与推断",
    "lesson-4": "检查情绪推动的行为并考虑替代回应", "lesson-5": "整理本人选择路径的小步行动计划",
    "lesson-6": "检查依据并形成更平衡的说法", "lesson-7": "整理睡眠习惯或舒适放松安排",
    "lesson-8": "整理再遇困难时的应对与支持计划",
}
PREDECESSORS = {"lesson-1": (), "lesson-2": ("lesson-1",), "lesson-3": ("lesson-2", "lesson-1"),
    "lesson-4": ("lesson-3", "lesson-2", "lesson-1"), "lesson-5": ("lesson-4", "lesson-3", "lesson-2", "lesson-1"),
    "lesson-6": ("lesson-3", "lesson-2", "lesson-1"), "lesson-7": ("lesson-6", "lesson-5", "lesson-4"),
    "lesson-8": tuple(f"lesson-{number}" for number in range(1, 8))}
PATTERN_LABELS = {"mind_reading": "还没核实，就确定别人怎么想", "catastrophising": "把最坏的可能当成必然", "overgeneralisation": "从一次事情推到所有时候", "all_or_nothing": "只允许全好或全坏"}
PATTERN_CHOICES = {"accepted": "这次像这种情况", "rejected": "这个解释不太符合", "unsure": "暂时不确定", "no_clear_pattern": "没有明显的思维模式"}
MODEL_TOKEN_LIMITS = {f"lesson-{number}": 1200 for number in range(1, 9)}
MODEL_TOKEN_LIMITS["lesson-2"] = 900
PREVIEW_EXAMPLES = {
    "lesson-1": {"learn": "昨晚女儿没有回电话，我想分析这一件事。", "practice": "事情：女儿昨晚没有回电话；想法：她是不是不在乎我；相信程度：6分；心情：有些失落；情绪强度：5分；做法：我没有再打电话"},
    "lesson-2": {"learn": "一个可能失落，另一个可能平静，因为想法不同。", "practice": "事情：女儿昨晚没有回电话；想法：她肯定不在乎我；心情：有些失落"},
    "lesson-3": {"learn": "肯定嫌我烦是在猜测别人的想法，目前还不知道。", "practice": "事情：女儿昨晚没有回电话；想法：她肯定不在乎我；心情：有些失落；线索：我还没有问过她，所以只是猜测"},
}

PATHS = {
    "lesson-5": {
        "activation": {"label": "行为激活：安排有意义的小活动", "action": "choose_activation", "fields": ("situation", "activity_goal", "first_step", "when_where", "barrier_plan", "safety_note"),
            "example": "小林最近减少了喜欢的活动，越待着越提不起劲。他准备先在窗边照料花草两分钟，不要求先变得开心。为什么先把活动缩小会更容易开始？",
            "learn": "不必等心情好才开始，小活动更容易尝试，也可以按情况调整。"},
        "exposure": {"label": "行为暴露：逐步面对日常回避", "action": "choose_exposure", "fields": ("situation", "feared_prediction", "graded_steps", "first_step", "when_where", "barrier_plan", "safety_note"),
            "example": "小林想和熟人打招呼，却担心尴尬。他只考虑安全的日常场景，先从点头、再到一句问候，选择自己愿意的一小步。为什么不用一开始就挑战最难的情形？",
            "learn": "先选本人愿意且安全的小一步，可以慢慢面对，不必一下做最难的。"},
    },
    "lesson-7": {
        "sleep": {"label": "睡眠：梳理习惯与小调整", "action": "choose_sleep", "fields": ("sleep_pattern", "sleep_habit", "first_step", "when_where", "safety_note"),
            "example": "小林睡前反复看时间，越看越着急。他先留意这一习惯，考虑把时钟转开，给自己一个安静的收尾。不要求马上睡着。这个小调整能保证当晚睡好吗？",
            "learn": "不能保证马上睡好，只是先观察习惯，尝试一个舒服的小调整。"},
        "relaxation": {"label": "放松：选择舒适的方式", "action": "choose_relaxation", "fields": ("stress_cue", "relax_method", "first_step", "when_where", "safety_note"),
            "example": "小林紧张时准备看看身边三样东西，感受椅子的支撑，保持自然呼吸。他不用闭眼或憋气，不舒服就停下。放松练习是否必须坚持到完全不紧张？",
            "learn": "不必强求完全不紧张，按舒适程度来，不舒服可以停下。"},
    },
}
INPUT_LABELS = {"situation": "事情", "thought": "想法", "emotion": "心情", "behavior": "做法", "awareness_note": "线索",
    "action_fit": "作用", "alternative_action": "替代", "safety_note": "边界", "activity_goal": "意义", "first_step": "小步",
    "when_where": "安排", "barrier_plan": "阻碍", "feared_prediction": "担心", "graded_steps": "阶梯", "evidence_for": "支持",
    "evidence_against": "不同信息", "balanced_thought": "新说法", "next_step": "下一步", "sleep_pattern": "睡眠", "sleep_habit": "习惯",
    "stress_cue": "信号", "relax_method": "方式", "early_signal": "早期信号", "helpful_skill": "技能", "response_plan": "应对",
    "support_plan": "支持安排", "review_plan": "回看"}
QUESTIONS = {"situation": "当时具体发生了什么？", "thought": "当时脑中最先出现的是哪句话？", "emotion": "当时心里是什么感受？",
    "behavior": "带着这份心情，您当时做了什么，或没有做什么？", "awareness_note": "当时有什么信息让您这样判断？还不确定或没有核实也可以。",
    "action_fit": "原来的做法对您有什么帮助，又带来了什么不方便？", "alternative_action": "在尊重自己和他人边界的前提下，您想考虑什么不同的回应？也可以先不行动。",
    "safety_note": "这一步有哪些需要尊重的边界，什么情况下您会停下或调整？", "activity_goal": "这件小活动对您有什么意义？",
    "first_step": "您愿意考虑的第一小步是什么？也可以先观察、暂不行动。", "when_where": "如果愿意试，您考虑在什么时候、什么地方？",
    "barrier_plan": "如果遇到阻碍，您想怎样缩小、暂停或调整这一步？", "feared_prediction": "想到这件日常小事，您担心会发生什么？",
    "graded_steps": "只考虑没有现实危险的日常情形，您会怎样从容易到困难分成两三个小台阶？", "evidence_for": "有哪些具体信息支持原来的想法？暂时没有也可以。",
    "evidence_against": "还有哪些不同的信息，或目前没有核实的地方？", "balanced_thought": "把这些信息都放进来，您现在愿意怎样说这条想法？不必强求积极。",
    "next_step": "接下来您想怎样核对信息或照顾自己的需要？", "sleep_pattern": "您愿意说说最近注意到的睡眠情况吗？",
    "sleep_habit": "睡前有什么习惯是您想先留意的？", "stress_cue": "什么时候您会注意到自己想放松一下？",
    "relax_method": "哪一种方式让您觉得舒服：看看周围、感受支撑，或您习惯的其他方式？",
    "early_signal": "如果以后又遇到困难，什么小变化能提醒您早点照顾自己？", "helpful_skill": "本课回顾后，您愿意继续使用哪项技能？有的还没试过也可以说明。",
    "response_plan": "看到这个信号后，您希望先做哪一小步？", "support_plan": "自己应对困难时，您想怎样找可信任的人或专业支持？不用写姓名或联系方式。",
    "review_plan": "您想什么时候回看这份计划，按实际情况调整？"}
PREVIEW_RECORDS = {
    "lesson-4": {"situation": "女儿昨晚没有回电话", "emotion": "有些失落", "behavior": "没有再联系", "action_fit": "暂时避开尴尬，但一直不联系让我更孤单", "alternative_action": "先发一句不催促的问候", "safety_note": "尊重她忙碌的时间，不连续催促，也可以等合适的时候"},
    "activation": {"situation": "最近常待在家里，减少了喜欢的活动", "activity_goal": "照料花草让我感到和生活有联系", "first_step": "先在窗边给一盆花看看土壤", "when_where": "明天下午在家里，先留两分钟", "barrier_plan": "累了就缩小到只看看花，也可以另约时间", "safety_note": "选择坐着也能完成的事，不勉强身体"},
    "exposure": {"situation": "见到熟人时担心尴尬，常绕开走", "feared_prediction": "我担心打招呼后对方不回应", "graded_steps": "先点头，再说一句你好，之后再考虑简短聊天", "first_step": "只考虑向熟悉的邻居点一下头", "when_where": "白天在熟悉而安全的楼道，有自然碰面时", "barrier_plan": "觉得太难就先观察，不强迫自己当场做", "safety_note": "只考虑没有现实危险的日常小事，不舒服或不愿意就暂停"},
    "lesson-6": {"situation": "女儿昨晚没有回电话", "thought": "她肯定不在乎我", "emotion": "有些失落", "evidence_for": "昨晚确实没有接到回复", "evidence_against": "以前她忙完会再联系，这次还没有问过原因", "balanced_thought": "我现在还不知道原因，她也可能在忙，我确实想和她联系", "next_step": "找合适的时间问问近况，不急着给关系下结论"},
    "sleep": {"sleep_pattern": "最近睡前有时很着急入睡", "sleep_habit": "躺下后总想反复看时间", "first_step": "先考虑把时钟转向一边，留意自己是否舒服", "when_where": "今晚在卧室睡前，不要求立刻睡着", "safety_note": "只调整一个小习惯，不擅自改变药物，持续困扰时寻求专业帮助"},
    "relaxation": {"stress_cue": "想到明天的安排时，注意到肩膀有点绷紧", "relax_method": "看看身边三样东西，感受椅子的支撑", "first_step": "先坐稳，看看眼前的一样东西，保持自然呼吸", "when_where": "白天在家里舒适的椅子上，按自己的节奏", "safety_note": "不用憋气或闭眼，不舒服就停下，身体不适不简单当成情绪"},
    "lesson-8": {"early_signal": "发现自己连续几天不想回应朋友消息", "helpful_skill": "先分开事情和猜测，再考虑一个小步，效果还需要实际观察", "response_plan": "先写下一件具体事情，看看有哪些信息，再决定是否发一句问候", "support_plan": "可以先找信任的家人聊聊，持续难以应对时寻求专业支持", "review_plan": "下周找一个方便的时间回看，看看哪些适用、哪些需要调整"},
}
PREVIEW_LEARN = {"lesson-4": "先看原来的做法是否有帮助、是否安全，不是所有情绪都要反着做。", "lesson-6": "保留了没回复这个事实，也承认目前还不知道原因，不强求积极。", "lesson-8": "先识别信号，再回看可用技能、小步应对和支持，困难不等于前功尽弃。"}


def path_spec(state: dict) -> dict | None:
    return PATHS.get(state["lesson_id"], {}).get(state.get("path"))


def required_fields(state: dict) -> tuple[str, ...]:
    return (path_spec(state) or {}).get("fields", REQUIRED_FIELDS.get(state["lesson_id"], ()))


def lesson_example(state: dict) -> str:
    return (path_spec(state) or {}).get("example", EXAMPLES[state["lesson_id"]])


def preview_examples(state: dict) -> dict:
    lesson = state["lesson_id"]
    values = PREVIEW_RECORDS.get(state.get("path") or lesson)
    examples = dict(PREVIEW_EXAMPLES.get(lesson, {}))
    if values:
        missing = [key for key in required_fields(state) if key not in state.get("draft_record", {})]
        examples["practice"] = "；".join(f"{INPUT_LABELS[key]}：{values[key]}" for key in missing[:4])
        examples["learn"] = (path_spec(state) or {}).get("learn", PREVIEW_LEARN.get(lesson, ""))
    elif state.get("draft_record") and lesson in PREVIEW_EXAMPLES:
        labels = {label: field for field, label in INPUT_LABELS.items()}
        examples["practice"] = "；".join(part for part in examples["practice"].split("；") if labels.get(part.split("：")[0]) not in state["draft_record"])
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
    return {**examples, "check_in": "这一周还算平稳，大概六分。", "summary": "生活里的例子更容易懂，术语有些没听懂，希望慢一点。"}


def task_step_id(state: dict) -> str:
    """A subtask may span several turns. This identifier is assigned by code."""
    stage = state["stage"]
    from cbt_course_llm_freeform import learning_check
    if learning_check.enabled(state) and (stage == "assessment" or learning_check.retrying(state)):
        attempt, _, question, _ = learning_check.current(state)
        return f"{stage}:{'retry:' if learning_check.retrying(state) else ''}{question['field']}:{attempt['index']}"
    path = state.get("path")
    if stage == "learn" and state["lesson_id"] in PATHS and not path:
        return "learn:choose_path"
    if stage == "practice":
        from cbt_course_llm_freeform.practice_flow import current_field
        missing = current_field(state) or "record"
        return f"practice:{path + ':' if path else ''}{missing}"
    if path:
        return f"{stage}:{path}"
    return {"check_in": "check_in:recent_state", "learn": "learn:example", "review": "review:record", "plan": "plan:choice", "summary": "summary:feedback", "check_feedback": "check_feedback:review", "learning_goal": "learning_goal:confirm"}[stage]


def stage_intro(lesson_id: str, stage: str, *, path: str | None = None) -> str:
    if stage == "check_in":
        return "我们先聊聊最近一周。您可以用几句话说说，也可以用一到十分表示心情；不想评分也没关系。"
    if stage == "learn":
        return lesson_example({"lesson_id": lesson_id, "path": path})
    if stage == "practice":
        if lesson_id == "lesson-1":
            return "接下来用同一件小事练习区分事情、想法、心情和做法，不需要分析得很深。想不起或不愿谈的部分可以先留空，最后一起核对。最近有没有一件愿意聊的小事？先说具体发生了什么就好。"
        if lesson_id == "lesson-7":
            return QUESTIONS["sleep_pattern" if path == "sleep" else "stress_cue"]
        if lesson_id == "lesson-8":
            return QUESTIONS["early_signal"]
        return "现在试试您自己的例子。最近有没有一件愿意聊的小事？先说当时具体发生了什么就好。"
    if stage == "review":
        if lesson_id == "lesson-3":
            return "请核对您的原话与可能的思维习惯。先选择这个解释是否适合，也可以保留不确定或没有明显模式，再确认整份记录。"
        return "我把您的原话整理成了学习记录。请看看是否准确；可以直接告诉我哪里要改。" + ("确认后，我们换个例子做四道小题。" if lesson_id == "lesson-1" else "确认后再选课后安排。")
    if stage == "plan":
        return "记录已按您的确认保存。" + PRACTICE_PLANS[lesson_id] + "您愿意试一次，还是这次不安排？两种选择都可以。"
    if stage == "summary":
        return "今天我们一起完成了一次练习，这代表本次尝试，不代表已经完全掌握。您可以说说哪里有帮助、哪里难懂，也可以直接完成本课。"
    return "本课已结束，您可以在这里回看自己的记录与课后安排。"
