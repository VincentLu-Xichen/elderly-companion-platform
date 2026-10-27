"""Lesson-one output policy; state transitions remain owned by runtime."""

import copy
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

VERSION = "lesson1-natural/1"
STATE_VERSION = "classroom-dialogue/1"


class TeachingTurn(BaseModel):
    """A sourced teaching action, not a learner trait or a new model call."""

    model_config = ConfigDict(extra="forbid", strict=True)
    kind: Literal[
        "answer", "concept_question", "conversation", "invite_return",
        "decline_return", "resume_course",
    ]
    source_message_id: str = Field(min_length=1, max_length=80)
    quote: str = Field(min_length=1, max_length=500)
    attempted_field: Literal[
        "situation", "thought", "thought_belief", "emotion", "emotion_intensity", "behavior"
    ] | None = None


TURN_PROMPT = """
CLASSROOM_DIALOGUE/1
普通教学非learning_request轮用turn_intent说明当前交流动作，含kind、最新learner的source_message_id及连续原话quote；learning_request非空时turn_intent=null，不重复提交动作。它是本轮行动依据，不是心理结论；不能只凭自己觉得用户情绪好转就写resume_course。
answer：本人正在回答练习、提供或纠正当前案例；允许按原话整理所有已表达字段。概念问题与回答并存时可整理明确答案，但不要急着补问评分。
attempted_field只在本人确实尝试回答某一记录项目时填写该项目；只提供别项信息、纠正或交流时可null。不能因为pending_task建议评分，就把尚未邀请或本人正在问概念的一轮标成评分作答。
concept_question：本轮主要在问概念、比较或提出与学习有关的思考，先解释具体疑问。没有新的本人答案时observations=[]，不把求助当未回答或催用户打分，不必问下一题。
conversation：用户联想其他事情、仍需要表达或只需要被听见。具体回应即可，可短可长、可不问；observations=[]、assessment.signals=[]、advance=false、case_options=[]、next_practice_field=null、attempted_field=null，不混写原案例，也不擅自恢复课程。明确只想倾诉或暂不评分时仍用已有learning_request，不用这项绕过其范围校验。
交流状态优先于课程待办：不主动整理或改写练习记录，不分析四要素、不催评分或核对，不以共情开场后马上执行pending_task。用户在交流中说“我只是想念她，并不是认为她一定不在乎我”时，先回应其澄清，不据此推断当时的原记录错误或自动改thought；不能确定是现在的新看法还是当时想法的纠正时，可以只问清这一点，不提交记录或correction信号。明确要求回到原练习修改记录才用resume_course；不明确授权时先澄清，不用answer偷偷恢复。当前诉求来自本轮，持续交流状态来自上下文，不复用旧请求的quote。
invite_return：结合当前表达已告一段落、用户明确说好一些等新依据，询问本人是否愿意回到保存的学习位置；必须表达选择并等待答复，不是宣布“那我们就回到刚才那件事”或直接开始下一题。情绪缓和/说完只支持提出邀请，不等于本人同意。可说“您愿意继续刚才的练习吗”，不在邀请后附上评分、核对任务或开始整理四要素。无需等10轮或20轮。observations=[]、advance=false；已有待答邀请时不重复问，用户暂不想返回时继续回应，不把每轮交流都变成邀请。
decline_return：本轮明确表示暂不返回课程，包括主动提出暂不返回或拒绝已有邀请，继续交流，observations=[]。没有pending邀请也可表达此意愿，不虚构此前邀请。尊重清楚的暂不返回，不需要强烈抗拒。
resume_course：本人明确愿意继续学习，或明确回答先前返回邀请。主动回到原练习给出答案也可表达继续意愿，不能把其他事件当成原题回答。quote摘本人继续意愿的完整分句，不能用情绪好转、引语、他人的同意或截断否定冒充；可以仍然难过。只恢复原进度，不代确认、不自动完成、不撤销评分暂留；只说继续不等于愿意重新评分，reply不重新索取deferred_fields中的项目。若本轮还明确给出练习答案，可同时提取该答案。
context.classroom_dialogue保存交流状态、返回点和邀请记录；context.pending_task仅描述教学待办、对象、量尺，不是本轮必须执行的台词。先解决本轮诉求，适合教学才组织下一步。非作答轮advance=false、case_options=[]，不能同时提交新记录或修改评分；next_practice_field可留null，非空也只是待办元数据，不意味着必须问该项。
""".strip()


def new_flow():
    return {"version": STATE_VERSION, "mode": "course", "return_to": None, "invitation": None}


def context(state):
    return copy.deepcopy(state.get("classroom_dialogue") or new_flow())


def guard_conversation_records(state, decision, latest, faithful):
    """Reject optional writes during a sourced ongoing conversation, with audit.

    This does not reinterpret an answer or repair sources. The model's explicit
    conversation action wins over its contradictory optional record candidates.
    Other illegal actions still reach the existing strict validators.
    """
    turn = decision.turn_intent
    if (context(state)["mode"] != "conversation" or turn is None
        or turn.kind != "conversation" or not decision.observations):
        return decision, None
    if decision.advance or decision.case_options or turn.attempted_field is not None:
        return decision, None
    if turn.source_message_id != latest.get("id") or not faithful(latest["content"], turn.quote):
        raise ValueError("Teaching turn has no faithful current learner source")
    for item in decision.observations:
        if item.source_message_id != latest.get("id") or not faithful(latest["content"], item.value):
            raise ValueError("Conversation record candidate has no faithful current learner source")
    for item in decision.assessment.signals:
        if item.source_message_id != latest.get("id") or not faithful(latest["content"], item.quote):
            raise ValueError("Conversation signal has no faithful current learner source")
    if re.search(r"(?:已|已经|帮您|为您|我把|我将|我会|替您).{0,14}(?:修改|改写|更正|更新|保存|记下|记入|记录)|(?:改为|改成|已确认|已完成)", decision.reply):
        raise ValueError("Conversation reply cannot claim a rejected record write")
    audit = {"action": "reject_conversation_record_candidates",
             "source_message_id": latest["id"],
             "rejected_observations": [item.model_dump() for item in decision.observations],
             "rejected_signals": [item.model_dump() for item in decision.assessment.signals]}
    cleaned = decision.model_copy(update={
        "observations": [], "assessment": decision.assessment.model_copy(update={"signals": []}),
        "next_practice_field": None,
    })
    return cleaned, audit


def resolve_turn(decision, latest, faithful):
    """Validate model-selected meaning; old captured JSON remains replayable."""
    turn = decision.turn_intent
    origin = "model"
    if turn is None:
        # Old JSON already carries a source-checked confusion signal. Do not
        # silently reinterpret arbitrary empty observations as conversation.
        confusion = next((item for item in decision.assessment.signals
                          if item.kind == "confusion"
                          and item.source_message_id == latest.get("id")
                          and faithful(latest["content"], item.quote)), None)
        kind = ("concept_question" if confusion and not decision.observations else "answer")
        if decision.practice_origin != "current_case" and not decision.observations:
            kind = "conversation"
        turn = TeachingTurn(kind=kind, source_message_id=latest["id"],
                            quote=confusion.quote if kind == "concept_question" else latest["content"][:500])
        origin = "legacy_signal" if kind == "concept_question" else "legacy_answer"
    if turn.source_message_id != latest.get("id") or not faithful(latest["content"], turn.quote):
        raise ValueError("Teaching turn has no faithful current learner source")
    if turn.kind not in {"answer", "resume_course"} and (
        getattr(decision, "observations", []) or getattr(decision, "advance", False)
        or getattr(decision, "case_options", []) or turn.attempted_field
    ):
        raise ValueError("A non-answer turn cannot update learner records or advance the lesson")
    return {**turn.model_dump(), "origin": origin}


def apply_turn(state, turn, latest, *, answer_evidence=False):
    """Keep invitations separate from consent and retain the actual return point."""
    flow = context(state)
    kind = turn["kind"]
    invitation = flow.get("invitation") or {}
    if kind in {"conversation", "invite_return", "decline_return"}:
        if not flow.get("return_to"):
            flow["return_to"] = {"stage": state["stage"], "case_id": state["case_id"]}
        flow["mode"] = "conversation"
    if kind == "invite_return":
        if invitation.get("status") == "pending":
            raise ValueError("A return invitation is already awaiting the learner")
        flow["invitation"] = {"status": "pending", "source_message_id": latest["id"],
                              "quote": turn["quote"]}
    elif kind == "decline_return":
        if invitation.get("status") == "pending":
            flow["invitation"] = {**invitation, "status": "declined",
                                  "answered_by": latest["id"], "answer_quote": turn["quote"]}
        # A learner may proactively decline returning without an invitation.
        # Keep invitation history truthful and record that separate preference.
        flow["return_preference"] = {"status": "not_now",
                                     "source_message_id": latest["id"], "quote": turn["quote"]}
    elif kind == "resume_course":
        if flow["mode"] != "conversation":
            raise ValueError("The lesson is not in a conversational detour")
        expected = {"stage": state["stage"], "case_id": state["case_id"]}
        if flow.get("return_to") != expected:
            raise ValueError("The saved lesson return point is no longer current")
        quote = turn["quote"]
        # These only reject absent/contradictory authorization candidates; they
        # never create consent. Meaning is proposed by the existing teacher.
        prefix = latest["content"][:latest["content"].find(quote)][-20:]
        if re.search(r"(?:不想|不愿|不要|先不|暂不|朋友说|别人说|他说|她说)[^，,。！？!?]{0,12}$", prefix) or re.search(
            r"(?:不想|不愿|不要|先不|暂不).{0,8}(?:继续|返回|回到|恢复|学习|练习)|(?:朋友|别人|他说|她说).{0,5}(?:说|愿意|继续)", quote
        ):
            raise ValueError("Return authorization is negated or reported")
        affirmative = quote.strip("。！!，, ") in {"好", "好的", "可以", "行", "愿意", "好啊", "可以的"}
        if not answer_evidence and not re.search(r"继续|接着|返回|回到|恢复|学习|练习|接下来|看看|分清|分析|解释|整理|了解|讲讲|修改|更正|纠正|改为|改成", quote) and not (
            invitation.get("status") == "pending" and affirmative
        ):
            raise ValueError("Feeling better alone does not authorize returning to the lesson")
        flow["mode"] = "course"
        flow.pop("return_preference", None)
        flow["return_to"] = None
        if invitation:
            flow["invitation"] = {**invitation, "status": "accepted", "answered_by": latest["id"],
                                  "answer_quote": quote}
    elif kind == "answer" and flow["mode"] == "conversation":
        raise ValueError("A conversational detour needs sourced willingness before recording answers")
    state["classroom_dialogue"] = flow
    state["latest_teaching_turn"] = copy.deepcopy(turn)


def enter_listening(state, latest):
    flow = state.setdefault("classroom_dialogue", new_flow())
    if not flow.get("return_to"):
        flow["return_to"] = {"stage": state["stage"], "case_id": state["case_id"]}
    flow["mode"] = "conversation"
    if (flow.get("invitation") or {}).get("status") == "pending":
        flow["invitation"].update(status="deferred", answered_by=latest["id"],
                                  answer_quote=latest["content"][:500])


def resume_from_request(state, latest, quote):
    if context(state)["mode"] == "conversation":
        apply_turn(state, {"kind": "resume_course", "quote": quote,
                          "source_message_id": latest["id"], "origin": "learning_request"}, latest)


def reset_after_control(state, action):
    if enabled(state) and action != "pause":
        flow = state.setdefault("classroom_dialogue", new_flow())
        flow.update(mode="course", return_to=None, invitation=None)


def enabled(state):
    return (
        state.get("lesson_id") == "lesson-1"
        and "blueprint" in state
        and state.get("dialogue_policy") == VERSION
    )


def confirms_record(state, text):
    # Only an answer to the current record check, never general authorization.
    return (
        enabled(state)
        and state.get("stage") == "review"
        and bool(
            re.fullmatch(
                r"(?:准确|准确的|是准确的|没问题|没有问题|核对无误|记录准确|记录无误|确认这份记录)[。.!！\s]*",
                text.strip(),
            )
        )
    )


def navigation_reply(text, receipt):
    # The model acknowledges intentions before execution; only the receipt may
    # report a completed write/control. Preserve the receipt on unsafe claims.
    if not text or any(
        word in text
        for word in (
            "已保存",
            "已确认",
            "已完成",
            "已修改",
            "已经保存",
            "已经确认",
            "已经完成",
            "已经修改",
            "本课结束",
        )
    ):
        return receipt
    return text.strip()
