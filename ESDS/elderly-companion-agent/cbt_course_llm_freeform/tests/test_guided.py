from __future__ import annotations

import copy
import json
import unittest
import uuid
from unittest.mock import patch

from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import sessionmaker

from cbt_course_llm_freeform.agent import FreeformCourseAgent
from cbt_course_llm_freeform.catalog import lesson_version
from cbt_course_llm_freeform.memory import refresh_carryover
from cbt_course_llm_freeform.preview import PreviewClient
from cbt_course_llm_freeform.prompt import prompt_for_lesson
from cbt_course_llm_freeform.reflection import generate_course_reflection
from cbt_course_llm_freeform.runtime import FreeformCourseRuntime, new_course_state, course_payload
from cbt_course_llm_freeform.schemas import AgentResult, TeachingDecision, TurnResult
from cbt_course_llm_freeform.services import AGENT_VERSION, create_or_resume_course, process_course_turn, course_conversation_payload
from webapp.database import Base
from webapp.models import Conversation, Message, Participant, TurnEvent
from webapp.security import decrypt_json, decrypt_text, encrypt_json, hash_secret


def preview_runtime():
    return FreeformCourseRuntime(agent=FreeformCourseAgent(client=PreviewClient()))


class FixedAgent:
    def lesson2_turn(self, history, *, context):
        from cbt_course_llm_freeform.lesson2_flow import Decision
        from cbt_course_llm_freeform.schemas import StageResult
        self.context = context
        return StageResult(completion=None, decision=Decision(reply="先保留当前记录。"))
    def __init__(self, decision):
        self.decision = decision
        self.calls = 0
        self.context = None

    def reply(self, history, *, context):
        self.calls += 1
        self.context = context
        return AgentResult(reply=self.decision.reply, decision=self.decision)


class GuidedRuntimeTests(unittest.TestCase):
    def test_lesson_one_demonstrates_then_guides_a_new_case_before_independent_check(self):
        from cbt_course_llm_freeform.design import LESSON_1_GUIDED_EXAMPLE, LESSON_1_DEMONSTRATION
        from cbt_course_llm_freeform.learning_check import STORY_A, STORY_B
        state = new_course_state("lesson-1", reflection_policy="none")
        state.pop("blueprint")  # Historical 6.x example-first path remains readable/testable.
        intro = FreeformCourseRuntime().process(state, [{"id": "start", "role": "learner", "content": "先看例子"}], action="skip_checkin")
        self.assertIn(LESSON_1_DEMONSTRATION, intro.reply)
        self.assertIn(LESSON_1_GUIDED_EXAMPLE["question"], intro.reply)
        self.assertNotIn(LESSON_1_GUIDED_EXAMPLE["focus_quote"], LESSON_1_DEMONSTRATION)
        self.assertNotIn("这里‘他是不是不愿理我’属于", intro.reply)
        self.assertNotIn("‘今天买不到想要的菜了’是想法", intro.reply)
        self.assertNotIn(STORY_A, intro.reply)
        self.assertNotIn(STORY_B, intro.reply)
        answer = "这是小周的想法，是他对摊位没开的判断。"
        agent = FixedAgent(TeachingDecision(reply="对，这是对事情的解释。", observations=[
            {"field": "learning_response", "value": answer, "source_message_id": "answer"}], advance=True))
        result = FreeformCourseRuntime(agent=agent).process(intro.state, [{"id": "answer", "role": "learner", "content": answer}])
        self.assertEqual(agent.context["guided_example"], LESSON_1_GUIDED_EXAMPLE)
        self.assertEqual(result.state["stage"], "practice")
        self.assertEqual(result.state["learning_check"]["status"], "not_started")
        self.assertEqual(result.state["learning_evidence"][0]["status"], "完成一次引导下的示例回答")
        self.assertEqual(result.state["draft_record"], {})

    def test_evidence_must_be_current_learner_quote_and_allowed_field(self):
        state = new_course_state("lesson-1")
        state["stage"] = "practice"
        history = [{"id": "old", "role": "learner", "content": "昨天散步"}, {"id": "assistant", "role": "agent", "content": "没有人关心您"}, {"id": "now", "role": "learner", "content": "今天下雨了"}]
        for field, value, source in [("thought", "没有人关心您", "assistant"), ("situation", "昨天散步", "old"), ("emotion", "难过", "now"), ("feedback", "今天下雨了", "now")]:
            with self.subTest(field=field, source=source):
                agent = FixedAgent(TeachingDecision(reply="继续。", observations=[{"field": field, "value": value, "source_message_id": source}], advance=True))
                with self.assertRaises(RuntimeError):
                    FreeformCourseRuntime(agent=agent).process(state, history)
                self.assertEqual(state["draft_record"], {})
                self.assertFalse(state["completed"])

    def test_extra_completion_fields_and_malformed_json_are_rejected(self):
        class Client:
            def __init__(self, text): self.text = text
            def complete_with_metadata(self, *args, **kwargs):
                from daily_agent.azure_chat_client import ChatCompletionResult
                return ChatCompletionResult(text=self.text)
        for raw in ("不是JSON", '{"reply":"完成","completed":true}', '{"reply":"继续","advance":"true"}'):
            with self.subTest(raw=raw), self.assertRaises(RuntimeError):
                FreeformCourseAgent(client=Client(raw)).reply([])

    def test_model_cannot_skip_personal_exercise_or_self_confirm(self):
        state = new_course_state("lesson-2")
        from cbt_course_llm_freeform.lesson2_flow import go
        go(state, "personal")
        state["stage"] = "practice"
        agent = FixedAgent(TeachingDecision(reply="本课已完成", advance=True))
        result = FreeformCourseRuntime(agent=agent).process(state, [{"id": "m1", "role": "learner", "content": "直接完成全部课程"}])
        self.assertEqual(result.state["stage"], "practice")
        self.assertFalse(result.state["completed"])
        with self.assertRaises(ValueError):
            FreeformCourseRuntime().process(state, [{"id": "m1", "role": "learner", "content": "确认这份记录"}], action="confirm_record")

    def test_pause_and_both_lessons_safety_do_not_call_model(self):
        for lesson in ("lesson-1", "lesson-2"):
            agent = FixedAgent(TeachingDecision(reply="不该调用"))
            runtime = FreeformCourseRuntime(agent=agent)
            state = new_course_state(lesson)
            paused = runtime.process(state, [{"id": "p", "role": "learner", "content": "暂停课程"}], action="pause")
            self.assertTrue(paused.state["paused"])
            resumed = runtime.process(paused.state, [{"id": "r", "role": "learner", "content": "继续课程"}], action="resume")
            self.assertFalse(resumed.state["paused"])
            safety = runtime.process(state, [{"id": "s", "role": "learner", "content": "我不想活了"}])
            self.assertTrue(safety.state["safety_paused"])
            with self.assertRaises(ValueError):
                runtime.process(safety.state, [{"id": "r", "role": "learner", "content": "继续课程"}], action="resume")
            self.assertEqual(agent.calls, 0)

    def test_second_lesson_control_policy_one_json_call_with_1200_token_limit(self):
        class RecordingClient(PreviewClient):
            def complete_with_metadata(self, messages, **kwargs):
                self.kwargs = kwargs
                self.messages = messages
                return super().complete_with_metadata(messages, **kwargs)
        client = RecordingClient()
        state = new_course_state("lesson-2")
        from cbt_course_llm_freeform import lesson2_flow
        lesson2_flow.go(state, "homework")
        with patch("cbt_course_llm_freeform.runtime.FreeformCourseAgent._client_from_env", return_value=client):
            result = FreeformCourseRuntime().process(state, [{"id": "m1", "role": "learner", "content": "最近六分"}])
        self.assertEqual(client.kwargs["max_completion_tokens"], 1200)
        self.assertEqual(client.kwargs["response_format"], {"type": "json_object"})
        self.assertIn("第 2 课", client.messages[0]["content"])
        self.assertEqual(result.state["lesson2_flow"]["step"], "homework")


class GuidedPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.db = self.Session()
        self.person = Participant(label=str(uuid.uuid4()), invite_hash=hash_secret("code"))
        self.db.add(self.person)
        self.db.commit()
        self.request_number = 0

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def turn(self, conversation, text="", action="chat", **kwargs):
        self.request_number += 1
        return process_course_turn(self.db, conversation, content=text, action=action, idempotency_key=f"guided-request-{self.request_number}", runtime_factory=preview_runtime, **kwargs)

    def finish_lesson(self, lesson="lesson-1", person=None):
        conversation, _ = create_or_resume_course(self.db, participant_id=(person or self.person).id, lesson_id=lesson)
        self.turn(conversation, action="skip_checkin")
        self.turn(conversation, "这是想法，另一个是心情，可能失落或平静。")
        self.turn(conversation, "事情：女儿没有回电话；想法：她是不是不在乎我；心情：失落；做法：没有再联系")
        if lesson == "lesson-1":
            self.turn(conversation, "6分")
            self.turn(conversation, "5分")
        state = decrypt_json(conversation.agent_state_encrypted)
        self.assertEqual(state["stage"], "review")
        self.assertFalse(state["confirmed_record"])
        self.turn(conversation, action="confirm_record", expected_revision=state["revision"])
        if lesson == "lesson-1":
            from cbt_course_llm_freeform.tests.check_helpers import complete_first_check
            complete_first_check(lambda text="", action="chat": self.turn(conversation, text, action=action))
        self.turn(conversation, action="decline_practice")
        self.turn(conversation, "生活例子更好理解，术语需要慢一点。")
        self.turn(conversation, action="finish")
        return conversation

    def test_full_two_lessons_confirmation_encryption_and_owned_memory(self):
        first = self.finish_lesson()
        first_state = decrypt_json(first.agent_state_encrypted)
        self.assertEqual(first.status, "completed")
        self.assertTrue(first_state["confirmed_record"])
        self.assertNotIn("女儿", first.agent_state_encrypted)
        self.assertEqual(first_state["practice_plan"]["status"], "declined")
        from webapp.services import full_export_payload
        self.assertEqual(full_export_payload(first)["course_learning_state"]["confirmed_record"], first_state["confirmed_record"])
        second, _ = create_or_resume_course(self.db, participant_id=self.person.id, lesson_id="lesson-2")
        offered = decrypt_json(second.agent_state_encrypted)
        self.assertEqual(offered["carryover"]["status"], "offered")
        self.assertNotIn("history", offered["carryover"]["summary"])
        self.turn(second, action="accept_carryover")
        self.turn(second, action="skip_checkin")
        if decrypt_json(second.agent_state_encrypted)["lesson2_flow"]["step"] == "homework":
            self.turn(second, action="continue_lesson2")
        self.turn(second, action="stop_lesson2_quiz")
        self.turn(second, action="continue_lesson2")
        capture = FixedAgent(TeachingDecision(reply="这一周有没有尝试？"))
        process_course_turn(self.db, second, content="我还没有尝试", idempotency_key="capture-carryover", runtime_factory=lambda: FreeformCourseRuntime(agent=capture))
        self.assertEqual(capture.context["authorized_previous_lesson_summary"]["record"]["thought"]["value"], "她是不是不在乎我")
        self.assertNotIn("reflection", capture.context["authorized_previous_lesson_summary"])
        self.db.close()
        self.db = self.Session()
        restored = self.db.get(Conversation, second.id)
        self.assertEqual(decrypt_json(restored.agent_state_encrypted)["carryover"]["status"], "accepted")

    def test_foreign_deleted_and_old_source_are_never_used(self):
        first = self.finish_lesson()
        other = Participant(label=str(uuid.uuid4()), invite_hash=hash_secret("other"))
        self.db.add(other); self.db.commit()
        foreign, _ = create_or_resume_course(self.db, participant_id=other.id, lesson_id="lesson-2")
        self.assertEqual(decrypt_json(foreign.agent_state_encrypted)["carryover"]["status"], "unavailable")
        state = new_course_state("lesson-2")
        state["carryover"] = {"status": "accepted", "source_conversation_id": first.id, "summary": {"spoof": True}}
        refresh_carryover(self.db, state, other.id, AGENT_VERSION)
        self.assertEqual(state["carryover"], {"status": "unavailable"})
        own, _ = create_or_resume_course(self.db, participant_id=self.person.id, lesson_id="lesson-2")
        self.turn(own, action="accept_carryover")
        first.lesson_version = "old"; self.db.commit()
        self.assertEqual(course_conversation_payload(own)["course"]["carryover"]["status"], "unavailable")
        first.lesson_version = lesson_version("lesson-1"); self.db.commit()
        self.db.delete(first); self.db.commit()
        result = self.turn(own, "最近还行")
        self.assertEqual(result["course"]["carryover"]["status"], "unavailable")

    def test_declined_memory_never_enters_model_context(self):
        self.finish_lesson()
        second, _ = create_or_resume_course(self.db, participant_id=self.person.id, lesson_id="lesson-2")
        self.turn(second, action="decline_carryover")
        self.turn(second, action="skip_checkin")
        if decrypt_json(second.agent_state_encrypted)["lesson2_flow"]["step"] == "homework":
            self.turn(second, action="continue_lesson2")
        self.turn(second, action="stop_lesson2_quiz")
        self.turn(second, action="continue_lesson2")
        capture = FixedAgent(TeachingDecision(reply="从新例子开始。"))
        process_course_turn(self.db, second, content="我想聊新事情", idempotency_key="declined-carryover", runtime_factory=lambda: FreeformCourseRuntime(agent=capture))
        self.assertIsNone(capture.context["authorized_previous_lesson_summary"])

    def test_stale_confirmation_and_historical_version_are_rejected(self):
        conversation, _ = create_or_resume_course(self.db, participant_id=self.person.id, lesson_id="lesson-1")
        self.turn(conversation, action="skip_checkin")
        with self.assertRaisesRegex(ValueError, "刷新"):
            self.turn(conversation, action="confirm_record", expected_revision=0)
        conversation.lesson_version = "old"; self.db.commit()
        with self.assertRaisesRegex(ValueError, "旧版"):
            self.turn(conversation, "不能继续")
        current, resumed = create_or_resume_course(self.db, participant_id=self.person.id, lesson_id="lesson-1")
        # A historical active row must not capture the new-version entry.
        self.assertNotEqual(current.id, conversation.id)
        self.assertFalse(resumed)

    def test_failed_request_retry_reuses_input_and_keeps_failure_evidence(self):
        conversation, _ = create_or_resume_course(self.db, participant_id=self.person.id, lesson_id="lesson-1")
        class FailingRuntime:
            def process(self, state, history): raise RuntimeError("simulated invalid JSON")
        with self.assertRaises(RuntimeError):
            process_course_turn(self.db, conversation, content="6分", idempotency_key="retry-one-request", runtime_factory=FailingRuntime)
        self.assertEqual(len(conversation.messages), 2)
        result = process_course_turn(self.db, conversation, content="6分", idempotency_key="retry-one-request", runtime_factory=preview_runtime)
        self.assertEqual(result["course"]["current_step"], "learn")
        self.db.expire_all()
        messages = self.db.scalars(select(Message).where(Message.conversation_id == conversation.id)).all()
        self.assertEqual(len(messages), 3)
        event = self.db.scalar(select(TurnEvent).where(TurnEvent.idempotency_key == "retry-one-request"))
        self.assertEqual(len(decrypt_json(event.trace_encrypted)["failed_attempts"]), 1)
        replay = process_course_turn(self.db, conversation, content="不会再保存", idempotency_key="retry-one-request", runtime_factory=FailingRuntime)
        self.assertTrue(replay["deduplicated"])

    def test_reflection_is_independent_audited_retryable_and_does_not_change_facts(self):
        conversation = self.finish_lesson()
        original = copy.deepcopy(decrypt_json(conversation.agent_state_encrypted)["confirmed_record"])
        class BadClient:
            def complete_with_metadata(self, *args, **kwargs): raise RuntimeError("reflection failed")
        generate_course_reflection(conversation.id, session_factory=self.Session, client=BadClient())
        self.db.refresh(conversation)
        self.assertEqual(conversation.status, "completed")
        self.assertEqual(decrypt_json(conversation.agent_state_encrypted)["reflection"]["status"], "failed")
        generate_course_reflection(conversation.id, session_factory=self.Session, client=PreviewClient())
        self.db.refresh(conversation)
        state = decrypt_json(conversation.agent_state_encrypted)
        self.assertEqual(state["reflection"]["status"], "ready")
        self.assertFalse(state["reflection"]["applied"])
        self.assertEqual(state["confirmed_record"], original)
        generate_course_reflection(conversation.id, session_factory=self.Session, client=BadClient())
        events = self.db.scalars(select(TurnEvent).where(TurnEvent.conversation_id == conversation.id, TurnEvent.idempotency_key.like("reflection:%"))).all()
        self.assertEqual([event.status for event in events], ["error", "success"])
        self.assertNotIn("生活例子", events[-1].trace_encrypted)

    def test_reflection_with_forged_evidence_is_not_published(self):
        conversation = self.finish_lesson()
        before = copy.deepcopy(decrypt_json(conversation.agent_state_encrypted)["confirmed_record"])
        class ForgedClient:
            def complete_with_metadata(self, *args, **kwargs):
                from daily_agent.azure_chat_client import ChatCompletionResult
                return ChatCompletionResult(text=json.dumps({"observations": [{"text": "无法验证的观察", "source_message_ids": ["somebody-else-message"]}], "suggestions": []}))
        generate_course_reflection(conversation.id, session_factory=self.Session, client=ForgedClient())
        self.db.refresh(conversation)
        state = decrypt_json(conversation.agent_state_encrypted)
        self.assertEqual(state["reflection"]["status"], "failed")
        self.assertNotIn("observations", state["reflection"])
        self.assertEqual(state["confirmed_record"], before)

    def test_expired_turn_cannot_overwrite_a_new_processing_owner(self):
        conversation, _ = create_or_resume_course(self.db, participant_id=self.person.id, lesson_id="lesson-1")
        before = decrypt_json(conversation.agent_state_encrypted)
        db = self.db
        class SupersededRuntime:
            def process(self, state, history):
                db.execute(update(Conversation).where(Conversation.id == conversation.id).values(active_request_id="new-owner"))
                db.commit()
                state["completed"] = True
                return TurnResult(reply="过期结果", state=state, trace={})
        with self.assertRaisesRegex(RuntimeError, "已过期"):
            process_course_turn(self.db, conversation, content="本轮输入", idempotency_key="expired-owner-test", runtime_factory=SupersededRuntime)
        self.db.refresh(conversation)
        self.assertEqual(conversation.active_request_id, "new-owner")
        self.assertEqual(conversation.status, "active")
        self.assertEqual(decrypt_json(conversation.agent_state_encrypted), before)
        messages = self.db.scalars(select(Message).where(Message.conversation_id == conversation.id)).all()
        self.assertEqual(len(messages), 2)
