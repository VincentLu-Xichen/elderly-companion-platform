from __future__ import annotations

from cbt_course_llm_freeform.design import stage_intro

INITIAL_MESSAGE = (
    "欢迎来到第 2 课“看见情境、想法和心情”。本课将留下一份由您确认的三栏记录。"
    + stage_intro("lesson-2", "check_in")
)

SYSTEM_PROMPT = "第 2 课：看见情境、想法和心情。目标是练习区分事实与解释。签到时可询问上课练习，没做或记不清也可以继续。示例：和老朋友约好去公园却下雨，有人失望、有人平静，探讨不同想法与心情的联系。不是要求乐观，也不否认现实困难。再完成本人事情、想法、心情三栏记录，逐项确认含义。"

HARD_SAFETY_SIGNALS = ("想死", "不想活", "自杀", "结束生命", "伤害自己", "伤害别人")
SAFETY_MESSAGE = (
    "我注意到您可能正处在危险或非常难受的状态，这节课程先暂停。"
    "请立刻联系身边可信任、能够到场的人或当地紧急医疗服务，不要独自承担。"
)
