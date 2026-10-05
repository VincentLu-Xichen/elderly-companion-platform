from __future__ import annotations

import json
import os
import tempfile
import unittest
import uuid

TEST_DB = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
TEST_DB.close()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{TEST_DB.name}")
os.environ.setdefault("APP_SECRET", "test-app-secret")
os.environ.setdefault("INVITE_CODES", "student-test:test-invite")
os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password")
os.environ.setdefault("COOKIE_SECURE", "false")

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from cbt_course.azure_chat_client import ChatCompletionResult
from cbt_course.agent import CourseModelResponseError, CourseTutorAgent
from cbt_course.catalog import COURSE_CATALOG
from cbt_course.engine import CourseEngine, new_course_state
from cbt_course.schemas import (
    CourseAgentResult,
    CourseExtractedValues,
    CourseTurnDecision,
    CourseTurnResult,
)
from cbt_course.services import (
    course_conversation_payload,
    create_or_resume_course,
    process_course_turn,
)
from webapp.database import Base
from webapp.models import Conversation, CourseHomeworkEntry, Message, Participant, TurnEvent
from webapp.security import decrypt_json, hash_secret


def decision(
    outcome: str,
    *,
    text: str = "",
    acknowledgement: str = "我听明白了。",
    safety_category: str = "none",
) -> CourseAgentResult:
    return CourseAgentResult(
        decision=CourseTurnDecision(
            outcome=outcome,
            extracted_values=CourseExtractedValues(text=text),
            acknowledgement=acknowledgement,
            safety_category=safety_category,
        ),
        completion=ChatCompletionResult(
            text="{}",
            model="course-test-model",
            deployment="course-test-deployment",
            api_version="test-version",
            request_id="course-request",
            finish_reason="stop",
            usage={"total_tokens": 12},
        ),
    )


class ScriptedCourseAgent:
    def __init__(self):
        self.calls: list[dict] = []

    def evaluate(self, **kwargs):
        self.calls.append(kwargs)
        step = kwargs["step"]
        if step == "problem":
            outcome = "one_event"
        elif step.startswith("quiz_"):
            outcome = "correct"
        elif step == "completed_idle":
            outcome = "start_diary"
        else:
            outcome = "valid_answer"
        return decision(outcome, text=kwargs["content"])


class CapturingClient:
    def __init__(self, text: str):
        self.text = text
        self.calls: list[tuple[list[dict], dict]] = []

    def complete_with_metadata(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return ChatCompletionResult(text=self.text, model="capture-model")


class ConversationalCourseEngineTest(unittest.TestCase):
    def test_catalog_has_eight_lessons_and_only_first_is_available(self):
        self.assertEqual(len(COURSE_CATALOG), 8)
        self.assertEqual([item["number"] for item in COURSE_CATALOG], list(range(1, 9)))
        self.assertEqual([item["available"] for item in COURSE_CATALOG], [True] + [False] * 7)

    def test_numeric_validation_does_not_advance_on_ambiguous_or_out_of_range_input(self):
        state = new_course_state("lesson-1")
        engine = CourseEngine(agent=ScriptedCourseAgent())
        for content in ("0", "11", "我在 5 到 6 分之间"):
            result = engine.process(state, content)
            self.assertEqual(result.state["step"], "mood")
            self.assertIn("一个 1—10", result.reply)
        accepted = engine.process(state, "大概是 6 分")
        self.assertEqual(accepted.state["step"], "problem")
        self.assertEqual(accepted.state["answers"]["mood_score"], 6)

    def test_multiple_events_stays_on_problem_step(self):
        class MultipleEventAgent(ScriptedCourseAgent):
            def evaluate(self, **kwargs):
                return decision("multiple_events", text=kwargs["content"])

        state = CourseEngine(agent=ScriptedCourseAgent()).process(new_course_state("lesson-1"), "5").state
        result = CourseEngine(agent=MultipleEventAgent()).process(state, "女儿没来，邻居也和我争吵")
        self.assertEqual(result.state["step"], "problem")
        self.assertNotIn("problem", result.state["answers"])
        self.assertIn("先选一件", result.reply)

    def test_complete_lesson_and_record_more_than_one_diary(self):
        agent = ScriptedCourseAgent()
        engine = CourseEngine(agent=agent)
        state = new_course_state("lesson-1")
        inputs = [
            "6",
            "昨天女儿没有给我回电话",
            "昨晚在家里，我给女儿打电话但她没有接",
            "她是不是不在乎我了",
            "8",
            "难过",
            "7",
            "我关掉电视，一个人坐着",
            "我发现我的想法会影响心情和行动",
            "别人打招呼时没想到合适的话",
            "不回应会显得不礼貌并影响关系",
            "紧张",
            "拼命想和人说话",
            "我希望遇到关系困扰时能更平静",
        ]
        attachments = []
        formulation_reply = ""
        for content in inputs:
            result = engine.process(state, content)
            state = result.state
            if result.attachment:
                attachments.append(result.attachment["kind"])
            if content == "我关掉电视，一个人坐着":
                formulation_reply = result.reply
                self.assertEqual(result.attachment, {})
        self.assertTrue(state["completed"])
        self.assertEqual(state["step"], "completed_idle")
        self.assertEqual(state["quiz_results"]["behavior"]["correct"], True)
        self.assertNotIn("formulation", attachments)
        self.assertIn("情境：昨晚在家里，我给女儿打电话但她没有接", formulation_reply)
        self.assertIn("想法：她是不是不在乎我了（当时相信程度 8/10）", formulation_reply)
        self.assertIn("情绪：难过（当时强烈程度 7/10）", formulation_reply)
        self.assertIn("行为：我关掉电视，一个人坐着", formulation_reply)
        self.assertGreaterEqual(attachments.count("image"), 4)

        diary_inputs = [
            "我想记录一条日记",
            "今天上午和邻居打招呼，他没有回应",
            "他可能不喜欢我",
            "尴尬",
            "我低头走开了",
        ]
        for content in diary_inputs:
            result = engine.process(state, content)
            state = result.state
        self.assertIsNotNone(result.homework_entry)
        self.assertEqual(result.homework_entry["emotion"], "尴尬")
        self.assertEqual(state["step"], "completed_idle")

        for content in ["再记录日记", "女儿晚回消息", "她可能在忙", "担心", "我等了一会儿"]:
            result = engine.process(state, content)
            state = result.state
        self.assertEqual(result.homework_entry["thought"], "她可能在忙")

    def test_model_cannot_supply_next_step_or_invalid_shape(self):
        invalid = json.dumps(
            {
                "outcome": "valid_answer",
                "extracted_values": {"text": "一件事"},
                "acknowledgement": "知道了。",
                "safety_category": "none",
                "next_step_id": "completed_idle",
            },
            ensure_ascii=False,
        )
        agent = CourseTutorAgent(client=CapturingClient(invalid))
        with self.assertRaises(CourseModelResponseError):
            agent.evaluate(
                step="problem",
                rubric="一件具体事件",
                allowed_outcomes=["valid_answer"],
                content="昨天我和女儿争吵",
                relevant_state={},
            )

    def test_course_agent_request_contains_only_current_step_input_and_required_state(self):
        response = json.dumps(
            {
                "outcome": "valid_answer",
                "extracted_values": {"text": "我很担心"},
                "acknowledgement": "我听到了这份担心。",
                "safety_category": "none",
            },
            ensure_ascii=False,
        )
        client = CapturingClient(response)
        agent = CourseTutorAgent(client=client)
        result = agent.evaluate(
            step="emotion",
            rubric="识别情绪",
            allowed_outcomes=["valid_answer", "no_clear_answer"],
            content="我很担心",
            relevant_state={"situation": "电话没有接通"},
        )
        self.assertEqual(result.decision.extracted_values.text, "我很担心")
        sent = json.dumps(client.calls[0][0], ensure_ascii=False)
        self.assertIn("电话没有接通", sent)
        self.assertNotIn("scenario", sent.lower())
        self.assertNotIn("语境卡", sent)
        response_format = client.calls[0][1]["response_format"]
        self.assertEqual(response_format["type"], "json_schema")
        self.assertTrue(response_format["json_schema"]["strict"])

    def test_model_safety_decision_keeps_course_on_current_step(self):
        class SafetyAgent:
            def evaluate(self, **kwargs):
                return decision(
                    "one_event",
                    text=kwargs["content"],
                    safety_category="self_harm",
                )

        state = CourseEngine(agent=ScriptedCourseAgent()).process(new_course_state("lesson-1"), "5").state
        result = CourseEngine(agent=SafetyAgent()).process(state, "一段需要模型识别风险的输入")
        self.assertEqual(result.state["step"], "problem")
        self.assertEqual(result.safety_event, "model_self_harm")
        self.assertEqual(result.trace["safety"], "self_harm")


class ConversationalCourseServiceTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.db = self.Session()
        self.participant = Participant(
            label=f"course-{uuid.uuid4()}",
            invite_hash=hash_secret("course-code"),
        )
        self.db.add(self.participant)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_create_resume_attachment_and_restart_after_completion(self):
        conversation, resumed = create_or_resume_course(
            self.db,
            participant_id=self.participant.id,
            lesson_id="lesson-1",
        )
        self.assertFalse(resumed)
        same, resumed = create_or_resume_course(
            self.db,
            participant_id=self.participant.id,
            lesson_id="lesson-1",
        )
        self.assertTrue(resumed)
        self.assertEqual(same.id, conversation.id)
        payload = course_conversation_payload(conversation)
        self.assertEqual(payload["messages"][0]["attachment"]["kind"], "image")
        self.assertIsNone(conversation.scenario_id)
        self.assertIsNone(conversation.scenario_snapshot_encrypted)

        class CompleteEngine:
            def process(self, state, content):
                completed = dict(state)
                completed.update({"step": "completed_idle", "completed": True})
                return CourseTurnResult(
                    reply="第 1 课完成了。",
                    state=completed,
                    trace={"step_from": state["step"], "step_to": "completed_idle"},
                )

        process_course_turn(
            self.db,
            conversation,
            content="完成测试",
            idempotency_key="complete-course-001",
            engine_factory=CompleteEngine,
        )
        self.db.refresh(conversation)
        self.assertEqual(conversation.status, "completed")
        self.assertIsNone(conversation.active_course_key)
        restarted, resumed = create_or_resume_course(
            self.db,
            participant_id=self.participant.id,
            lesson_id="lesson-1",
        )
        self.assertFalse(resumed)
        self.assertNotEqual(restarted.id, conversation.id)

    def test_keyword_like_input_is_delegated_to_course_engine(self):
        conversation, _ = create_or_resume_course(
            self.db,
            participant_id=self.participant.id,
            lesson_id="lesson-1",
        )
        initial_state = decrypt_json(conversation.agent_state_encrypted)

        class RecordingEngine:
            called = False

            def process(self, state, content):
                self.__class__.called = True
                return CourseTurnResult(
                    reply="课程引擎已处理。",
                    state=state,
                    trace={"step_from": state["step"], "step_to": state["step"]},
                )

        result = process_course_turn(
            self.db,
            conversation,
            content="我不想活了",
            idempotency_key="course-safety-001",
            engine_factory=RecordingEngine,
        )
        self.assertTrue(RecordingEngine.called)
        self.assertEqual(result["status"], "success")
        self.assertIsNone(result["safety_event"])
        self.assertEqual(result["course"]["current_step"], "mood")
        self.db.expire_all()
        stored = self.db.get(Conversation, conversation.id)
        self.assertEqual(decrypt_json(stored.agent_state_encrypted), initial_state)
        event = self.db.scalar(select(TurnEvent).where(TurnEvent.conversation_id == conversation.id))
        self.assertEqual(event.status, "success")
        self.assertIsNone(event.safety_event)

    def test_error_keeps_user_message_and_pending_audit_becomes_error(self):
        conversation, _ = create_or_resume_course(
            self.db,
            participant_id=self.participant.id,
            lesson_id="lesson-1",
        )

        class ErrorEngine:
            def process(self, state, content):
                raise RuntimeError("invalid structured response")

        with self.assertRaisesRegex(RuntimeError, "invalid structured response"):
            process_course_turn(
                self.db,
                conversation,
                content="这条用户输入必须保留",
                idempotency_key="course-error-0001",
                engine_factory=ErrorEngine,
            )
        self.db.expire_all()
        messages = self.db.scalars(
            select(Message).where(Message.conversation_id == conversation.id).order_by(Message.sequence)
        ).all()
        self.assertEqual(len(messages), 2)
        event = self.db.scalar(select(TurnEvent).where(TurnEvent.conversation_id == conversation.id))
        self.assertEqual(event.status, "error")
        self.assertEqual(event.error_type, "RuntimeError")

    def test_idempotency_and_encrypted_homework_persistence(self):
        conversation, _ = create_or_resume_course(
            self.db,
            participant_id=self.participant.id,
            lesson_id="lesson-1",
        )
        first = process_course_turn(
            self.db,
            conversation,
            content="5",
            idempotency_key="course-idempotent-001",
        )
        second = process_course_turn(
            self.db,
            conversation,
            content="不会再次保存",
            idempotency_key="course-idempotent-001",
        )
        self.assertEqual(first["reply"], second["reply"])
        self.assertTrue(second["deduplicated"])

        class HomeworkEngine:
            def process(self, state, content):
                completed = dict(state)
                completed.update({"step": "completed_idle", "completed": True})
                return CourseTurnResult(
                    reply="日记已保存。",
                    state=completed,
                    trace={"step_from": state["step"], "step_to": "completed_idle"},
                    homework_entry={
                        "situation": "和邻居见面",
                        "thought": "他没看见我",
                        "emotion": "失落",
                        "behavior": "回家了",
                    },
                )

        process_course_turn(
            self.db,
            conversation,
            content="保存日记",
            idempotency_key="course-homework-001",
            engine_factory=HomeworkEngine,
        )
        entry = self.db.scalar(
            select(CourseHomeworkEntry).where(CourseHomeworkEntry.conversation_id == conversation.id)
        )
        self.assertIsNotNone(entry)
        self.assertNotIn("和邻居见面", entry.payload_encrypted)
        self.assertEqual(decrypt_json(entry.payload_encrypted)["emotion"], "失落")


if __name__ == "__main__":
    unittest.main()
