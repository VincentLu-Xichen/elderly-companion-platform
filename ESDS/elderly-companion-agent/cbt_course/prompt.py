from __future__ import annotations

import json
from typing import Any


COURSE_TUTOR_SYSTEM_PROMPT = """
你是“认知行为练习课”的中文课程理解助手。后端课程引擎已经决定当前步骤，你不能决定课程顺序，也不能提出下一道问题。

你的任务只有四项：
1. 根据当前步骤规则判断用户是否回答了问题。
2. 尽量原样提取用户提供的核心内容，不补充用户没有说过的事实。
3. 生成一句简短、自然、不过度赞美的回应；不得在回应中提出新问题。
4. 识别明显的自伤、紧急身体危险或诈骗风险。

不要诊断，不给药物建议，不承诺疗效，不使用说教式口吻。只输出符合给定 JSON Schema 的 JSON。
""".strip()


def build_course_prompt(
    *,
    step: str,
    rubric: str,
    allowed_outcomes: list[str],
    content: str,
    relevant_state: dict[str, Any],
) -> str:
    return (
        f"当前步骤：{step}\n"
        f"判断规则：{rubric}\n"
        f"允许的 outcome：{json.dumps(allowed_outcomes, ensure_ascii=False)}\n"
        f"已有必要信息：{json.dumps(relevant_state, ensure_ascii=False)}\n"
        f"用户本轮输入：{content}\n"
        "extracted_values.text 应尽量使用用户原文；没有可提取内容时返回空字符串。"
    )
