from __future__ import annotations

import copy
import re
import uuid
from typing import Any

from cbt_course_llm_freeform.agent import FreeformCourseAgent
from cbt_course_llm_freeform.catalog import require_available_course
from cbt_course_llm_freeform.design import (
    FIELD_LABELS,
    MODEL_TOKEN_LIMITS,
    PRACTICE_PLANS,
    INPUT_LABELS,
    QUESTIONS,
    SKILLS,
    STAGE_LABELS,
    stage_intro,
    task_step_id,
    required_fields,
    lesson_example,
    LESSON_1_GUIDED_EXAMPLE,
)
from cbt_course_llm_freeform.feedback import (
    active_guidance,
    allowed_strategies,
    answer_needs_help,
    decide_trigger,
    STRATEGY_INSTRUCTIONS,
)
from cbt_course_llm_freeform.lesson_1 import COMPLETION_MARKER, STATIC_ATTACHMENTS
from cbt_course_llm_freeform.lesson_2 import HARD_SAFETY_SIGNALS, SAFETY_MESSAGE
from cbt_course_llm_freeform.prompt import prompt_for_lesson
from cbt_course_llm_freeform.schemas import TeachingDecision, TurnResult
from cbt_course_llm_freeform import learning_check, practice_flow, interaction, boundaries
from cbt_course_llm_freeform import navigation, blueprint, lesson2_flow, dialogue

# Keep established imports working while implementations live with their responsibility.
from cbt_course_llm_freeform.presentation import course_payload as course_payload
from cbt_course_llm_freeform.state import (
    IMPLEMENTATION as IMPLEMENTATION,
    can_reuse_case as can_reuse_case,
    new_course_state as new_course_state,
    reusable_fields,
)

ATTACHMENT_PATTERN = re.compile(r"\[\[CBT_ATTACHMENT:([^\]\r\n]+)\]\]")
ACTION_LABELS = {
    "edit_learning_goal": "修改课程目标",
    "skip_checkin": "先看例子",
    "confirm_record": "确认这份记录",
    "edit_record": "我要修改记录",
    "accept_practice": "愿意试一次",
    "decline_practice": "这次不安排",
    "finish": "完成本课",
    "pause": "暂停课程",
    "resume": "继续课程",
    "accept_carryover": "使用已确认的课程摘要",
    "decline_carryover": "本课重新开始",
    "reuse_case": "沿用上一课这件事",
}
ACTION_LABELS.update(learning_check.CONTROL_LABELS)
ACTION_LABELS.update(practice_flow.CONTROL_LABELS)
TEXT_ACTIONS = {label: key for key, label in ACTION_LABELS.items()}
TEXT_ACTIONS["使用上一课摘要"] = "accept_carryover"
ACTION_LABELS.update(
    continue_lesson2="继续第二课当前环节",
    skip_lesson2_step="跳过第二课当前项",
    stop_lesson2_quiz="剩余复习题先不做",
)
ACTION_LABELS["start_mood_check"] = "已看完，开始心境检查"


def parse_control_markers(raw_reply: str, lesson_id: str = "lesson-1"):
    """Historical parser, never used by the current state machine to finish."""
    keys = [m.group(1).strip() for m in ATTACHMENT_PATTERN.finditer(raw_reply)]
    key = next(
        (
            key
            for key in keys
            if lesson_id == "lesson-1" and key in STATIC_ATTACHMENTS and key != "course_overview"
        ),
        None,
    )
    cleaned = ATTACHMENT_PATTERN.sub("", raw_reply.replace(COMPLETION_MARKER, "")).strip()
    if not cleaned:
        raise RuntimeError("自由课程模型只返回了控制标记，没有可展示的回复。")
    return (
        cleaned,
        dict(STATIC_ATTACHMENTS[key]) if key else {},
        COMPLETION_MARKER in raw_reply,
        key,
    )


def faithful_excerpt(source: str, quote: str) -> bool:
    """Conservative negation/uncertainty guard, not a semantic correctness proof."""
    start = source.find(quote)
    if start < 0:
        return False
    prefix = source[max(0, start - 8) : start]
    return not re.search(r"(?:没有|不是|并非|不确定|可能|也许|不|没|未)(?:很|太|觉得|是)?$", prefix)


def next_question(state: dict) -> str:
    from cbt_course_llm_freeform import teacher_flow

    if (
        teacher_flow.enabled(state)
        and state["stage"] == "check_in"
        and state.get("lesson2_flow", {}).get("step", "check_in") == "check_in"
    ):
        return teacher_flow.MOOD_QUESTION
    if lesson2_flow.enabled(state):
        return lesson2_flow.question(state)
    if learning_check.enabled(state) and state["stage"] in {
        "assessment",
        "check_feedback",
        "learning_goal",
    }:
        return learning_check.next_prompt(state)
    if blueprint.enabled(state) and state["stage"] in {"learn", "practice", "review"}:
        return blueprint.instruction(state)
    if state["stage"] == "practice":
        if boundaries.fictional(state):
            field = next(iter(practice_flow.missing(state)), None)
            return (
                "我们用这个虚构案例继续："
                + boundaries.source(state)["story"]
                + (
                    "\n请从案例里找出“" + FIELD_LABELS[field] + "”的内容。"
                    if field
                    else "\n请核对案例练习记录。"
                )
            )
        if practice_flow.enabled(state):
            return practice_flow.reply(state)
        missing = next(
            (key for key in required_fields(state) if key not in state["draft_record"]), None
        )
        if missing:
            return QUESTIONS[missing]
    return stage_intro(state["lesson_id"], state["stage"], path=state.get("path"))


class FreeformCourseRuntime:
    def __init__(self, *, agent: FreeformCourseAgent | None = None, on_reply=None):
        self.agent = agent
        self.on_reply = on_reply
        self.model_calls: list[dict] = []

    def _lesson2_agent(self):
        if self.agent is None:
            self.agent = FreeformCourseAgent(
                system_prompt=prompt_for_lesson("lesson-2"), max_completion_tokens=1200
            )
        self.agent.call_log = self.model_calls
        if isinstance(self.agent, FreeformCourseAgent):
            self.agent.on_reply = None
            self.agent.stream_teaching = False
        return self.agent

    def _context(self, state: dict) -> dict:
        lesson_id, stage = state["lesson_id"], state["stage"]
        labels = {**STAGE_LABELS, **learning_check.LABELS}
        if blueprint.enabled(state):
            labels.update(
                learn="选择困扰与情境",
                practice="逐步理解这件事",
                review="回看模型与核对",
                assessment="四要素辨认练习",
                learning_goal="整套课程目标",
            )
        return {
            "dialogue_policy": state.get("dialogue_policy"),
            "lesson2": lesson2_flow.enabled(state),
            "lesson2_step": state.get("lesson2_flow", {}).get("step"),
            "lesson_id": lesson_id,
            "stage": stage,
            "stage_label": labels[stage],
            "path": state.get("path"),
            "path_label": None,
            "task_step_id": task_step_id(state),
            "case_id": state["case_id"],
            "recorded_fields": state["draft_record"],
            "required_fields": (
                blueprint.FIELDS if blueprint.enabled(state) else required_fields(state)
            ),
            "field_input_labels": INPUT_LABELS,
            "field_labels": FIELD_LABELS,
            "missing_fields": (
                lesson2_flow.missing(state)
                if lesson2_flow.enabled(state)
                and state["lesson2_flow"]["step"] in {"personal", "model"}
                else practice_flow.missing(state)
            ),
            "stage_focus": practice_flow.stage_focus(state),
            "personal_practice": practice_flow.payload(state),
            "interaction_adaptation": copy.deepcopy(practice_flow.adaptation(state)),
            "interaction_guidance": interaction.guidance(state),
            "stop_probing": state.get("practice_flow", {}).get("stop_probing", False),
            "personal_disclosure": boundaries.context(state),
            "practice_source": boundaries.source(state),
            "primary_interaction_decision": (
                {
                    key: state["latest_interaction_event"]["judgment"].get(key)
                    for key in ("verdict", "personal_intent", "source_message_id")
                }
                if state.get("latest_interaction_event", {}).get("judgment")
                else None
            ),
            "confirmed_record": state.get("confirmed_record"),
            "domain_candidates": state.get("domain_candidates", []),
            "authorized_previous_lesson_summary": (
                state["carryover"].get("summary")
                if state["carryover"].get("status") == "accepted"
                else None
            ),
            "authorized_previous_lesson_summaries": (
                [item["summary"] for item in state["carryover"].get("sources", [])]
                if state["carryover"].get("status") == "accepted"
                else []
            ),
            "active_guidance": active_guidance(state),
            "next_question": next_question(state),
            "example": (
                blueprint.CONCEPTS["situation"]
                if blueprint.enabled(state)
                else lesson_example(state)
            ),
            "blueprint": blueprint.payload(state),
            "guided_example": (
                dict(LESSON_1_GUIDED_EXAMPLE)
                if lesson_id == "lesson-1" and stage == "learn" and not blueprint.enabled(state)
                else None
            ),
            "learning_check": (
                learning_check.payload(state) if learning_check.enabled(state) else None
            ),
        }

    def process(
        self, state: dict[str, Any], history: list[dict[str, str]], *, action: str = "chat"
    ) -> TurnResult:
        updated = copy.deepcopy(state)
        updated.pop("latest_interaction_event", None)
        updated.pop("boundary_event", None)
        lesson_id = str(updated.get("lesson_id", ""))
        require_available_course(lesson_id)
        self.model_calls = []
        if isinstance(self.agent, FreeformCourseAgent):
            self.agent.call_log = self.model_calls
            hide_draft = practice_flow.enabled(updated) and updated["stage"] in (
                {"learn", "practice", "review"}
                if blueprint.enabled(updated)
                else {"practice", "review"}
            )
            if self.on_reply is not None:
                self.agent.on_reply = None if hide_draft else self.on_reply
            self.agent.stream_teaching = updated["workflow"]["policy"] == "none" and not hide_draft
        if updated.get("implementation") != IMPLEMENTATION:
            raise ValueError("该课程使用旧版实现，仅支持查看。请从课程目录进入新版。")
        if updated.get("completed"):
            raise ValueError("本课已经完成，仅支持查看。")
        latest = next((item for item in reversed(history) if item.get("role") == "learner"), {})
        text = latest.get("content", "").strip()
        if action == "chat" and dialogue.confirms_record(updated, text):
            action = "confirm_record"
        natural_feedback = updated.get("interaction_reflection_version") == interaction.VERSION
        if (
            action == "chat"
            and natural_feedback
            and text in practice_flow.FEEDBACK_CONTROLS.values()
        ):
            pass  # Natural feedback must go through the semantic judge, not the old buttons.
        else:
            navigation_chat = updated.get("navigation_version") == navigation.VERSION and updated[
                "stage"
            ] in {"learning_goal", "plan", "summary"}
            action = (
                TEXT_ACTIONS.get(text, action)
                if action == "chat" and not navigation_chat
                else action
            )
        if action == "chat" and practice_flow.enabled(updated) and updated["stage"] == "practice":
            action = (
                (None if natural_feedback else practice_flow.feedback_action(text))
                or practice_flow.explicit_action(text)
                or action
            )
        stage_before, task_before = updated["stage"], task_step_id(updated)
        if updated.get("safety_paused"):
            raise ValueError("本课已安全暂停，请联系现实中的帮助；记录可以继续查看。")
        if any(signal in text for signal in HARD_SAFETY_SIGNALS):
            updated["safety_paused"] = True
            return self._result(updated, SAFETY_MESSAGE, stage_before, safety="local_self_harm")
        if updated.get("paused") and action != "resume":
            raise ValueError("课程已暂停，请选择继续课程。")
        boundaries.ensure(updated)
        from cbt_course_llm_freeform import teacher_flow

        if action in {"skip_checkin", "start_mood_check"}:
            response = teacher_flow.handle_checkin(self, updated, latest, action)
            if response is not None:
                return self._result(updated, response, stage_before, action=action)
        if action != "chat":
            reply = self._control(updated, latest, action)
            updated["workflow"]["last_trigger"] = {
                "policy": updated["workflow"]["policy"],
                "triggered": False,
                "reason_codes": ["deterministic_action"],
                "action": action,
            }
            return self._result(updated, reply, stage_before, action=action)
        boundary_candidate = boundaries.applicable(updated) and (
            boundaries.candidate(text)
            or updated.get("privacy", {}).get("pending")
            or updated.get("privacy", {}).get("recovery")
        )
        if natural_feedback and (
            interaction.candidate(
                text, task_feedback=blueprint.enabled(updated) or lesson2_flow.enabled(updated)
            )
            or boundary_candidate
        ):
            event_result = self._interaction_event(updated, history, latest, stage_before)
            if event_result is not None:
                return event_result
        response = teacher_flow.handle_checkin(self, updated, latest, action)
        if response is not None:
            return self._result(updated, response, stage_before, action="weekly_mood")
        if lesson2_flow.enabled(updated):
            return lesson2_flow.process(self, updated, history, latest, stage_before)
        if (
            blueprint.enabled(updated)
            and updated["stage"] == "learn"
            and blueprint.select_case(updated, latest)
        ):
            return self._result(
                updated,
                "我们先看您选的这一件："
                + updated["draft_record"]["situation"]["value"]
                + "。"
                + next_question(updated),
                stage_before,
                action="select_case",
            )
        if updated.get("navigation_version") == navigation.VERSION and (
            updated["stage"] in {"learning_goal", "plan", "summary"}
            or dialogue.enabled(updated)
            and updated["stage"] == "check_feedback"
            and not learning_check.retrying(updated)
        ):
            return self._navigate(updated, history, latest, stage_before)
        if learning_check.enabled(updated) and updated["stage"] == "learning_goal":
            return self._result(
                updated,
                learning_check.goal_answer(updated, latest),
                stage_before,
                action="learning_goal_draft",
            )
        if learning_check.enabled(updated) and (
            updated["stage"] == "assessment" or learning_check.retrying(updated)
        ):
            if self.agent is None:
                self.agent = FreeformCourseAgent(
                    system_prompt=prompt_for_lesson(lesson_id),
                    max_completion_tokens=MODEL_TOKEN_LIMITS[lesson_id],
                    on_reply=self.on_reply,
                )
                self.agent.call_log = self.model_calls
            reply, completion = learning_check.answer(updated, latest, self.agent)
            if not isinstance(reply, str):
                note = interaction.validate(reply, latest)
                event_result = self._accept_interaction(
                    updated, note, latest, stage_before, completion
                )
                if event_result is not None:
                    return event_result
                # A reported non-feedback/uncertain message is not automatically
                # an answer, a hint request or permission to skip.
                return self._result(
                    updated,
                    "这一轮先不计作答。您可以继续回答当前题，也可以直接说想跳过或暂停。",
                    stage_before,
                    completion=completion,
                    action="check_intent_uncertain",
                )
            updated["workflow"]["last_trigger"] = {
                "triggered": False,
                "reason_codes": ["learning_check_no_early_feedback"],
            }
            return self._result(
                updated, reply, stage_before, completion=completion, action="learning_check"
            )
        return self._teach(state, updated, history, latest, stage_before, task_before)

    def _teach(self, state, updated, history, latest, stage_before, task_before):
        """Apply teaching only after safety, controls and lesson routing have finished."""
        from cbt_course_llm_freeform import teacher_flow

        lesson_id = updated["lesson_id"]
        text = latest.get("content", "").strip()
        if blueprint.enabled(updated) and stage_before == "learn":
            focus_before_learn = "situation"
        else:
            focus_before_learn = None
        if stage_before == "review" and not blueprint.enabled(updated):
            updated["stage"] = "practice"
        stage = updated["stage"]
        bounded_practice = practice_flow.enabled(updated) and stage == "practice"
        focus_before = practice_flow.current_field(updated) if bounded_practice else None
        before_fields = copy.deepcopy(updated["draft_record"])
        if self.agent is None:
            self.agent = FreeformCourseAgent(
                system_prompt=prompt_for_lesson(lesson_id),
                max_completion_tokens=MODEL_TOKEN_LIMITS[lesson_id],
                on_reply=self.on_reply,
            )
            self.agent.call_log = self.model_calls
        if isinstance(self.agent, FreeformCourseAgent):
            hide_draft = (
                bounded_practice or blueprint.enabled(updated) and stage in {"learn", "review"}
            )
            self.agent.stream_teaching = updated["workflow"]["policy"] == "none" and not hide_draft
            if hide_draft:
                self.agent.on_reply = None
        result = self.agent.reply(history[-24:], context=self._context(updated))
        if not isinstance(result.decision, TeachingDecision):
            raise RuntimeError("课程模型未返回有效结构化结果，本轮学习记录未更新。")
        # Test adapters may not implement a client call log. Real calls log at the client boundary.
        if not isinstance(self.agent, FreeformCourseAgent) and result.completion is not None:
            self.model_calls.append(
                {
                    "phase": "teaching",
                    "status": "success",
                    "usage": result.completion.usage,
                    "model": result.completion.model,
                }
            )
        decision = result.decision
        if not blueprint.enabled(updated) and (
            len(decision.observations) > 4
            or decision.next_practice_field is not None
            or decision.case_options
        ):
            raise RuntimeError("本课不接受第一课专属教学字段。")
        if decision.interaction is not None and not updated.get("latest_interaction_event", {}).get(
            "judgment"
        ):
            note = interaction.validate(decision.interaction, latest)
            event_result = self._accept_interaction(
                updated, note, latest, stage_before, result.completion
            )
            if event_result is not None:
                return event_result
        if decision.case_options:
            if (
                not blueprint.enabled(updated)
                or stage != "learn"
                or decision.observations
                or any(
                    not item or not faithful_excerpt(text, item) for item in decision.case_options
                )
            ):
                raise RuntimeError("案例选择缺少当前原话依据。")
            updated["blueprint"]["case_options"] = [
                {"value": item, "source_message_id": latest["id"]} for item in decision.case_options
            ]
            return self._result(
                updated,
                "您提到了几件事，我们先选一件：\n"
                + "\n".join(f"{i+1}. {item}" for i, item in enumerate(decision.case_options))
                + "\n您想先看哪一件？也可以先不谈。",
                stage_before,
                completion=result.completion,
                action="offer_case_choice",
            )
        if (
            stage == "practice"
            and boundaries.fictional(updated)
            and decision.practice_origin != "current_case"
        ):
            return self._result(
                updated,
                "您刚才说的内容我先保留在对话里，不把它填成虚构人物的经历。我们先不往下追问，当前案例记录也先不改。",
                stage_before,
                completion=result.completion,
                action="case_source_mismatch",
                case_origin=decision.practice_origin,
            )
        accepted, changed = self._apply_observations(updated, decision, latest, stage)
        signals = self._validated_signals(decision, latest, before_fields, changed)
        if blueprint.enabled(updated) and stage in {"learn", "practice"}:
            teacher_flow.after_lesson1(
                updated, focus_before_learn or focus_before, accepted, latest
            )
        reply = decision.reply
        uncertain = answer_needs_help(text)
        if blueprint.enabled(updated) and stage == "learn":
            if "situation" in accepted:
                updated["stage"] = "practice"
                blueprint.after_turn(updated, None, accepted, latest)
                reply = (
                    "谢谢您分享这件事。"
                    + teacher_flow.CARDS["situation"]["definition"]
                    + "已说出的内容会一起整理，不再重复问。"
                    + next_question(updated)
                )
            else:
                blueprint.after_turn(updated, focus_before_learn, accepted, latest)
                if "situation" in updated["practice_flow"]["deferred"]:
                    updated["stage"] = "practice"
                    reply = "这一项先留空。" + next_question(updated)
                elif uncertain and not interaction.guidance(updated):
                    reply = next_question(updated)
        elif blueprint.enabled(updated) and stage in {"practice", "review"}:
            if stage == "practice":
                blueprint.after_turn(updated, focus_before, accepted, latest)
            elif blueprint.missing(updated):
                updated["stage"] = "practice"
            if updated["stage"] == "review":
                if "relationship_note" in accepted and not changed:
                    reply = "谢谢您分享回看后的想法，这段补充也会保留。请核对右侧记录，准确的话可以确认；想修改也可以直接说。"
                elif stage == "review" and not changed:
                    reply = (
                        blueprint.review_text(updated, invite=False)
                        if updated["practice_flow"].get("stop_probing")
                        else "请核对现有记录是否准确；可以指出需要修改的地方，准确后再确认。"
                    )
                else:
                    reply = blueprint.review_text(updated)
            # Keep the model's natural acknowledgement; show a short, accurate
            # next-task anchor if its projected question is no longer current.
            elif accepted or focus_before != practice_flow.current_field(updated):
                if decision.next_practice_field != practice_flow.current_field(updated):
                    acknowledgement = "".join(
                        part + "。"
                        for part in reply.split("。")[:-1]
                        if "？" not in part and "?" not in part
                    )[:180]
                    reply = acknowledgement + next_question(updated)
            if (
                updated["blueprint"].get("rating_rejection", {}).get("source_message_id")
                == latest["id"]
            ):
                reply = (
                    "这次评分还没能准确对应到当前想法或情绪，我先不填入，也不会改成其他分数。"
                    + next_question(updated)
                )
            elif (
                uncertain
                and not interaction.guidance(updated)
                and stage == "practice"
                and focus_before in teacher_flow.CARDS
                and focus_before not in accepted
                and updated["stage"] == "practice"
            ):
                reply = next_question(updated)
        elif stage in {"check_in", "learn"} and decision.advance and accepted and not uncertain:
            updated["stage"] = "learn" if stage == "check_in" else "practice"
            if stage == "check_in" and updated["carryover"].get("status") == "offered":
                updated["carryover"] = {"status": "declined"}
            feedback = (
                decision.reply.strip()
                if len(decision.reply) <= 140
                and not any(word in decision.reply for word in ("？", "?", "完成", "确认", "[["))
                else ""
            )
            boundaries.ensure(updated)
            reply = feedback + (
                next_question(updated)
                if blueprint.enabled(updated)
                or boundaries.fictional(updated)
                and updated["stage"] == "practice"
                else stage_intro(lesson_id, updated["stage"], path=updated.get("path"))
            )
        elif bounded_practice:
            if boundaries.enabled(updated):
                for field in accepted:
                    updated["practice_flow"]["deferred"].pop(field, None)
                    updated["practice_flow"]["unanswered"].pop(field, None)
                if practice_flow.ready(updated):
                    updated["stage"] = "review"
            else:
                reply = practice_flow.update(updated, focus_before, accepted, latest)
        elif stage == "practice" and all(
            key in updated["draft_record"] for key in required_fields(updated)
        ):
            updated["stage"] = "review"
            reply = stage_intro(lesson_id, "review")
        if dialogue.enabled(updated) and stage in {"learn", "practice", "review"}:
            # Keep the state/teaching-card updates above, but do not replace the
            # model's acknowledgement, explanation or question with a template.
            if (
                updated["blueprint"].get("rating_rejection", {}).get("source_message_id")
                != latest["id"]
            ):
                reply = decision.reply
        trigger = decide_trigger(
            updated["workflow"],
            task_before=task_before,
            task_after=task_step_id(updated),
            signals=signals,
            changed_fields=changed,
            stage_before=stage_before,
        )
        trigger["evidence_message_ids"] = list(
            dict.fromkeys(signal["source_message_id"] for signal in signals)
        )
        trigger["context"] = {
            "case_id": updated["case_id"],
            "stage": stage_before,
            "task_step_id": task_before,
        }
        updated["workflow"]["last_trigger"] = trigger
        reflection_created = False
        if trigger["triggered"]:
            reply, reflection_created = self._reflect_and_guide(state, updated, history, latest)
        if bounded_practice and not boundaries.enabled(updated):
            # Reflection may suggest teaching strategies, never override the task boundary.
            reply = practice_flow.reply(updated) if reflection_created else reply
        reply = self._safe_reply(reply, updated)
        if updated.get("practice_flow", {}).get("stop_probing") and any(
            mark in reply for mark in ("？", "?")
        ):
            reply = "我们先不再补问，就围绕您前面说的这件事。" + practice_flow.reply(updated)
        return self._result(
            updated,
            reply,
            stage_before,
            completion=result.completion,
            observations=accepted,
            changed_fields=changed,
            trigger=trigger,
            reflection_created=reflection_created,
            reflection_response_applied=reflection_created
            and (not bounded_practice or boundaries.enabled(updated)),
        )

    def _accept_interaction(self, state, note, latest, stage_before, completion=None):
        task_action = note.get("task_action", "continue")
        second = lesson2_flow.enabled(state)
        if (
            second
            and task_action == "pause"
            and note.get("response_type") == "review_current_case"
            and note.get("follow_up") == "stop"
            and note.get("personal_intent", "none") == "none"
        ):
            # A same-case teaching adjustment cannot silently escalate to a
            # whole-course pause. Preserve the proposal for audit.
            if not re.search(
                r"暂停|停止.{0,3}(?:课程|本课)|休息|先不学|结束.{0,3}(?:课程|本课)",
                latest["content"],
            ):
                note = {
                    **note,
                    "proposed_task_action": task_action,
                    "task_action": "continue",
                    "action_guard": "local_stop_not_course_pause",
                }
                task_action = "continue"
        checking = (
            second
            and state["lesson2_flow"]["step"] == "recall"
            and state["lesson2_flow"]["quiz"]["index"] < 3
        ) or (
            learning_check.enabled(state)
            and (state["stage"] == "assessment" or learning_check.retrying(state))
        )
        personal_intent = note.get("personal_intent", "none")
        compatible_intent = (
            personal_intent == "none" or task_action == "pause" and personal_intent == "pause"
        )
        if task_action != "continue" and (
            state["lesson_id"] != "lesson-1"
            and not second
            or note["verdict"] != "feedback"
            or not compatible_intent
        ):
            raise ValueError("Task adjustment lacks valid lesson-one feedback")
        if task_action == "stop_check" and not checking:
            raise ValueError("Cannot stop a check outside an active check")
        if task_action == "continue" and boundaries.apply(state, note, latest):
            state["latest_interaction_event"] = {
                "status": "boundary_handled",
                "schema_version": boundaries.VERSION,
            }
            response = note["reply"]
            if second and personal_intent == "refuse_field":
                response = "这一项先不补问。" + lesson2_flow.question(state)
            return self._result(
                state,
                self._safe_reply(response, state),
                stage_before,
                completion=completion,
                action="boundary_feedback",
            )
        if note["verdict"] != "feedback":
            return None
        response = note["reply"]
        if task_action == "stop_check":
            if second:
                lesson2_flow.stop_quiz(state, latest)
                response += "\n" + lesson2_flow.question(state)
            else:
                learning_check.stop_remaining(state, latest)
                response = note["reply"]
            note.update(follow_up="standard", response_type="acknowledge_adjustment")
        elif task_action == "pause":
            state["paused"] = True
            response = "可以，我们先休息，课程已经暂停。之前的记录会保留，想继续时再恢复即可。"
        elif state.get("interaction_response_version") == interaction.RESPONSE_VERSION and (
            note.get("response_type") == "review_current_case" or note["follow_up"] == "stop"
        ):
            if second:
                step = state["lesson2_flow"]["step"]
                if step in {"personal", "model"}:
                    lesson2_flow.stop_personal(state, latest)
                elif step == "rain":
                    for field in ("emotion", "thought"):
                        if field not in state["lesson2_flow"]["rain"]["fields"]:
                            state["lesson2_flow"]["rain"]["deferred"][field] = {
                                "status": "withheld",
                                "source_message_ids": [latest["id"]],
                            }
                    response += "\n" + lesson2_flow.make_contrast(state)
            else:
                practice_flow.stop_and_review(state, latest)
            anchor = state.get("draft_record", {}).get("situation", {}).get("value")
            if anchor and anchor not in note["reply"]:
                response += "\n仍围绕这件事：" + anchor + "。已有记录可在右侧核对或修改。"
        note.update(applied_action=task_action, effect="not_measured")
        note.update(
            id=str(uuid.uuid4()),
            kind="llm_interaction_reflection",
            schema_version=interaction.VERSION,
            lesson_id=state["lesson_id"],
            effect="not_measured",
            status="active",
        )
        state["latest_interaction_event"] = {
            "status": "accepted",
            "memory": note,
            "response_applied": True,
        }
        state["interaction_memories"] = [note] + state.get("interaction_memories", [])[:2]
        return self._result(
            state,
            self._safe_reply(response, state),
            stage_before,
            completion=completion,
            action="interaction_feedback",
        )

    def _interaction_event(self, state, history, latest, stage_before):
        """A feedback turn is not an answer to the current learning task."""
        event = {
            "kind": "llm_interaction_reflection",
            "status": "pending",
            "source_message_id": latest.get("id"),
            "schema_version": interaction.VERSION,
            "effect": "not_measured",
        }
        state["latest_interaction_event"] = event
        try:
            if self.agent is None:
                self.agent = FreeformCourseAgent(
                    system_prompt=prompt_for_lesson(state["lesson_id"]),
                    max_completion_tokens=MODEL_TOKEN_LIMITS[state["lesson_id"]],
                    on_reply=self.on_reply,
                )
            self.agent.call_log = self.model_calls
            result = self.agent.reflect_interaction(history[-8:], context=self._context(state))
            note = interaction.validate(result.decision, latest)
            event["judgment"] = copy.deepcopy(note)
            event.update(status="judged", verdict=note["verdict"])
            return self._accept_interaction(state, note, latest, stage_before, result.completion)
        except Exception as exc:
            event.update(status="failed", error_type=type(exc).__name__, response_applied=False)
            if type(exc) is ValueError:
                event["validation_reason"] = str(exc)
            if learning_check.enabled(state) and (
                state["stage"] == "assessment" or learning_check.retrying(state)
            ):
                state["paused"] = True
                event.update(fallback_applied=True, fallback_action="pause_check")
                return self._result(
                    state,
                    "抱歉，这次没能准确理解您的调整要求。我先暂停出题，已做内容会保留；您可以稍后恢复，或再说明想跳过剩下的题。",
                    stage_before,
                    action="interaction_feedback_failed",
                )
            if lesson2_flow.enabled(state):
                state["paused"] = True
                event.update(fallback_applied=True, fallback_action="pause_current_activity")
                return self._result(
                    state,
                    "抱歉，这次没能准确理解您的调整要求。先停止当前询问，已有内容保留，您可以稍后恢复。",
                    stage_before,
                    action="interaction_feedback_failed",
                )
            disclosure_attempt = boundaries.applicable(state) and (
                boundaries.candidate(latest.get("content", ""))
                or state.get("privacy", {}).get("pending")
                or state.get("privacy", {}).get("recovery")
            )
            if disclosure_attempt:
                state.setdefault("privacy", boundaries.new_flow())["recovery"] = True
            if (
                state.get("interaction_response_version") == interaction.RESPONSE_VERSION
                and not disclosure_attempt
            ):
                event.update(fallback_applied=True, fallback_action="review_current_case")
                practice_flow.stop_and_review(state, latest)
                return self._result(
                    state,
                    "抱歉，刚才的追问给您添了负担。我们先不再补问，仍围绕您前面说的这件事，已有内容保留，没说到的先留空。",
                    stage_before,
                    action="interaction_feedback_failed",
                )
            if state.get("interaction_response_version") == interaction.RESPONSE_VERSION:
                return self._result(
                    state,
                    "抱歉，刚才的询问可能让您不舒服。这件事先不再追问，您不需要补充说明。",
                    stage_before,
                    action="interaction_feedback_failed",
                )
            return self._result(
                state,
                "收到您的表达。这轮先不继续追问，课程记录保持原样。",
                stage_before,
                action="interaction_feedback_failed",
            )

    @staticmethod
    def _apply_observations(state, decision, latest, stage):
        lesson_id = state["lesson_id"]
        allowed = {
            "check_in": {"mood"},
            "learn": {"learning_response"},
            "practice": set(required_fields(state)),
            "plan": {"goal"},
            "summary": {"feedback"},
            "check_feedback": {"feedback"},
        }.get(stage, set())
        aligned = blueprint.enabled(state)
        focus = practice_flow.current_field(state) if aligned and stage == "practice" else None
        if aligned and stage == "learn":
            allowed = set(blueprint.FIELDS)
        elif aligned and stage in {"practice", "review"}:
            allowed = set(blueprint.FIELDS) | (
                {"relationship_note"} if stage == "review" else set()
            )
        accepted, changed = [], []
        if aligned:
            changed_bases = [
                item.field
                for item in decision.observations
                if item.field in {"situation", "thought", "emotion", "behavior"}
                and state["draft_record"].get(item.field, {}).get("value") != item.value
            ]
            blueprint.invalidate(state, changed_bases)
        for evidence in sorted(
            decision.observations, key=lambda item: item.field in blueprint.RATINGS
        ):
            if (
                evidence.field not in allowed
                or evidence.source_message_id != latest.get("id")
                or not faithful_excerpt(latest["content"], evidence.value)
            ):
                raise RuntimeError("课程记录的字段或原话来源无效，本轮进度未改变。")
            if evidence.field in accepted:
                raise RuntimeError("同一字段不能在一轮中提交多个不同摘录。")
            if aligned and evidence.field in blueprint.RATINGS:
                if blueprint.accept_rating(state, evidence, latest, focus):
                    accepted.append(evidence.field)
                else:
                    state["blueprint"]["rating_rejection"] = {
                        "field": evidence.field,
                        "quote": evidence.value,
                        "source_message_id": latest["id"],
                    }
                continue
            if aligned and evidence.field == "relationship_note":
                state["blueprint"]["relationship"] = {
                    "value": evidence.value,
                    "source_message_id": latest["id"],
                    "source_kind": boundaries.source(state)["kind"],
                    "case_id": state["case_id"],
                }
                accepted.append(evidence.field)
                continue
            value = {"value": evidence.value, "source_message_id": evidence.source_message_id}
            accepted.append(evidence.field)
            if stage == "practice" or aligned and stage in {"learn", "review"}:
                if state["draft_record"].get(evidence.field, {}).get("value") != evidence.value:
                    changed.append(evidence.field)
                state["draft_record"][evidence.field] = {
                    **value,
                    "source_kind": boundaries.source(state)["kind"],
                }
            elif evidence.field == "learning_response":
                state["learning_evidence"] = [
                    {"skill": SKILLS[lesson_id], "status": "完成一次引导下的示例回答", **value}
                ]
            else:
                state[evidence.field] = value
        if changed:
            state["domain_candidates"], state["pattern_review"] = [], None
            state["workflow"]["active_reflection"] = None
        return accepted, changed

    @staticmethod
    def _validated_signals(decision, latest, before_fields, changed):
        signals = []
        for signal in decision.assessment.signals:
            if signal.source_message_id != latest.get("id") or not faithful_excerpt(
                latest["content"], signal.quote
            ):
                raise RuntimeError("任务反馈信号没有有效的本轮原话来源。")
            item = signal.model_dump()
            old = before_fields.get(signal.target_field, {})
            if signal.kind == "potential_conflict":
                if signal.reference_message_id and signal.reference_message_id != old.get(
                    "source_message_id"
                ):
                    raise RuntimeError("冲突比较引用了不属于同一字段的旧消息。")
                item["comparable_context"] = bool(
                    signal.comparable_context
                    and old
                    and signal.reference_message_id == old.get("source_message_id")
                )
            item["replaces_existing"] = bool(old and signal.target_field in changed)
            signals.append(item)
        for kind, phrases in {
            "confusion": ("没听懂", "没明白", "不懂这个", "解释一下", "解释得太快"),
            "correction": ("记录错了", "不是这个意思", "我刚才说的是", "请改成"),
        }.items():
            phrase = next((phrase for phrase in phrases if phrase in latest["content"]), None)
            if phrase and not any(item["kind"] == kind for item in signals):
                signals.append(
                    {
                        "kind": kind,
                        "quote": phrase,
                        "source_message_id": latest.get("id"),
                        "source": "explicit_phrase_rule",
                    }
                )
        return signals

    def _reflect_and_guide(self, previous, updated, history, latest):
        workflow = updated["workflow"]
        start_id = workflow.get("last_reflection_message_id")
        start = next(
            (index + 1 for index, item in enumerate(history) if item.get("id") == start_id), 0
        )
        scope = history[start:][-24:]
        context = {
            "state_before": self._context(previous),
            "state_after": self._context(updated),
            "previous_reflection": next(
                (
                    note
                    for note in reversed(workflow["reflections"])
                    if note.get("case_id") == updated["case_id"]
                    and note.get("path") == updated.get("path")
                ),
                None,
            ),
            "trigger_decision": workflow["last_trigger"],
            "allowed_strategies": allowed_strategies(updated),
            "window_truncated": len(history[start:]) > 24,
        }
        result = self.agent.reflect(scope, context=context)
        reflection = result.decision.reflection
        source_roles = {item.get("id"): item.get("role") for item in scope if item.get("id")}
        if not set(reflection.source_message_ids).issubset(source_roles) or not any(
            source_roles.get(source) == "learner" for source in reflection.source_message_ids
        ):
            raise RuntimeError("反思没有可验证的学习者消息依据。")
        allowed_fields = set(
            blueprint.FIELDS if blueprint.enabled(updated) else required_fields(updated)
        ) | {"relationship_note", "mood", "learning_response", "goal", "feedback"}
        if reflection.focus_field is not None and reflection.focus_field not in allowed_fields:
            raise RuntimeError("反思指向了当前课程之外的字段。")
        if reflection.strategy not in context["allowed_strategies"] or (
            reflection.strategy == "clarify_missing_field"
            and reflection.focus_field not in practice_flow.missing(updated)
        ):
            raise RuntimeError("反思策略不适用于当前阶段或缺失字段。")
        if any(len(item) > 160 for item in reflection.open_items) or any(
            label in reflection.brief
            for label in ("诊断为", "人格障碍", "认知障碍", "理解能力差", "智力低")
        ):
            raise RuntimeError("反思包含不支持的个人标签或过长事项。")
        note = {
            **reflection.model_dump(),
            "id": str(uuid.uuid4()),
            "case_id": updated["case_id"],
            "stage": updated["stage"],
            "path": updated.get("path"),
            "task_step_id": task_step_id(updated),
            "ordinary_turn": workflow["ordinary_turns"],
            "scope_message_ids": [item["id"] for item in scope if item.get("id")],
            "applied": False,
            "validation_status": "unverified",
        }
        # Generated self-evaluation never turns an unknown outcome into a measured success.
        note["previous_strategy_result"] = "unknown"
        workflow["reflections"] = (workflow["reflections"] + [note])[-3:]
        workflow["last_reflection_message_id"] = latest.get("id")
        if reflection.update == "replace":
            workflow["active_reflection"] = note
        hint = active_guidance(updated)
        actor_context = {
            **self._context(updated),
            "strategy_instruction": (
                hint["instruction"] if hint else STRATEGY_INSTRUCTIONS["continue_current"]
            ),
            "reflection_brief": reflection.brief,
            "reflection_id": note["id"],
        }
        final = self.agent.guide(history[-6:], context=actor_context)
        note["generated_followup"] = True
        return final.decision.reply, True

    @staticmethod
    def _safe_reply(reply, state):
        cleaned = ATTACHMENT_PATTERN.sub("", reply.replace(COMPLETION_MARKER, "")).strip()
        if not cleaned or any(
            word in cleaned
            for word in ("本课已完成", "课程已完成", "已确认保存", "本课结束", "已经完全掌握")
        ):
            return next_question(state)
        return cleaned

    def _control(self, state: dict, latest: dict, action: str) -> str:
        if lesson2_flow.enabled(state) and action not in {
            "pause",
            "resume",
            "accept_carryover",
            "decline_carryover",
        }:
            return lesson2_flow.control(self, state, latest, action)
        stage, lesson_id = state["stage"], state["lesson_id"]
        if (
            action == "edit_learning_goal"
            and blueprint.enabled(state)
            and stage in {"plan", "summary", "learning_goal"}
        ):
            state["blueprint"]["goal_edit_base"] = copy.deepcopy(
                (state.get("learning_goal") or state.get("learning_goal_draft") or {}).get(
                    "items", []
                )
            )
            state.pop("learning_goal", None)
            state.pop("learning_goal_draft", None)
            state["stage"] = "learning_goal"
            state["practice_plan"] = {"status": "undecided", "text": ""}
            return "原目标确认已撤回，请说出您希望保留的新目标；课后安排稍后重新核对。"
        if action in practice_flow.CONTROL_LABELS:
            return practice_flow.control(state, latest, action)
        if action in learning_check.CONTROL_LABELS:
            if not learning_check.enabled(state):
                raise ValueError("本课没有这项检验或目标操作。")
            return learning_check.control(state, latest, action)
        if action == "pause":
            state["paused"] = True
            return "课程已暂停，当前记录已经保存。准备好时可以继续，也可以返回课程目录。"
        if action == "resume":
            if not state.get("paused"):
                raise ValueError("课程没有暂停。")
            state["paused"] = False
            return next_question(state)
        if action in {"accept_carryover", "decline_carryover"}:
            if stage != "check_in" or state["carryover"].get("status") != "offered":
                raise ValueError("当前没有可选择的上一课摘要。")
            if action == "accept_carryover":
                state["carryover"]["status"] = "accepted"
                if reusable_fields(state):
                    note = "本课会参考您已确认的上一课摘要。进入个人练习时，您可以明确选择沿用这件事，也可以聊新例子。"
                else:
                    note = "本课会参考您已确认的前课摘要。本课的安排会从您当前的回答重新整理。"
                return note + next_question(state)
            state["carryover"] = {"status": "declined"}
            return "好的，本课从新的例子开始。" + next_question(state)
        if action == "reuse_case":
            if not can_reuse_case(state):
                raise ValueError("当前不能沿用案例，请先选择摘要并进入个人练习。")
            summary = state["carryover"]["summary"]
            for key in reusable_fields(state):
                state["draft_record"][key] = {
                    "value": summary["record"][key]["value"],
                    "source_artifact_id": summary["artifact_id"],
                    "source_field": key,
                    "adopted_by_message_id": latest["id"],
                }
            if all(key in state["draft_record"] for key in required_fields(state)):
                state["stage"] = "review"
            return "我们接着您选择的这件事；记录哪里不再准确，都可以修改。" + next_question(state)
        if action == "skip_checkin" and stage == "check_in":
            if state["carryover"].get("status") == "offered":
                state["carryover"] = {"status": "declined"}
            state["stage"] = "learn"
        elif action == "edit_record" and stage in {"review", "plan", "summary"}:
            state["stage"], state["confirmed_record"], state["artifact"] = "practice", None, None
            state["practice_plan"] = {"status": "undecided", "text": ""}
            state["domain_candidates"], state["pattern_review"] = [], None
            state["workflow"]["active_reflection"] = None
            if learning_check.enabled(state):
                if practice_flow.enabled(state):
                    state["practice_flow"] = practice_flow.new_flow()
                if state["learning_check"]["answers"]:
                    state["previous_learning_checks"] = (
                        state.get("previous_learning_checks", [])
                        + [copy.deepcopy(state["learning_check"])]
                    )[-3:]
                state["learning_check"] = learning_check.new_check()
                for key in ("learning_result", "learning_goal", "learning_goal_draft"):
                    state.pop(key, None)
            return (
                "请告诉我哪一项需要修改，以及您希望保留的说法。修改后会重新请您核对记录与课后安排。"
            )
        elif action == "confirm_record" and stage == "review":
            if not practice_flow.ready(state):
                raise ValueError("必要记录尚未齐全，暂时不能确认。")
            state["confirmed_record"] = {
                "fields": copy.deepcopy(state["draft_record"]),
                "confirmation_message_id": latest["id"],
                "revision": state["revision"] + 1,
                "path": state.get("path"),
                "pattern_review": copy.deepcopy(state.get("pattern_review")),
                "source_kind": boundaries.source(state)["kind"],
                "case_id": state["case_id"],
                "practice_source": copy.deepcopy(boundaries.source(state)),
            }
            if practice_flow.enabled(state):
                state["confirmed_record"]["deferred_fields"] = copy.deepcopy(
                    state["practice_flow"]["deferred"]
                )
                state["confirmed_record"]["practice_scope"] = practice_flow.scope(state)
            if blueprint.enabled(state):
                state["confirmed_record"]["blueprint"] = blueprint.payload(state)
            if learning_check.enabled(state):
                return learning_check.begin(state)
            state["stage"] = "plan"
        elif action in {"accept_practice", "decline_practice"} and stage == "plan":
            state["practice_plan"] = {
                "status": "accepted" if action == "accept_practice" else "declined",
                "text": (
                    PRACTICE_PLANS[lesson_id]
                    if action == "accept_practice"
                    else "本次选择不安排课后练习。"
                ),
                "source_message_id": latest["id"],
            }
            if action == "accept_practice" and (
                boundaries.blocked(state) or boundaries.fictional(state)
            ):
                state["practice_plan"][
                    "text"
                ] = "愿意时，用一个新的虚构例子回看本课方法；可以随时停下或调整，实际运用尚未测量。"
            state["stage"] = "summary"
        elif (
            action == "finish"
            and stage == "summary"
            and state.get("confirmed_record")
            and state["practice_plan"]["status"] in {"accepted", "declined"}
        ):
            if learning_check.enabled(state) and (
                state["learning_check"]["status"] != "completed" or not state.get("learning_goal")
            ):
                raise ValueError("请先完成或明确跳过检验题，并确认或跳过练习目标。")
            state["completed"] = True
            record = state["confirmed_record"]
            state["artifact"] = {
                "artifact_id": f"{state.get('conversation_id', 'local')}:record:{record['revision']}",
                "schema_version": "course-artifact/2",
                "lesson_id": lesson_id,
                "lesson_version": state["lesson_version"],
                "kind": "learning_record",
                "path": state.get("path"),
                "application_status": "not_measured",
                "referenced_artifact_ids": (
                    [
                        item["summary"]["artifact_id"]
                        for item in state["carryover"].get("sources", [])
                    ]
                    if state["carryover"].get("status") == "accepted"
                    else []
                ),
                "record": copy.deepcopy(record),
                "practice_plan": copy.deepcopy(state["practice_plan"]),
                "learning_evidence": copy.deepcopy(state["learning_evidence"]),
            }
            if learning_check.enabled(state):
                state["learning_result"] = {
                    **learning_check.report(state),
                    "personal_record": (
                        None if boundaries.fictional(state) else copy.deepcopy(record)
                    ),
                    "guided_practice_result": (
                        copy.deepcopy(record) if boundaries.fictional(state) else None
                    ),
                    "learning_goal": copy.deepcopy(state["learning_goal"]),
                }
                state["artifact"]["learning_result"] = copy.deepcopy(state["learning_result"])
            state["reflection"] = {
                "status": "pending",
                "observations": [],
                "suggestions": [],
                "applied": False,
            }
            return "本课已完成。您的学习记录和课后选择已经保存；课后教学复盘会单独整理，不改变您的原话。"
        else:
            raise ValueError("当前阶段不能执行这个操作，请先完成眼前的练习。")
        return next_question(state)

    def _navigate(self, state, history, latest, before):
        if self.agent is None:
            self.agent = FreeformCourseAgent(system_prompt=prompt_for_lesson(state["lesson_id"]))
            self.agent.call_log = self.model_calls
        try:
            result = self.agent.navigate(
                history[-12:],
                context={
                    "stage": state["stage"],
                    "dialogue_policy": state.get("dialogue_policy"),
                    "learning_goal_draft": state.get("learning_goal_draft")
                    or state.get("learning_goal")
                    or {"items": state.get("blueprint", {}).get("goal_edit_base", [])},
                    "practice_plan": state["practice_plan"],
                    "goal_edit_candidate": blueprint.enabled(state)
                    and bool(
                        re.search(
                            r"第[一二三四五1-5][项个条]|修改.{0,6}目标|调整.{0,6}目标",
                            latest["content"],
                        )
                    ),
                    "blueprint_goal": (
                        state["blueprint"].get("goal_step") if blueprint.enabled(state) else None
                    ),
                },
            )
            decision = result.decision
            navigation.validate(decision, state, latest)
            proposed = copy.deepcopy(state)
            if decision.intent == "goal":
                if proposed["stage"] == "check_feedback":
                    self._control(proposed, latest, "continue_after_check")
                base_goals = copy.deepcopy(
                    (
                        proposed.get("learning_goal") or proposed.get("learning_goal_draft") or {}
                    ).get("items", [])
                    or proposed.get("blueprint", {}).get("goal_edit_base", [])
                )
                if blueprint.enabled(proposed) and proposed["stage"] != "learning_goal":
                    self._control(proposed, latest, "edit_learning_goal")
                if blueprint.enabled(proposed) and decision.goal_updates:
                    if decision.goal_items:
                        raise ValueError("Cannot replace and update goals in the same decision")
                    reply = blueprint.revise_goals(
                        proposed, latest, decision.goal_updates, base_goals
                    )
                else:
                    reply = (
                        blueprint.goal_answer(
                            proposed, latest, decision.goal_items, decision.goal_level
                        )
                        if blueprint.enabled(proposed)
                        else learning_check.goal_answer(proposed, latest)
                    )
            elif decision.intent == "clarify":
                reply = decision.reply or "您是想继续当前安排，还是跳过这个可选环节？"
            else:
                replies = [
                    self._control(proposed, latest, item.action) for item in decision.actions
                ]
                reply = replies[-1]
                if len(replies) > 1:
                    goal_note = (
                        "目标已按您的确认保存。"
                        if decision.actions[0].action == "confirm_learning_goal"
                        else "本次暂不设置目标。"
                    )
                    plan_note = (
                        "课后练习已安排为待尝试。"
                        if decision.actions[1].action == "accept_practice"
                        else "本次不安排课后练习。"
                    )
                    reply = goal_note + plan_note + reply
            if dialogue.enabled(proposed) and decision.intent != "clarify":
                reply = dialogue.navigation_reply(decision.reply, reply)
            proposed["workflow"]["last_trigger"] = {
                "triggered": False,
                "reason_codes": ["natural_language_navigation"],
            }
            return self._result(
                proposed,
                reply,
                before,
                completion=result.completion,
                action="course_navigation",
                navigation_event={"status": "accepted", **decision.model_dump()},
            )
        except (ValueError, RuntimeError, OSError) as exc:
            return self._result(
                state,
                "这次没能确定您的推进意图，当前环节先保留。您可以重新说一下，也可以使用旁边的操作继续。",
                before,
                action="course_navigation",
                navigation_event={"status": "failed", "error_type": type(exc).__name__},
            )

    def _result(
        self, state: dict, reply: str, before: str, *, completion=None, safety=None, **extra
    ) -> TurnResult:
        if (
            blueprint.enabled(state)
            and state["stage"] == "review"
            and not safety
            and not state.get("paused")
        ):
            from cbt_course_llm_freeform import case_review

            fingerprint = case_review.fingerprint(state)
            recap = state["blueprint"].get("case_review", {})
            if state["draft_record"] and recap.get("fingerprint") != fingerprint:
                try:
                    if self.agent is None:
                        self.agent = FreeformCourseAgent(
                            system_prompt=prompt_for_lesson("lesson-1")
                        )
                        self.agent.call_log = self.model_calls
                    if not isinstance(self.agent, FreeformCourseAgent):
                        raise RuntimeError("Case recap adapter unavailable")
                    self.agent.call_log = self.model_calls
                    output, review_completion = case_review.generate(self.agent, state)
                    recap = {"status": "ready", "fingerprint": fingerprint, **output}
                    if completion is None:
                        completion = review_completion
                except Exception as exc:
                    recap = {
                        "status": "failed",
                        "fingerprint": fingerprint,
                        "error_type": type(exc).__name__,
                    }
                    if self.model_calls and self.model_calls[-1].get("phase") == "case_review":
                        self.model_calls[-1].update(status="error", error_type=type(exc).__name__)
                state["blueprint"]["case_review"] = recap
                extra["case_review_event"] = copy.deepcopy(recap)
                natural = blueprint.review_text(state, invite=before != "review")
                if not dialogue.enabled(state):
                    reply = (
                        reply + "\n" + natural
                        if extra.get("action")
                        in {"interaction_feedback", "interaction_feedback_failed"}
                        else natural
                    )
            # Track delivery by case content, including pause/refresh/resume paths.
            # This is an invitation marker, never learner confirmation or a finding.
            state["blueprint"]["review_invited_for"] = fingerprint
        state["revision"] += 1
        state["turn_count"] += 1
        state["workflow"]["last_model_call_count"] = len(self.model_calls)
        return TurnResult(
            reply=reply,
            state=state,
            completion=completion,
            safety_event=safety,
            trace={
                "implementation": IMPLEMENTATION,
                "stage_from": before,
                "stage_to": state["stage"],
                "path": state.get("path"),
                "case_id": state.get("case_id"),
                "task_step_id": task_step_id(state),
                "completed": state["completed"],
                "model_called": bool(self.model_calls),
                "personal_practice": practice_flow.payload(state),
                "interaction_feedback": copy.deepcopy(
                    state.get("practice_flow", {}).get("interaction_feedback")
                ),
                "interaction_event": copy.deepcopy(state.get("latest_interaction_event")),
                "boundary_event": copy.deepcopy(state.get("boundary_event")),
                "practice_source": copy.deepcopy(boundaries.source(state)),
                "interaction_guidance": interaction.guidance(state),
                "interaction_guidance_delivery": (
                    "event_reply"
                    if extra.get("action") == "interaction_feedback"
                    else (
                        "program_reply"
                        if interaction.guidance(state)
                        and practice_flow.enabled(state)
                        and not boundaries.enabled(state)
                        and state["stage"] == "practice"
                        else (
                            "model_context"
                            if interaction.guidance(state)
                            and any(
                                call.get("phase") in {"teaching", "lesson2_teaching"}
                                for call in self.model_calls
                            )
                            else "not_applied"
                        )
                    )
                ),
                "model_calls": copy.deepcopy(self.model_calls),
                **extra,
            },
        )
