"""Model interprets speech; the runtime owns all stage transitions."""
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

VERSION = "course-navigation/1"

STAGE_INSTRUCTIONS = {
    "learning_goal": """本轮在【练习目标】。逐项检查最新消息是否同时表达了目标选择与课后练习选择，不要只读前半句。
明确不设目标 -> skip_learning_goal；有草稿且明确确认 -> confirm_learning_goal。
真正提出训练方向 -> intent=goal，保留原话待确认；仅说完成了/好了 -> clarify，不当目标内容也不当同意。
若同一句还明确不安排课后练习，必须在目标动作后追加 decline_practice；若明确愿安排则追加 accept_practice。
例如“目标先不设，也不安排课后练习，直接总结吧”必须 actions=[skip_learning_goal, decline_practice]，不能只跳过目标。
只有表达目标选择、未表达课后选择时，才只输出一个目标动作。clarify 只问确认/暂不设目标，不代选后续环节。""",
    "plan": """本轮在【课后安排】，目标已处理，禁止重新询问是否设置目标。
明确愿安排 -> accept_practice；明确不安排 -> decline_practice。完成了/继续吧含糊时，clarify只问是否安排课后练习。
此阶段不得 finish；想直接总结但没表达练习选择时也先澄清练习选择。""",
    "summary": """本轮在【本课总结】，目标与课后安排已处理，禁止倒退询问它们。
明确结束本课/完成本课/没有补充结束吧 -> finish；仅要看总结不等于结束，不推断生活练习已执行。
普通反馈不能当完成，可简短回应并询问是否结束本课。""",
}


class RequestedAction(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    action: Literal["skip_learning_goal", "confirm_learning_goal", "accept_practice", "decline_practice", "finish"]
    source_message_id: str = Field(min_length=1, max_length=80)
    quote: str = Field(min_length=1, max_length=500)


class GoalUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    index: int = Field(ge=1, le=5)
    value: str = Field(min_length=1, max_length=500)


class NavigationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    intent: Literal["goal", "actions", "clarify"]
    actions: list[RequestedAction] = Field(default_factory=list, max_length=2)
    reply: str = Field(default="", max_length=500)
    goal_items: list[str] = Field(default_factory=list, max_length=10)
    goal_level: Literal["direction", "concrete"] = "concrete"
    goal_updates: list[GoalUpdate] = Field(default_factory=list, max_length=5)





def validate(decision, state, latest):
    if decision.intent != "goal" and (decision.goal_items or decision.goal_updates):
        raise ValueError("Goal data does not match navigation intent")
    if decision.intent == "clarify" and any(word in decision.reply for word in ("已记录", "已经记录", "已修改", "已经修改", "已保存", "已确认", "改好了", "记下了")):
        raise ValueError("Clarification cannot claim an unperformed update")
    if decision.intent != "actions":
        from cbt_course_llm_freeform import blueprint
        if decision.actions or (decision.intent == "goal" and state["stage"] != "learning_goal" and not (blueprint.enabled(state) and state["stage"] in {"plan", "summary"})):
            raise ValueError("Navigation intent does not match stage")
        return
    if not decision.actions:
        raise ValueError("No requested actions")
    stage = state["stage"]
    for item in decision.actions:
        if item.source_message_id != latest["id"] or item.quote not in latest["content"]:
            raise ValueError("Navigation evidence mismatch")
        allowed = {"learning_goal": {"skip_learning_goal", "confirm_learning_goal"},
                   "plan": {"accept_practice", "decline_practice"}, "summary": {"finish"}}.get(stage, set())
        if item.action not in allowed or (item.action == "finish" and state["stage"] != "summary"):
            raise ValueError("Navigation action outside allowed stage")
        if item.action == "confirm_learning_goal" and not state.get("learning_goal_draft"):
            raise ValueError("No goal draft to confirm")
        stage = {"learning_goal": "plan", "plan": "summary", "summary": "completed"}[stage]
