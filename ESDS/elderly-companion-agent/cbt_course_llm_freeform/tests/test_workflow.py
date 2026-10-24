from __future__ import annotations

import copy
import json
import unittest
import uuid
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from cbt_course_llm_freeform.agent import FreeformCourseAgent
from cbt_course_llm_freeform.design import PREVIEW_EXAMPLES
from cbt_course_llm_freeform.feedback import POLICIES, active_guidance
from cbt_course_llm_freeform.preview import PreviewClient
from cbt_course_llm_freeform.prompt import prompt_for_lesson
from cbt_course_llm_freeform.tests.shared_turn_fixture import shared_state
from cbt_course_llm_freeform.runtime import FreeformCourseRuntime, new_course_state
from cbt_course_llm_freeform.services import AGENT_VERSION, create_or_resume_course, process_course_turn, course_conversation_payload
from webapp.database import Base
from webapp.models import Conversation, Message, Participant, TurnEvent
from webapp.security import decrypt_json, encrypt_json, hash_secret


def runtime_for(client=None, lesson="lesson-1"):
    return FreeformCourseRuntime(agent=FreeformCourseAgent(client=client or PreviewClient(), system_prompt=prompt_for_lesson(lesson)))


def one_turn(state, text, client=None):
    return runtime_for(client, state["lesson_id"]).process(state, [{"id": "previous-guide", "role": "agent", "content": "请说说当前例子。"}, {"id": "current-answer", "role": "learner", "content": text}])


class WorkflowRuntimeTests(unittest.TestCase):
    def test_all_policies_keep_the_same_valid_record_updates(self):
        values = []
        for policy in POLICIES:
            state = new_course_state("lesson-1", reflection_policy=policy)
            state["stage"] = "practice"
            result = one_turn(state, "事情：昨天下雨了")
            values.append(result.state["draft_record"])
            expected = 3 if policy in {"per_turn", "per_task_step"} else 1
            self.assertEqual(len(result.trace["model_calls"]), expected)
            self.assertEqual(result.state["stage"], "practice")
        self.assertTrue(all(record == values[0] for record in values))

    def test_event_trigger_reflection_precedes_final_actor(self):
        state = shared_state(reflection_policy="event_driven")
        state["stage"] = "learn"
        result = one_turn(state, "没听懂，可以换个说法吗？")
        self.assertEqual([call["phase"] for call in result.trace["model_calls"]], ["teaching", "guidance_reflection", "guidance_actor"])
        self.assertEqual(result.state["stage"], "learn")
        self.assertEqual(result.state["workflow"]["reflections"][-1]["strategy"], "rephrase_plainly")
        self.assertIn("换种生活里的说法", result.reply)
        self.assertFalse(result.state["workflow"]["reflections"][-1]["applied"])

    def test_task_step_can_span_multiple_turns(self):
        state = new_course_state("lesson-1", reflection_policy="per_task_step")
        state["stage"] = "learn"
        first = one_turn(state, "我还没听懂")
        self.assertFalse(first.trace["trigger"]["triggered"])
        second = one_turn(first.state, "这是他的想法，失落是心情。")
        self.assertTrue(second.trace["trigger"]["triggered"])
        self.assertEqual(second.trace["trigger"]["reason_codes"], ["task_step_finished"])

    def test_reasonable_uncertainty_is_not_confusion(self):
        state = shared_state(reflection_policy="event_driven")
        state["stage"] = "learn"
        result = one_turn(state, PREVIEW_EXAMPLES["lesson-2"]["learn"])
        self.assertEqual(result.state["stage"], "practice")
        self.assertFalse(result.trace["trigger"]["triggered"])

    def test_stall_uses_task_progress_not_time_or_emotion(self):
        # Lesson 1 now advances past an unresolved field after one clarification.
        # Keep testing repeated stalls on the unchanged lesson-2 workflow.
        state = shared_state(reflection_policy="event_driven")
        state["stage"] = "practice"
        class NoProgress(PreviewClient):
            @staticmethod
            def _teaching(context, latest):
                return {"reply": "可以慢慢说。", "observations": [], "advance": False}
        first = one_turn(state, "暂时不想展开", NoProgress())
        second = one_turn(first.state, "还是暂时不想展开", NoProgress())
        self.assertFalse(first.trace["trigger"]["triggered"])
        self.assertEqual(second.trace["trigger"]["reason_codes"], ["repeated_no_progress"])
        self.assertEqual(second.state["draft_record"], {})

    def test_incomparable_context_does_not_trigger_conflict(self):
        state = shared_state(reflection_policy="event_driven")
        state["stage"] = "practice"
        state["draft_record"]["emotion"] = {"value": "开心", "source_message_id": "old-answer"}
        class DifferentQuestion(PreviewClient):
            @staticmethod
            def _teaching(context, latest):
                return {"reply": "这是另一件事。", "assessment": {"signals": [{"kind": "potential_conflict", "quote": latest["text"], "source_message_id": latest["id"], "target_field": "emotion", "reference_message_id": "old-answer", "comparable_context": False}]}}
        result = one_turn(state, "说到另一件事情，我有点担心", DifferentQuestion())
        self.assertFalse(result.trace["trigger"]["triggered"])

    def test_truncated_negation_is_rejected(self):
        state = new_course_state("lesson-1")
        state["stage"] = "practice"
        class Truncated(PreviewClient):
            @staticmethod
            def _teaching(context, latest):
                return {"reply": "继续。", "observations": [{"field": "emotion", "value": "难过", "source_message_id": latest["id"]}]}
        with self.assertRaises(RuntimeError):
            one_turn(state, "我不是难过，是担心", Truncated())
        self.assertEqual(state["draft_record"], {})

    def test_unsupported_pattern_does_not_become_a_fact(self):
        state = shared_state()
        state["stage"] = "practice"
        class ForgedPattern(PreviewClient):
            @staticmethod
            def _teaching(context, latest):
                return {"reply": "继续。", "domain_candidates": [{"category": "mind_reading", "basis_field": "thought", "basis_quote": "没有人喜欢我", "explanation": "一个解释"}]}
        with self.assertRaises(RuntimeError):
            one_turn(state, "还没想好", ForgedPattern())
        self.assertEqual(state["domain_candidates"], [])

    def test_reflection_cannot_ask_for_an_already_recorded_field(self):
        state = new_course_state("lesson-1", reflection_policy="per_turn")
        state["stage"] = "practice"
        class StaleFocus(PreviewClient):
            @staticmethod
            def _reflection(context, latest):
                output = PreviewClient._reflection(context, latest)
                output["reflection"].update(strategy="clarify_missing_field", focus_field="situation")
                return output
        with self.assertRaises(RuntimeError):
            one_turn(state, "事情：昨天下雨了", StaleFocus())
        self.assertEqual(state["draft_record"], {})

    def test_old_confirmation_strategy_does_not_survive_stage_change(self):
        state = new_course_state("lesson-1")
        state["stage"] = "plan"
        state["workflow"]["active_reflection"] = {"id": "old", "stage": "plan", "case_id": state["case_id"],
            "ordinary_turn": 0, "strategy": "summarize_for_confirmation", "focus_field": None}
        self.assertIsNone(active_guidance(state))


class WorkflowPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.db = self.Session()
        self.person = Participant(label=uuid.uuid4().hex, invite_hash=hash_secret("offline-test"))
        self.db.add(self.person); self.db.commit()

    def tearDown(self):
        self.db.close(); self.engine.dispose()

    def start(self, lesson="lesson-1", policy="none"):
        with patch.dict("os.environ", {"CBT_REFLECTION_POLICY": policy}):
            conversation = create_or_resume_course(self.db, participant_id=self.person.id, lesson_id="lesson-1" if lesson == "shared-test" else lesson)[0]
            if lesson == "shared-test":
                from webapp.security import encrypt_json
                state = shared_state(reflection_policy=policy)
                state["conversation_id"] = conversation.id
                conversation.agent_state_encrypted = encrypt_json(state)
                self.db.commit()
            return conversation

    def turn(self, conversation, content="", action="chat", client=None, key=None):
        return process_course_turn(self.db, conversation, content=content, action=action, idempotency_key=key or uuid.uuid4().hex,
            runtime_factory=lambda: runtime_for(client, conversation.lesson_id))

    def prepare_review(self, lesson="lesson-1"):
        conversation = self.start(lesson)
        if lesson == "lesson-2":
            from cbt_course_llm_freeform.tests.lesson2_helpers import prepare
            prepare(lambda text="", action="chat": self.turn(conversation, text, action=action))
            return conversation
        self.turn(conversation, action="skip_checkin")
        self.turn(conversation, PREVIEW_EXAMPLES[lesson]["learn"])
        result = self.turn(conversation, PREVIEW_EXAMPLES[lesson]["practice"])
        if lesson == "lesson-1" and result["course"]["current_step"] == "practice":
            self.turn(conversation, "6分")
            result = self.turn(conversation, "5分")
        self.assertEqual(result["course"]["current_step"], "review")
        return conversation

    def finish(self, lesson="lesson-1", choice="unsure_pattern"):
        conversation = self.prepare_review(lesson)
        self.turn(conversation, action="confirm_record")
        if lesson == "lesson-1":
            from cbt_course_llm_freeform.tests.check_helpers import complete_first_check
            complete_first_check(lambda text="", action="chat": self.turn(conversation, text, action=action))
        self.turn(conversation, action="decline_practice")
        self.turn(conversation, action="finish")
        return conversation

    def test_both_lessons_complete_without_predecessors_and_keep_artifacts(self):
        for lesson in ("lesson-2", "lesson-1"):
            conversation = self.finish(lesson)
            state = decrypt_json(conversation.agent_state_encrypted)
            self.assertEqual(conversation.status, "completed")
            self.assertIn(conversation.id, state["artifact"]["artifact_id"])
            self.assertNotIn("女儿", conversation.agent_state_encrypted)



    def test_confirmed_record_can_be_explicitly_revised_before_finish(self):
        conversation = self.prepare_review()
        self.turn(conversation, action="confirm_record")
        from cbt_course_llm_freeform.tests.check_helpers import complete_first_check
        complete_first_check(lambda text="", action="chat": self.turn(conversation, text, action=action))
        self.turn(conversation, action="decline_practice")
        self.turn(conversation, action="edit_record")
        state = decrypt_json(conversation.agent_state_encrypted)
        self.assertIsNone(state["confirmed_record"])
        self.assertEqual(state["practice_plan"]["status"], "undecided")
        self.turn(conversation, "心情：担心")
        self.turn(conversation, "5分")  # Changed emotion invalidates its previous intensity.
        self.turn(conversation, action="confirm_record")
        self.assertEqual(decrypt_json(conversation.agent_state_encrypted)["confirmed_record"]["fields"]["emotion"]["value"], "担心")

    def test_policy_is_frozen_on_resume(self):
        conversation = self.start(policy="per_turn")
        same = self.start(policy="none")
        self.assertEqual(same.id, conversation.id)
        self.assertEqual(decrypt_json(same.agent_state_encrypted)["workflow"]["policy"], "per_turn")

    def test_actor_failure_is_atomic_audited_and_same_key_retryable(self):
        conversation = self.start("shared-test", policy="per_turn")
        original = copy.deepcopy(decrypt_json(conversation.agent_state_encrypted))
        class FailedActor(PreviewClient):
            def complete_with_metadata(self, messages, **kwargs):
                if "COURSE_GUIDANCE_ACTOR" in messages[0]["content"]:
                    raise RuntimeError("simulated actor failure")
                return super().complete_with_metadata(messages, **kwargs)
        with self.assertRaises(RuntimeError):
            self.turn(conversation, "最近六分", client=FailedActor(), key="same-step-retry")
        self.db.refresh(conversation)
        self.assertEqual(decrypt_json(conversation.agent_state_encrypted), original)
        event = self.db.scalar(select(TurnEvent).where(TurnEvent.conversation_id == conversation.id))
        failure = decrypt_json(event.trace_encrypted)["failed_attempts"][0]
        self.assertEqual([item["phase"] for item in failure["model_calls"]], ["teaching", "guidance_reflection", "guidance_actor"])
        result = self.turn(conversation, "最近六分", key="same-step-retry")
        self.assertEqual(result["course"]["current_step"], "learn")
        state = decrypt_json(conversation.agent_state_encrypted)
        self.assertTrue(state["workflow"]["reflections"][-1]["applied"])
        self.assertEqual(len(self.db.scalars(select(Message).where(Message.conversation_id == conversation.id)).all()), 3)
        self.db.refresh(event)
        trace = decrypt_json(event.trace_encrypted)
        self.assertEqual(len(trace["failed_attempts"]), 1)
        self.assertEqual(len(trace["model_calls"]), 3)
        replay = self.turn(conversation, "最近六分", key="same-step-retry")
        self.assertTrue(replay["deduplicated"])

    def test_forged_reflection_does_not_commit_valid_observation(self):
        conversation = self.start("shared-test", policy="per_turn")
        original = decrypt_json(conversation.agent_state_encrypted)
        class BadSource(PreviewClient):
            @staticmethod
            def _reflection(context, latest):
                output = PreviewClient._reflection(context, latest)
                output["reflection"]["source_message_ids"] = ["foreign-source"]
                return output
        with self.assertRaises(RuntimeError):
            self.turn(conversation, "最近六分", client=BadSource())
        self.db.refresh(conversation)
        self.assertEqual(decrypt_json(conversation.agent_state_encrypted), original)

    def test_reflection_audit_survives_the_three_note_context_window(self):
        conversation = self.start("shared-test", policy="per_turn")
        for index in range(4):
            self.turn(conversation, f"第{index + 1}次还是没听懂", key=f"reflection-audit-{index}")
        state = decrypt_json(conversation.agent_state_encrypted)
        self.assertEqual(len(state["workflow"]["reflections"]), 3)
        event = self.db.scalar(select(TurnEvent).where(TurnEvent.conversation_id == conversation.id, TurnEvent.idempotency_key == "reflection-audit-0"))
        saved = decrypt_json(event.trace_encrypted)["guidance_reflection"]
        self.assertTrue(saved["applied"])
        self.assertEqual(saved["applied_to_message_id"], event.assistant_message_id)
        self.assertNotIn(saved["id"], [item["id"] for item in state["workflow"]["reflections"]])

    def test_v1_is_read_only_and_new_start_has_a_new_identity(self):
        old = self.start()
        old.agent_version, old.lesson_version = "course-guided-v1", "3.0-guided-record"
        self.db.commit()
        with self.assertRaises(ValueError):
            self.turn(old, "不能继续旧协议")
        current = self.start()
        self.assertNotEqual(current.id, old.id)
        self.assertEqual(current.agent_version, AGENT_VERSION)
