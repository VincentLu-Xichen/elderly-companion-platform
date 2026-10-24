from __future__ import annotations

import json
import unittest
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cbt_course_llm_freeform import practice_flow
from cbt_course_llm_freeform.agent import FreeformCourseAgent
from cbt_course_llm_freeform.preview import PreviewClient
from cbt_course_llm_freeform.prompt import prompt_for_lesson
from cbt_course_llm_freeform.runtime import FreeformCourseRuntime, course_payload, new_course_state
from cbt_course_llm_freeform.schemas import AgentResult, TeachingDecision
from cbt_course_llm_freeform.services import create_or_resume_course, process_course_turn, AGENT_VERSION
from cbt_course_llm_freeform.memory import offer_previous_summary
from cbt_course_llm_freeform.reflection import generate_course_reflection
from daily_agent.azure_chat_client import ChatCompletionResult
from webapp.database import Base
from webapp.models import Participant, Message
from webapp.security import decrypt_json, encrypt_text, hash_secret


class DecisionAgent:
    def lesson2_turn(self, history, *, context):
        from cbt_course_llm_freeform.lesson2_flow import Decision
        from cbt_course_llm_freeform.schemas import StageResult
        self.context = context
        return StageResult(completion=None, decision=Decision(reply="先保留当前记录。"))
    def __init__(self, observations=()):
        self.observations = list(observations)
        self.calls = 0

    def reply(self, history, *, context):
        self.calls += 1
        self.context = context
        return AgentResult(reply="会不会撞到人？身体一紧也算。", decision=TeachingDecision(
            reply="会不会撞到人？身体一紧也算。", observations=self.observations))


def turn(state, text="", action="chat", agent=None, message_id=None):
    return FreeformCourseRuntime(agent=agent).process(state, [{"id": message_id or uuid.uuid4().hex,
        "role": "learner", "content": text or action}], action=action)


class PracticeFlowTests(unittest.TestCase):
    def practice(self):
        state = new_course_state("lesson-1", reflection_policy="none")
        state.pop("blueprint")  # Explicit historical four-field fixture.
        state["stage"] = "practice"
        return state

    def test_cross_field_answer_is_kept_but_unanswered_focus_is_bounded(self):
        state = self.practice()
        state.pop("privacy")  # Historical bounded-template behavior, not the new model-led practice.
        state["draft_record"]["situation"] = {"value": "听到砰的一声", "source_message_id": "s"}
        agent = DecisionAgent([{"field": "emotion", "value": "很吓人", "source_message_id": "e"}])
        first = turn(state, "很吓人", agent=agent, message_id="e")
        self.assertEqual(first.state["draft_record"]["emotion"]["value"], "很吓人")
        self.assertIn("脑中的解释或判断", first.reply)
        self.assertNotIn("撞到人", first.reply)
        self.assertNotIn("身体一紧", first.reply)
        second = turn(first.state, "就是这样", agent=DecisionAgent(), message_id="no-thought")
        self.assertEqual(second.state["practice_flow"]["deferred"]["thought"],
                         {"status": "not_observed", "source_message_ids": ["e", "no-thought"]})
        self.assertEqual(course_payload(second.state)["personal_practice"]["current_field"], "behavior")
        self.assertIn("做了什么", second.reply)
        self.assertNotIn("thought", second.state["draft_record"])
        self.assertEqual(state["practice_flow"]["deferred"], {})

    def test_explicit_deferral_has_no_model_call_and_preserves_distinct_reasons(self):
        state, agent = self.practice(), DecisionAgent()
        first = turn(state, action="defer_practice_field", agent=agent, message_id="skip")
        second = turn(first.state, "这一项先不谈", agent=agent, message_id="decline")
        self.assertEqual(agent.calls, 0)
        self.assertEqual(first.trace["model_calls"], [])
        self.assertEqual(second.state["draft_record"], {})
        self.assertEqual(second.state["practice_flow"]["deferred"]["thought"]["status"], "withheld")
        self.assertEqual(first.state["practice_flow"]["deferred"]["situation"]["status"], "not_recalled")
        for lesson, stage in (("lesson-2", "practice"), ("lesson-1", "learn"), ("lesson-1", "review")):
            other = new_course_state(lesson); other["stage"] = stage
            with self.subTest(lesson=lesson, stage=stage), self.assertRaises(ValueError):
                turn(other, action="defer_practice_field", agent=agent)

    def test_mixed_sentence_is_not_treated_as_a_skip(self):
        text = "我想不起来当时的念头，但后来回家了"
        self.assertIsNone(practice_flow.explicit_action(text))
        self.assertEqual(practice_flow.explicit_action("我想不起来。"), "defer_practice_field")

    def test_all_deferred_can_be_confirmed_checked_and_completed_without_fake_facts(self):
        state = self.practice()
        for _ in range(4):
            state = turn(state, action="defer_practice_field").state
        self.assertEqual(state["stage"], "review")
        self.assertEqual(course_payload(state)["personal_practice_scope"]["status"], "not_observed")
        state = turn(state, action="confirm_record").state
        self.assertEqual(state["stage"], "assessment")
        for _ in range(4):
            state = turn(state, action="skip_check_question").state
        for action in ("continue_after_check", "skip_learning_goal", "decline_practice", "finish"):
            state = turn(state, action=action).state
        self.assertTrue(state["completed"])
        record = state["artifact"]["record"]
        self.assertEqual(record["fields"], {})
        self.assertEqual(len(record["deferred_fields"]), 4)
        self.assertEqual(state["learning_result"]["personal_practice_scope"]["status"], "not_observed")
        self.assertTrue(all(item["verdict"] == "not_observed" for item in state["learning_check"]["answers"]))

    def test_edit_reopens_deferred_fields_and_new_evidence_restores_a_real_record(self):
        state = self.practice()
        state["draft_record"] = {key: {"value": key, "source_message_id": key} for key in ("situation", "emotion", "behavior")}
        state = turn(state, action="defer_practice_field").state
        state = turn(state, action="edit_record").state
        self.assertEqual(practice_flow.current_field(state), "thought")
        self.assertEqual(state["practice_flow"]["deferred"], {})
        result = turn(state, "我以为出了什么事", message_id="new", agent=DecisionAgent([
            {"field": "thought", "value": "我以为出了什么事", "source_message_id": "new"}]))
        self.assertEqual(result.state["stage"], "review")
        self.assertEqual(result.state["draft_record"]["thought"]["source_message_id"], "new")
        self.assertEqual(practice_flow.scope(result.state)["status"], "complete_record")

    def test_reflection_and_streaming_cannot_override_task_boundaries(self):
        class NoDraftStream(PreviewClient):
            def stream_with_metadata(self, *args, **kwargs):
                raise AssertionError("Personal-practice drafts must not stream")
        for policy, expected_calls in (("none", 1), ("per_turn", 3)):
            state = self.practice(); state["workflow"]["policy"] = policy
            fragments = []
            runtime = FreeformCourseRuntime(agent=FreeformCourseAgent(client=NoDraftStream(),
                system_prompt=prompt_for_lesson("lesson-1")), on_reply=fragments.append)
            result = runtime.process(state, [{"id": "s", "role": "learner", "content": "事情：今天下雨了"}])
            self.assertEqual(fragments, [])
            self.assertIn("脑中", result.reply)
            self.assertEqual(len(runtime.model_calls), expected_calls)
            self.assertEqual(result.state["stage"], "practice")

    def test_stage_focus_tracks_nine_stages_retry_and_other_lessons(self):
        state = self.practice()
        from cbt_course_llm_freeform.learning_check import STAGES
        for stage in STAGES:
            state["stage"] = stage
            focus = course_payload(state)["stage_focus"]
            self.assertEqual(set(focus), {"task", "purpose", "exit"})
        state["stage"] = "check_feedback"; state["learning_check"]["retry"]["status"] = "active"
        self.assertIn("再练", course_payload(state)["stage_focus"]["task"])
        self.assertEqual(set(course_payload(new_course_state("lesson-2"))["stage_focus"]), {"task", "purpose", "exit"})


class PracticeFlowPersistenceTests(unittest.TestCase):
    def test_partial_record_survives_reload_dedup_and_authorized_summary(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine, expire_on_commit=False)
        try:
            with Session() as db:
                person = Participant(label=uuid.uuid4().hex, invite_hash=hash_secret("code"))
                db.add(person); db.commit()
                conversation, _ = create_or_resume_course(db, participant_id=person.id, lesson_id="lesson-1")
                factory = lambda: FreeformCourseRuntime(agent=FreeformCourseAgent(client=PreviewClient()))
                def send(text="", action="chat", key=None):
                    return process_course_turn(db, conversation, content=text, action=action,
                        idempotency_key=key or uuid.uuid4().hex, runtime_factory=factory)
                send(action="skip_checkin"); send("这是想法")
                send("事情：今天下雨了")
                send("一直让我解释，感觉像审问", action="request_less_probing", key="feedback-pilot")
                feedback_before = decrypt_json(conversation.agent_state_encrypted)
                self.assertTrue(send("一直让我解释，感觉像审问", action="request_less_probing", key="feedback-pilot")["deduplicated"])
                self.assertEqual(decrypt_json(conversation.agent_state_encrypted), feedback_before)
                send(action="continue_practice_dialogue")
                send(action="defer_practice_field", key="one-skip")
                before = decrypt_json(conversation.agent_state_encrypted)
                replay = send(action="defer_practice_field", key="one-skip")
                self.assertTrue(replay["deduplicated"])
                self.assertEqual(decrypt_json(conversation.agent_state_encrypted), before)
                self.assertNotIn("今天下雨", conversation.agent_state_encrypted)
                send("心情：有点失望；做法：回家看书")
                send(action="defer_practice_field")
                send(action="defer_practice_field")
                send(action="confirm_record")
                for _ in range(4): send(action="skip_check_question")
                for action in ("continue_after_check", "skip_learning_goal", "decline_practice", "finish"): send(action=action)
                db.expire_all()
                state = decrypt_json(conversation.agent_state_encrypted)
                self.assertEqual(state["confirmed_record"]["deferred_fields"]["thought"]["status"], "not_recalled")
                summary = offer_previous_summary(db, person.id, AGENT_VERSION, "lesson-2")["summary"]
                self.assertNotIn("thought", summary["record"])
                self.assertEqual(summary["practice_scope"]["status"], "partial_record")
                self.assertEqual(summary["record"]["situation"]["value"], "今天下雨了")
                foreign = offer_previous_summary(db, "different-person", AGENT_VERSION, "lesson-2")
                self.assertEqual(foreign["status"], "unavailable")
                events = list(conversation.turn_events)
                self.assertTrue(all(event.status == "success" for event in events))
                # Required omission sources survive even when outside the recent-40 window.
                deferred_id = state["confirmed_record"]["deferred_fields"]["thought"]["source_message_ids"][0]
                sequence = max(item.sequence for item in conversation.messages)
                for index in range(45):
                    db.add(Message(conversation_id=conversation.id, sequence=sequence + index + 1,
                        role="agent", content_encrypted=encrypt_text("回顾材料")))
                db.commit()
                test = self
                class ReflectionClient:
                    def complete_with_metadata(self, messages, **kwargs):
                        data = json.loads(messages[-1]["content"])
                        test.assertIn(deferred_id, {item["id"] for item in data["history"]})
                        interaction = data["learning_result"]["interaction_feedback"]
                        test.assertEqual(interaction["effect"], "not_measured")
                        for source in (interaction["source_message_id"], interaction["choice"]["source_message_id"]):
                            test.assertIn(source, {item["id"] for item in data["history"]})
                        test.assertEqual(data["learner_record"]["practice_scope"]["status"], "partial_record")
                        return ChatCompletionResult(text=json.dumps({"observations": [], "suggestions": [],
                            "hypotheses": [{"text": "本次想法一项暂留，指导方式仍待核对。", "source_message_ids": [deferred_id],
                                "context": "本次个人练习", "alternative_explanation": "也可能是问题表达不清楚。",
                                "next_action": "下次先说明提问目的。", "verification": "用新例子观察是否更清楚。"}]}, ensure_ascii=False), finish_reason="stop")
                generate_course_reflection(conversation.id, session_factory=Session, client=ReflectionClient())
                db.refresh(conversation)
                after_reflection = decrypt_json(conversation.agent_state_encrypted)
                self.assertEqual(after_reflection["reflection"]["status"], "ready")
                self.assertEqual(after_reflection["confirmed_record"], state["confirmed_record"])
        finally:
            engine.dispose()
