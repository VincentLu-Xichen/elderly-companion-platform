"""Local learning requests, independent of style feedback and disclosure consent."""
from __future__ import annotations
import copy
import re
from typing import Literal
import uuid
from pydantic import BaseModel, ConfigDict, Field
from cbt_course_llm_freeform.interaction import InteractionReflection, VERSION

class TeachingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    mode: Literal["listen", "continue", "pause_lesson"]
    deferred_rating_fields: list[Literal["thought_belief", "emotion_intensity"]] = Field(default_factory=list, max_length=2)
    source_message_id: str = Field(min_length=1, max_length=80)
    quote: str = Field(min_length=1, max_length=500)

class LearningInteraction(InteractionReflection):
    learning_request: TeachingRequest | None = None

PROMPT = """
第一课learn/practice/review：学习请求与讲法评价是两件事。普通教学在顶层learning_request表达本轮学习请求，不要为它编造interaction风格反思；普通回答/概念问题learning_request=null。已有辅助判读使用其learning_request字段，含义相同。
请求只含mode、deferred_rating_fields、source_message_id、quote四项，不需要心理解释或风格结论。
mode=listen：本轮主要在倾诉、想被听见或缓一缓，尚未明确停止整课。先具体回应，不提问，不催核对，不说已暂停课程；不分析四要素、不主动整理或改写练习记录，不因pending_task未完成就附带课程任务。普通难过不等于拒绝或心理结论。
mode=continue：本人想继续理解/分析，但明确暂不评分；可直接用recorded_fields解释想法与事实等当前概念，不催核对别的部分。普通练习回答不用这个请求。
mode=pause_lesson：本人明确要求停止这节课/今天不继续课程，才暂停整课。“先听我说”“先别评分”“听不进去，让我缓一会儿”不足以授权整课暂停。否定、引语和转述不是本人请求；“不是要停课，只先听我说”可以listen。
deferred_rating_fields独立于mode：未明确拒绝评分=[]；只拒绝相信程度=[thought_belief]；只拒绝情绪强度=[emotion_intensity]；泛指本次评分=[thought_belief,emotion_intensity]。即使同时想倾诉，listen也必须列出明确拒绝的量尺。没有当期评分任务时留[]。pause_lesson时[]。不升级为停止整例、永久偏好或个人经历边界。
quote连续摘录本轮完整依据，保留否定、转述和范围；source_message_id必须为最新learner。quote是原文证据，不是语义解释：逐字复制最新learner的text中一个连续片段，不润色、不概括、不替换同义词、不拼接分散句子、不复制历史请求。输出前核对quote在最新text中逐字存在，source_message_id与该条id一致；无合适的当前请求依据则learning_request=null，不用旧请求补齐。交流状态可以延续，历史请求不应冒充本轮新请求。
例如最新text为“我其实很想她，以前经常联系，现在少了，我有些不适应。”，不得引用历史“只想说说”，也不得将quote改写为“我需要倾诉”。若判为本轮listen，引用当前连续原话；若仅延续交流，用conversation并保持learning_request=null。程序只执行此来源化请求，不从风格verdict推出动作。若在辅助判读报告请求，personal_intent=none,task_action=continue，verdict仍只描述是否针对Agent讲法，未评价可not_feedback；follow_up等风格字段不代表课程暂停。
请求轮：reply自然回应/讲解，observations=[]，advance=false,next_practice_field=null,interaction=null（普通教学）。不重复摘录旧记录，不能在observations引用seed或其他历史ID。即使本人说愿意听概念但暂不评分，引用旧句子解释也不算新证据；直接在reply讲，observations仍[]。真正新回答/纠正由普通教学轮校验。
程序校验并执行真实暂停状态，reply由模型自然承接本次选择，不自行声称记录已保存/已确认或本课已完成。listen与pause_lesson不提问；continue也可不提问。不把本轮请求自动作为后续偏好，下一轮本人主动继续就照顾新的诉求。明确抱怨持续追问并要求回顾原例时仍用原interaction停问协议；拒绝个人经历、长期边界及检验规则保留，不用learning_request替代。
""".strip()

def enabled(state):
    return state.get("lesson_id") == "lesson-1" and bool(state.get("blueprint")) and state.get("stage") in {"learn", "practice", "review"}

def apply(state, request, latest, reply):
    """Model interprets meaning; program checks provenance and legal scope."""
    from cbt_course_llm_freeform import dialogue

    fields, mode = request["deferred_rating_fields"], request["mode"]
    quote = request["quote"]
    if request["source_message_id"] != latest.get("id"):
        raise ValueError("Learning request has no faithful current source: message id mismatch")
    if not quote or quote not in latest.get("content", ""):
        raise ValueError("Learning request has no faithful current source: quote is not current verbatim text")
    prefix = latest["content"][:latest["content"].find(quote)][-8:]
    if re.search(r"(?:没有|不是|并非|不觉得|没觉得)(?:很|太|觉得|是)?$", prefix):
        raise ValueError("Learning request quote omitted a negation")
    if (not enabled(state) or len(fields) != len(set(fields))
        or mode == "continue" and not fields
        or fields and state["stage"] != "practice" and mode != "pause_lesson"):
        raise ValueError("Learning request exceeds current task scope")
    if any(mark in reply for mark in ("[[", "已完成本课", "已经完成课程", "已确认记录", "本课已完成", "课程已完成", "已确认保存", "本课结束", "已经完全掌握")) or mode in {"listen", "pause_lesson"} and any(mark in reply for mark in ("？", "?")):
        raise ValueError("Learning request response exceeds its authority")
    guarded_request = copy.deepcopy(request)
    if mode == "pause_lesson" and fields:
        # Pause authorizes only pausing. Extra scale proposals neither change
        # existing scores/deferrals nor block an independently valid pause.
        guarded_request.update(deferred_rating_fields=[], rejected_rating_fields=fields,
                               action_guard="pause_does_not_change_rating_scope")
        fields = []
    if fields and not re.search(
        r"评分|打分|分数|几分|强度|相信程度|信念|量表|量尺|数字|数值|(?:这|那|两|当前).{0,4}(?:项|个)|不想(?:答|回答)|先不(?:答|说)|空着|暂留|略过|跳过|不回答",
        latest["content"],
    ):
        # Absence of even a refusal/scale candidate cannot authorize withholding.
        # This rule only rejects a proposed action; matches never create refusal
        # or a psychological conclusion. The model still decides meaning/scope.
        if mode != "listen":
            raise ValueError("Rating refusal lacks a current candidate source")
        guarded_request.update(deferred_rating_fields=[], rejected_rating_fields=fields,
                               action_guard="no_rating_refusal_candidate")
        fields = []
    if mode == "listen":
        dialogue.enter_listening(state, latest)
    elif mode == "continue":
        dialogue.resume_from_request(state, latest, quote)
    for field in fields:
        if field not in state["blueprint"]["ratings"]:
            state["practice_flow"]["deferred"][field] = {"status": "withheld", "source_message_ids": [latest["id"]]}
    if mode == "pause_lesson":
        state["paused"] = True
    memory = {**guarded_request, "id": str(uuid.uuid4()), "kind": "local_learning_request",
              "schema_version": VERSION, "lesson_id": state["lesson_id"], "scope": "lesson",
              "status": "observed", "applied_action": mode, "effect": "not_measured"}
    # Existing independent encrypted save path; observed notes are excluded from active guidance.
    state["latest_interaction_event"] = {"status": "accepted", "memory": memory, "response_applied": True}
    return reply
