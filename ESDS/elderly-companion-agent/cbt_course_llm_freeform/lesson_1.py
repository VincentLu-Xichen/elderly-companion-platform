from __future__ import annotations


INITIAL_MESSAGE = (
    "你好，欢迎来到第 1 课“认知行为三角”。整套课程共有 8 课，围绕认知调整和行为练习展开。"
    "本课程用于学习与课堂研究，不代替心理治疗、医疗诊断或紧急救援。\n\n"
    "开始前，请用 1—10 分评价自己上周的整体状态：1 分代表非常糟糕，10 分代表非常好。"
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
        "caption": "想法是我们对事情的即时解读。",
    },
    "emotion_vocabulary": {
        "kind": "image",
        "src": "/cbt-course-assets/lesson_1/emotion-vocabulary.svg",
        "alt": "常见消极情绪词汇",
        "caption": "一时找不到合适的词时，可以参考这些感受。",
    },
    "practice_scenario": {
        "kind": "image",
        "src": "/cbt-course-assets/lesson_1/practice-scenario.svg",
        "alt": "认知行为四要素练习材料",
        "caption": "请依次找出情境、想法、情绪和行为。",
    },
    "practice_answers": {
        "kind": "image",
        "src": "/cbt-course-assets/lesson_1/practice-answers.svg",
        "alt": "认知行为四要素练习答案",
        "caption": "四要素答案回顾",
    },
}

ATTACHMENT_MARKER_PREFIX = "CBT_ATTACHMENT"
COMPLETION_MARKER = "[[CBT_COURSE_COMPLETE]]"
