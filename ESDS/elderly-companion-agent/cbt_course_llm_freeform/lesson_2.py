from __future__ import annotations

from cbt_course_llm_freeform.design import stage_intro
from cbt_course_llm_freeform.teacher_flow import MOOD_QUESTION

INITIAL_MESSAGE = (
    "欢迎来到第 2 课“捕捉我的思维”。今天回顾课后练习，学习捕捉自动思维，并用三栏表整理情境、想法和情绪。" + MOOD_QUESTION
)

SYSTEM_PROMPT = "第 2 课：捕捉我的思维。按老师原稿先进行上周1—10分心境检查，再回顾课后记录及三个概念，通过雨天情境和小雨的对照学习捕捉自动思维，观察同一情境中的不同解释与感受。帮助说明自动思维的即时性、可能不易觉察以及如何留意它，不能用不断分类提问代替心理教育。之后练习情境、自动思维、情绪三栏，记录明确情绪强度并共同核对关系。允许不同意、无新感想和自愿出口，不强迫乐观、认同单一因果或宣称情绪已改善。"

HARD_SAFETY_SIGNALS = ("想死", "不想活", "自杀", "结束生命", "伤害自己", "伤害别人")
SAFETY_MESSAGE = (
    "我注意到您可能正处在危险或非常难受的状态，这节课程先暂停。"
    "请立刻联系身边可信任、能够到场的人或当地紧急医疗服务，不要独自承担。"
)
