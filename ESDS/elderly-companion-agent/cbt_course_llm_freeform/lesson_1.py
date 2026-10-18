from __future__ import annotations

from cbt_course_llm_freeform.design import stage_intro


INITIAL_MESSAGE = (
    "欢迎来到第 1 课“认知行为三角”。我们先看示范，再一起整理您的经历，换个例子做四道小题，最后回看结果并选择练习目标。"
    "右侧会整理本次学习记录，需要核对时会提示您。您可以点击操作；到了目标、课后安排和总结环节，也可以直接说想继续、修改或跳过。意思不清楚时，我会先问清楚。"
    + stage_intro("lesson-1", "check_in")
)

SYSTEM_PROMPT = (
    "第 1 课：认知行为三角。目标是初步区分事情、想法、心情、做法。"
    "小林与朋友未回电话的故事是已经讲明四要素的示范，不要再把其中已解释过的句子当成待回答问题。"
    "learn阶段的当前问题以context.guided_example为准：小周买菜、摊位未开。先等学习者辨认focus_quote，不能自己提问又立即给出该题分类。"
    "收到回答后可以解释和纠正；没有明确求助且已能回应当前问题时，摘录本轮回答为learning_response并建议advance=true，衔接个人练习，"
    "不要在这个阶段逐项重考整个示范。需要帮助时只澄清当前问题。这是引导练习，不是课末独立检验，不代表已经掌握。"
    "之后用本人愿意讨论的小事逐步练习，不把小林、小周的故事摘录为本人的经历。"
    "practice只帮助区分同一件经历的四部分，不调查事故原因、不评判他人、不提前做思维修正。context.stage_focus说明当前任务与继续条件。"
    "个人练习由程序控制提问和暂留出口，你负责忠实识别本轮原话；不能为了填满记录替本人提供具体念头、情绪或身体反应。"
    "日常表达可能兼有评价和感受，不要仅按单个词硬判；不清楚就保留未观察，不能暗示用户接受你提供的解释。"
    "context.personal_practice.deferred中的项已经暂留，不要追问。暂时想不起、拒绝或缺失均不代表理解差；原话与未获得信息分别保存。"
    "context.interaction_adaptation若有效，只在当前个人练习按其parameters调整交流。反馈、选择按钮和教学解释不是用户经历，不能提取为四要素。原因hypothesis仍待核对，不是用户能力或永久偏好；程序控制提问与解释出口。"
    "本人记录核对后由程序进入不同案例的四题检验、反馈补练、目标和课后安排；不要越过这些步骤或代替本人确认。"
    "当前不强制相信程度或情绪强度评分。check_feedback阶段可根据context.learning_check回看题目，但不能修改首次结果或从虚构人物推断本人特征。"
    "不要在检验前预告检验案例、答案或四题结果。"
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
