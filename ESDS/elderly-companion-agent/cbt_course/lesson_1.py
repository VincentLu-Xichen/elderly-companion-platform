from __future__ import annotations

from typing import Any


STEP_ORDER = [
    "mood",
    "problem",
    "situation",
    "thought",
    "thought_belief",
    "emotion",
    "emotion_intensity",
    "behavior",
    "reflection",
    "quiz_situation",
    "quiz_thought",
    "quiz_emotion",
    "quiz_behavior",
    "goal",
    "completed_idle",
]


STEP_PHASE = {
    "mood": "心境检查",
    "problem": "我的案例",
    "situation": "我的案例",
    "thought": "我的案例",
    "thought_belief": "我的案例",
    "emotion": "我的案例",
    "emotion_intensity": "我的案例",
    "behavior": "认知行为模型",
    "reflection": "认知行为模型",
    "quiz_situation": "概念练习",
    "quiz_thought": "概念练习",
    "quiz_emotion": "概念练习",
    "quiz_behavior": "概念练习",
    "goal": "目标与课后练习",
    "completed_idle": "课程已完成",
    "diary_situation": "四要素日记",
    "diary_thought": "四要素日记",
    "diary_emotion": "四要素日记",
    "diary_behavior": "四要素日记",
}


INITIAL_MESSAGE = (
    "你好，欢迎来到第 1 课“认知行为三角”。整套课程共有 8 课，会从理解想法与行动开始，"
    "一步步练习更清楚地看见自己的经历。这是一项学习与研究工具，不代替心理治疗、医疗诊断或紧急救援。\n\n"
    "开始前，我想先大致了解一下你上周过得怎么样。请用 1—10 分评价整体状态："
    "1 分代表非常糟糕，10 分代表非常好。直接回复一个分数就可以。"
)


STATIC_ATTACHMENTS = {
    "course_overview": {
        "kind": "image",
        "src": "/cbt-course-assets/lesson_1/course-overview.svg",
        "alt": "八次课程内容总览",
        "caption": "八次课程内容总览",
    },
    "thought_example": {
        "kind": "image",
        "src": "/cbt-course-assets/lesson_1/thought-example.svg",
        "alt": "情境与想法的区分示例",
        "caption": "想法是我们对事情的即时解读，并不等同于已经确认的事实。",
    },
    "emotion_vocabulary": {
        "kind": "image",
        "src": "/cbt-course-assets/lesson_1/emotion-vocabulary.svg",
        "alt": "常见消极情绪词汇",
        "caption": "如果一时找不到合适的词，可以参考这些感受。",
    },
    "practice_scenario": {
        "kind": "image",
        "src": "/cbt-course-assets/lesson_1/practice-scenario.svg",
        "alt": "认知行为四要素练习材料",
        "caption": "请阅读材料，接下来依次找出情境、想法、情绪和行为。",
    },
    "practice_answers": {
        "kind": "image",
        "src": "/cbt-course-assets/lesson_1/practice-answers.svg",
        "alt": "认知行为四要素练习答案",
        "caption": "四要素答案回顾",
    },
}


MODEL_STEP_RULES: dict[str, dict[str, Any]] = {
    "problem": {
        "outcomes": ["one_event", "multiple_events", "no_clear_event"],
        "rubric": (
            "判断用户是否描述了一件具体困扰事件。若有多件未选择，返回 multiple_events；"
            "若没有可识别事件，返回 no_clear_event；只有一件或明确选定一件时返回 one_event。"
        ),
    },
    "situation": {
        "outcomes": ["valid_answer", "no_clear_answer"],
        "rubric": "判断是否说明了可观察的时间、地点、人物或发生的事情，而不是只说感受或推测。",
    },
    "thought": {
        "outcomes": ["valid_answer", "no_clear_answer"],
        "rubric": "判断是否表达了当时脑中出现的解释、判断、预测或一句内心话。",
    },
    "emotion": {
        "outcomes": ["valid_answer", "no_clear_answer"],
        "rubric": "判断是否表达了具体情绪或感受，例如紧张、难过、担心、生气、孤独。",
    },
    "behavior": {
        "outcomes": ["valid_answer", "no_clear_answer"],
        "rubric": "判断是否表达了具体做了什么、没有做什么、回避了什么或采取了什么行动。",
    },
    "reflection": {
        "outcomes": ["valid_answer", "no_clear_answer"],
        "rubric": "判断用户是否分享了新的理解、感受；不知道或暂时没有也属于 no_clear_answer。",
    },
    "quiz_situation": {
        "outcomes": ["correct", "incorrect"],
        "rubric": "正确答案需覆盖：别人和我说话或打招呼时，我没有想到合适的话。",
    },
    "quiz_thought": {
        "outcomes": ["correct", "incorrect"],
        "rubric": "正确答案需覆盖：不回应会显得不礼貌或没兴趣聊天，并可能影响关系。",
    },
    "quiz_emotion": {
        "outcomes": ["correct", "incorrect"],
        "rubric": "正确答案是紧张。",
    },
    "quiz_behavior": {
        "outcomes": ["correct", "incorrect"],
        "rubric": "正确答案需覆盖：拼命、努力或不停地想和别人说话。",
    },
    "goal": {
        "outcomes": ["valid_answer", "no_clear_answer"],
        "rubric": "判断是否表达了希望在课程后改善的生活、情绪、关系或行动方向。",
    },
    "completed_idle": {
        "outcomes": ["start_diary", "not_start_diary"],
        "rubric": "判断用户是否想开始、继续或记录一篇四要素日记。",
    },
    "diary_situation": {
        "outcomes": ["valid_answer", "no_clear_answer"],
        "rubric": "判断是否说明了一件具体发生的事情或情境。",
    },
    "diary_thought": {
        "outcomes": ["valid_answer", "no_clear_answer"],
        "rubric": "判断是否写出了当时脑中的想法、判断或预测。",
    },
    "diary_emotion": {
        "outcomes": ["valid_answer", "no_clear_answer"],
        "rubric": "判断是否写出了具体情绪或感受。",
    },
    "diary_behavior": {
        "outcomes": ["valid_answer", "no_clear_answer"],
        "rubric": "判断是否写出了具体行为或行动。",
    },
}
