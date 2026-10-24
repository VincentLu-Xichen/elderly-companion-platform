"""Deterministic offline demonstration; never claims to measure model quality."""

from __future__ import annotations

import json
import re

from daily_agent.azure_chat_client import ChatCompletionResult
from cbt_course_llm_freeform.feedback import answer_needs_help
from cbt_course_llm_freeform.design import QUESTIONS


class PreviewClient:
    def complete_with_metadata(self, messages, **kwargs):
        prompt = messages[0]["content"]
        if "课后教学复盘" in prompt:
            data = json.loads(messages[-1]["content"])
            feedback = data.get("learner_feedback")
            check = data.get("learning_result")
            if check and check.get("first_attempt"):
                wrong = next(
                    (
                        item
                        for item in check["first_attempt"]
                        if item["verdict"] in {"does_not_match", "partial", "unclear"}
                    ),
                    None,
                )
                observed = next(
                    (item for item in check["first_attempt"] if item["verdict"] != "not_observed"),
                    None,
                )
                item = wrong or observed
                output = {"observations": [], "suggestions": [], "hypotheses": []}
                if item:
                    source = item["source_message_id"]
                    output["observations"] = [
                        {
                            "text": "本次检验的首次回答与提示、补练已分别保存；实际生活使用尚待反馈。",
                            "source_message_ids": [source],
                        }
                    ]
                    output["hypotheses"] = [
                        {
                            "text": (
                                "本次有概念需要继续核对，可以先用日常说法作对照。"
                                if wrong
                                else "本次概念辨认较顺利，下一课可尝试减少个人记录的提示。"
                            ),
                            "source_message_ids": [source],
                            "context": "仅针对本次课程任务，不代表稳定能力或个人心理特征。",
                            "alternative_explanation": "题目表述和这一次的注意点也可能影响表现，规则体验尚不能检验真实理解。",
                            "next_action": "第二课用新的生活例子复核想法、心情的区别，再邀请本人自行整理。",
                            "verification": "观察新任务中是否仍需概念提示；根据新证据修改或撤回这条建议。",
                        }
                    ]
            elif feedback:
                source = feedback["source_message_id"]
                output = {
                    "observations": [
                        {
                            "text": "本人留下了课后反馈：" + feedback["value"][:120],
                            "source_message_ids": [source],
                        }
                    ],
                    "suggestions": [
                        {
                            "text": "之后可先询问这条反馈是否仍适用，再共同调整讲解节奏；这是待验证的建议。",
                            "source_message_ids": [source],
                        }
                    ],
                }
            else:
                output = {"observations": [], "suggestions": []}
        else:
            context = json.loads(messages[1]["content"])["data"]
            if "COURSE_CASE_REVIEW" in prompt:
                fields = list(context["fields"].values())
                output = {
                    "summary": ("虚构案例中，" if context["fictional"] else "这次您提到：")
                    + "；".join(item["value"] for item in fields)[:240]
                    + "。",
                    "source_message_ids": list(
                        dict.fromkeys(item["source_message_id"] for item in fields)
                    )[:8],
                }
                return ChatCompletionResult(
                    text=json.dumps(output, ensure_ascii=False),
                    model="offline-rule-preview",
                    finish_reason="stop",
                )
            latest = next(
                json.loads(item["content"])
                for item in reversed(messages)
                if item["role"] == "user" and "text" in json.loads(item["content"])
            )
            if prompt.lstrip().startswith("你是课程互动反馈的审慎复盘器"):
                text = latest["text"]
                feedback = any(
                    word in text for word in ("一直追问", "已经说过", "别再问", "解释太长")
                ) and not text.startswith("不是")
                output = dict(
                    verdict="feedback" if feedback else "not_feedback",
                    source_message_id=latest["id"],
                    quote=text,
                    observation="仅离线合成判读",
                    hypothesis="本次追问可能有负担",
                    alternative_explanation="也可能在谈故事人物",
                    scope="lesson",
                    reply_length="short",
                    follow_up="stop" if feedback else "standard",
                    reply=(
                        "抱歉，刚才追问造成负担，我们先不再补问。" if feedback else "继续当前教学。"
                    ),
                    personal_intent="none",
                    response_type="review_current_case" if feedback else "neutral",
                    tone="polite",
                    task_action="continue",
                )
            elif "COURSE_LESSON2_BLUEPRINT" in prompt:
                output = self._lesson2(context, latest)
            elif "COURSE_NAVIGATION" in prompt:
                # Offline demonstration only; real runs use the navigation LLM.
                text = latest["text"]
                if context["stage"] == "check_feedback":
                    if text in {"继续", "继续设置目标", "我想设置目标"}:
                        output = dict(
                            intent="actions",
                            actions=[
                                dict(
                                    action="continue_after_check",
                                    source_message_id=latest["id"],
                                    quote=text,
                                )
                            ],
                        )
                    elif text in {"再练一次", "我想补练"}:
                        output = dict(
                            intent="actions",
                            actions=[
                                dict(
                                    action="start_check_retry",
                                    source_message_id=latest["id"],
                                    quote=text,
                                )
                            ],
                        )
                    elif re.search(r"我(?:的练习目标|希望|愿意|想减少)", text) and not re.search(
                        r"不是|没想好|他说|她说", text
                    ):
                        output = dict(
                            intent="goal",
                            goal_items=[text],
                            goal_level="concrete" if "记录一次" in text else "direction",
                        )
                    else:
                        output = dict(intent="clarify", reply="可以继续设置目标，也可以补练一次。")
                elif context["stage"] == "learning_goal" and not re.search(
                    r"完成|结束|继续|跳过|不设", text
                ):
                    output = {
                        "intent": "goal",
                        "actions": [],
                        "reply": "",
                        "goal_items": [
                            item.strip() for item in re.split(r"[；;\n]", text) if item.strip()
                        ],
                    }
                else:
                    output = {
                        "intent": "clarify",
                        "actions": [],
                        "reply": "您是想保留当前安排，还是跳过这个可选环节？",
                    }
            elif "COURSE_CHECK_ANSWER" in prompt:
                output = self._check(context, latest)
            elif "COURSE_GUIDANCE_REFLECTION" in prompt:
                output = self._reflection(context, latest)
            elif "COURSE_GUIDANCE_ACTOR" in prompt:
                strategy = (
                    context["active_guidance"]["strategy"]
                    if context.get("active_guidance")
                    else "continue_current"
                )
                lead = {
                    "rephrase_plainly": "我们换种生活里的说法，慢一点看。",
                    "acknowledge_correction": "谢谢您纠正，我会保留您的说法。",
                    "clarify_missing_field": "已经有的记录先保留，我们只补这一项。",
                    "ask_concrete_fact": "可以暂时不确定，我们只看具体依据。",
                }.get(strategy, "我们按您刚才的回答继续。")
                output = {"reply": lead + context["next_question"]}
            else:
                output = self._teaching(context, latest)
        return ChatCompletionResult(
            text=json.dumps(output, ensure_ascii=False),
            model="offline-rule-preview",
            finish_reason="stop",
        )

    @staticmethod
    def _check(context, latest):
        text = latest["text"].strip()
        field = context["field"]
        retry = context["retry"]
        patterns = {
            "situation": r"打招呼|问好|早上好",
            "thought": r"安排.*乱" if retry else r"没礼貌|不礼貌|礼貌.*[？?]",
            "emotion": r"失望" if retry else r"紧张|不安",
            "behavior": r"低.*头|没.*[回开][应话口]|没有回应",
        }
        if context.get("lesson2_review"):
            patterns = {
                "thought": r"认知|想法",
                "emotion": r"情绪|心情|感受",
                "behavior": r"行为|动作",
            }
        matched = bool(re.search(patterns[field], text)) and not re.search(
            r"不是(?:紧张|失望|不安|低头|打招呼)", text
        )
        return {
            "verdict": "matches" if matched else "does_not_match",
            "reason": (
                "规则体验：回答包含本题参考含义。"
                if matched
                else "规则体验：未识别到本题参考含义，请在反馈时核对；这不是实际模型理解评估。"
            ),
            "source_message_id": latest["id"],
        }

    @staticmethod
    def _lesson2(context, latest):
        text, step = latest["text"], context["step"]
        output = {"reply": "谢谢您的说明。", "observations": [], "practice_origin": "current_case"}

        def add(field, value):
            output["observations"].append(
                {"field": field, "value": value, "source_message_id": latest["id"]}
            )

        if step == "check_in":
            add("mood", text)
        elif step == "homework":
            add("homework_report", text)
            output["homework_status"] = (
                "self_reported_attempt" if "试" in text and "没" not in text else "not_attempted"
            )
        elif step in {"contrast", "rain_insight", "recall"}:
            output["intent"] = "continue"
        elif step in {"rain", "personal", "model"}:
            labels = {
                "情境": "situation",
                "事情": "situation",
                "想法": "thought",
                "情绪": "emotion",
                "心情": "emotion",
                "情绪强度": "emotion_intensity",
            }
            for match in re.finditer(
                r"(?:^|[；;\n])\s*(情绪强度|情境|事情|想法|情绪|心情)[:：]\s*([^；;\n]+)", text
            ):
                if labels[match[1]] in context["allowed_fields"]:
                    add(labels[match[1]], match[2].strip())
            if not output["observations"] and context.get("focus"):
                add(context["focus"], text)
            if step == "model" and not output["observations"]:
                add("relationship_note", text)
        return output

    @staticmethod
    def _reflection(context, latest):
        reasons = context["trigger_decision"]["reason_codes"]
        state = context["state_after"]
        missing = state["missing_fields"]
        if "confusion" in reasons:
            strategy, brief = (
                "rephrase_plainly",
                "本次回答明确表示没听懂，下一条指导可以减少术语并换一个说法；效果待核对。",
            )
        elif "correction" in reasons or "comparable_conflict" in reasons:
            strategy, brief = (
                "acknowledge_correction",
                "本次出现纠正或待核对的信息，先核对本人说法，不继续沿用旧推测。",
            )
        elif state["stage"] == "review":
            strategy, brief = (
                "summarize_for_confirmation",
                "必要字段已收集，邀请本人核对；字段齐全不代表已经掌握。",
            )
        elif state["stage"] == "practice" and missing:
            strategy, brief = (
                "clarify_missing_field",
                "聚焦当前尚缺的一项，避免重复索取已经回答的信息。",
            )
        else:
            strategy, brief = "continue_current", "当前按阶段继续，后续是否有帮助仍待反馈。"
        return {
            "reflection": {
                "update": "replace",
                "brief": brief,
                "strategy": strategy,
                "focus_field": (
                    missing[0] if strategy == "clarify_missing_field" and missing else None
                ),
                "source_message_ids": [latest["id"]],
                "open_items": [],
                "previous_strategy_result": "unknown",
            }
        }

    @staticmethod
    def _teaching(context, latest):
        text, message_id, stage = latest["text"], latest["id"], context["stage"]
        observations, advance, candidates, signals = [], False, [], []

        def record(field, value):
            observations.append({"field": field, "value": value, "source_message_id": message_id})

        uncertain = answer_needs_help(text)
        if stage == "check_in":
            if not uncertain:
                record("mood", text[:450])
                advance = True
            reply = (
                "谢谢您告诉我，我们按您舒服的节奏来。"
                if advance
                else "可以慢慢说，不用一定打分。您也可以选择先看一个例子。"
            )
        elif stage == "learn" and not context.get("blueprint"):
            if not uncertain and any(
                word in text
                for word in (
                    "想法",
                    "心情",
                    "平静",
                    "失落",
                    "难过",
                    "不同",
                    "担心",
                    "猜测",
                    "推测",
                    "安全",
                    "小步",
                    "不必",
                    "不能",
                    "信号",
                    "依据",
                    "调整",
                    "技能",
                    "原来的",
                    "事实",
                    "信息",
                )
            ):
                record("learning_response", text[:450])
                advance = True
            reply = (
                "谢谢您的回答，我们接着看自己的例子。"
                if advance
                else "我们先用生活里的话看看这个例子。" + context["example"]
            )
        elif stage == "practice" or context.get("blueprint") and stage in {"learn", "review"}:
            labels = {label: field for field, label in context["field_input_labels"].items()}
            labels.update({"情绪": "emotion", "行为": "behavior"})
            labels.update({"相信程度": "thought_belief", "情绪强度": "emotion_intensity"})
            tag_pattern = "|".join(
                re.escape(label) for label in sorted(labels, key=len, reverse=True)
            )
            matches = list(
                re.finditer(r"(?:^|[；;\n])\s*(" + tag_pattern + r")\s*[:：]\s*([^；;\n]+)", text)
            )
            for match in matches:
                field = labels[match.group(1)]
                if field in context["required_fields"] and match.group(2).strip():
                    record(
                        field,
                        (
                            match.group(0).strip("；;\n ")
                            if field in {"thought_belief", "emotion_intensity"}
                            else match.group(2).strip()[:450]
                        ),
                    )
            missing = [
                field
                for field in context["missing_fields"]
                if field not in [item["field"] for item in observations]
            ]
            if not matches and stage == "review" and not uncertain:
                record("relationship_note", text[:450])
            if not matches and missing and not uncertain:
                record(
                    (
                        "relationship_note"
                        if stage == "review"
                        else "situation" if stage == "learn" else missing[0]
                    ),
                    text[:450],
                )
                missing = missing[1:]
            from cbt_course_llm_freeform.blueprint import QUESTIONS as BLUEPRINT_QUESTIONS

            reply = (
                {**QUESTIONS, **BLUEPRINT_QUESTIONS}[missing[0]]
                if missing
                else "我们来一起核对这份记录。"
            )
        elif stage == "summary":
            record("feedback", text[:450])
            reply = "谢谢您告诉我，我会保留这条反馈。准备好时，可以选择完成本课。"
        elif stage == "check_feedback":
            record("feedback", text[:450])
            reply = "您的反馈已保留。首次回答不会被改写；可以选择补练，也可以继续设置练习目标。"
        else:
            reply = "课后尝试由您决定，愿意或暂时不安排都可以。请使用页面上的选择确认。"
        if "没听懂" in text:
            signals = [{"kind": "confusion", "quote": "没听懂", "source_message_id": message_id}]
        return {
            "reply": reply,
            "observations": observations,
            "advance": advance,
            "domain_candidates": candidates,
            "assessment": {"signals": signals},
        }
