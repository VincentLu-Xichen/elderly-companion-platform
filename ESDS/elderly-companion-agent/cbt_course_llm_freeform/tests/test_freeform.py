from __future__ import annotations

import json
import unittest
import os
import urllib.error
import uuid
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from cbt_course_llm_freeform.agent import FreeformCourseAgent
from cbt_course_llm_freeform.azure_chat_client import AzureChatCompletionsClient, ChatCompletionResult
from cbt_course_llm_freeform.catalog import LESSON_2_VERSION, course_by_id
from cbt_course_llm_freeform.prompt import prompt_for_lesson
LESSON_2_SYSTEM_PROMPT = prompt_for_lesson("lesson-2")
from cbt_course_llm_freeform.tests.shared_turn_fixture import shared_state
from cbt_course_llm_freeform.runtime import (
    FreeformCourseRuntime,
    course_payload,
    new_course_state,
    parse_control_markers,
)
from cbt_course_llm_freeform.schemas import AgentResult, TurnResult, TeachingDecision
from cbt_course_llm_freeform.services import AGENT_VERSION, create_or_resume_course, process_course_turn
from webapp.database import Base
from webapp.models import Conversation, Message, Participant, TurnEvent
from webapp.security import decrypt_json, hash_secret


class CapturingClient:
    def __init__(self, text: str):
        self.text = json.dumps({"reply": text, "observations": [], "advance": False}, ensure_ascii=False)
        self.messages = []
        self.kwargs = {}

    def complete_with_metadata(self, messages, **kwargs):
        self.messages = messages
        self.kwargs = kwargs
        return ChatCompletionResult(text=self.text, model="freeform-test")


class FakeAgent:
    def __init__(self, reply: str):
        self.reply_text = reply
        self.history = None

    def reply(self, history, *, context=None):
        self.history = history
        return AgentResult(
            reply=self.reply_text,
            completion=ChatCompletionResult(text=self.reply_text, model="freeform-test"),
            decision=TeachingDecision(reply=self.reply_text),
        )


class FreeformAgentRuntimeTest(unittest.TestCase):
    def test_default_course_provider_is_dashscope(self):
        with patch.dict(
            os.environ,
            {
                "CBT_COURSE_PROVIDER": "dashscope",
                "DASHSCOPE_API_KEY": "test-key",
                "CBT_COURSE_MODEL": "qwen-plus",
            },
            clear=False,
        ):
            agent = FreeformCourseAgent()
        self.assertEqual(agent.client.model, "qwen-plus")

    def test_azure_client_retries_transient_connection_failure(self):
        attempts = []
        delays = []

        class Response:
            headers = {"x-request-id": "retry-ok"}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps(
                    {"model": "test", "choices": [{"message": {"content": "成功"}, "finish_reason": "stop"}]}
                ).encode()

        def flaky_opener(request, timeout):
            attempts.append(request.full_url)
            if len(attempts) < 3:
                raise urllib.error.URLError("temporary TLS disconnect")
            return Response()

        client = AzureChatCompletionsClient(
            endpoint="https://example.invalid",
            api_key="test",
            deployment="test",
            opener=flaky_opener,
            sleeper=delays.append,
        )
        result = client.complete_with_metadata([{"role": "user", "content": "测试"}])
        self.assertEqual(result.text, "成功")
        self.assertEqual(len(attempts), 3)
        self.assertEqual(delays, [0.5, 1.0])

    def test_agent_sends_course_history_with_ids_and_structured_format(self):
        client = CapturingClient("我们继续。")
        history = [
            {"role": "agent", "content": "欢迎来到第一课"},
            {"role": "learner", "content": "5"},
            {"role": "agent", "content": "最近发生了什么？"},
            {"role": "learner", "content": "女儿没有回电话"},
        ]
        FreeformCourseAgent(client=client).reply(history)
        self.assertEqual([item["role"] for item in client.messages], ["system", "assistant", "user", "assistant", "user"])
        sent = "\n".join(item["content"] for item in client.messages)
        self.assertIn("女儿没有回电话", sent)
        self.assertNotIn("scenario_id", sent)
        self.assertEqual(client.kwargs["response_format"], {"type": "json_object"})
        self.assertEqual(client.kwargs["temperature"], 1.0)

    def test_control_markers_are_removed_and_whitelisted(self):
        reply, attachment, completed, key = parse_control_markers(
            "请看这份材料。[[CBT_ATTACHMENT:practice_scenario]][[CBT_COURSE_COMPLETE]]"
        )
        self.assertEqual(reply, "请看这份材料。")
        self.assertEqual(attachment["kind"], "image")
        self.assertEqual(key, "practice_scenario")
        self.assertTrue(completed)

        reply, attachment, completed, key = parse_control_markers(
            "继续课程。[[CBT_ATTACHMENT:../../secret]]"
        )
        self.assertEqual(reply, "继续课程。")
        self.assertEqual(attachment, {})
        self.assertIsNone(key)
        self.assertFalse(completed)

    def test_model_completion_marker_cannot_complete_a_course(self):
        state = shared_state()
        fake = FakeAgent("我们继续梳理。")
        result = FreeformCourseRuntime(agent=fake).process(state, [{"role": "learner", "content": "回答"}])
        self.assertEqual(course_payload(result.state)["progress_percent"], 0)
        self.assertEqual(course_payload(result.state)["phase"], "近况与回顾")
        self.assertEqual(fake.history[-1]["content"], "回答")

        result = FreeformCourseRuntime(agent=FakeAgent("本课结束。[[CBT_COURSE_COMPLETE]]")).process(
            result.state, [{"role": "learner", "content": "目标不用修改"}]
        )
        self.assertFalse(result.state["completed"])
        self.assertEqual(course_payload(result.state)["progress_percent"], 0)
        with self.assertRaisesRegex(ValueError, "当前阶段"):
            FreeformCourseRuntime(agent=FakeAgent("不应调用")).process(result.state, [{"id": "finish", "role": "learner", "content": "完成本课"}], action="finish")

    def test_marker_only_reply_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "控制标记"):
            parse_control_markers("[[CBT_COURSE_COMPLETE]]")

    def test_lesson_2_is_available_and_uses_its_own_prompt(self):
        self.assertTrue(course_by_id("lesson-2")["available"])
        state = new_course_state("lesson-2")
        self.assertEqual(state["lesson_version"], LESSON_2_VERSION)
        self.assertEqual(course_payload(state)["lesson"]["title"], "捕捉我的思维")

        client = CapturingClient("我们先从最近一周开始。")
        FreeformCourseAgent(
            client=client,
            system_prompt=LESSON_2_SYSTEM_PROMPT,
            max_completion_tokens=600,
        ).reply([{"role": "learner", "content": "最近还可以"}])
        self.assertIn("第 2 课", client.messages[0]["content"])
        self.assertIn("不把身体不适简单说成情绪", client.messages[0]["content"])
        self.assertIn("记录确认、课后选择、结束和授权由学习者显式操作", client.messages[0]["content"])
        self.assertEqual(client.kwargs["max_completion_tokens"], 600)

    def test_lesson_2_local_safety_skips_model(self):
        state = new_course_state("lesson-2")
        result = FreeformCourseRuntime().process(
            state,
            [{"role": "learner", "content": "我不想活了"}],
        )
        self.assertEqual(result.safety_event, "local_self_harm")
        self.assertFalse(result.trace["model_called"])
        self.assertTrue(result.state["safety_paused"])


class FreeformServiceTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.db = self.Session()
        self.participant = Participant(
            label=f"freeform-{uuid.uuid4()}",
            invite_hash=hash_secret("test-code"),
        )
        self.db.add(self.participant)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_create_resume_and_foreign_course_is_read_only(self):
        conversation, resumed = create_or_resume_course(
            self.db, participant_id=self.participant.id, lesson_id="lesson-1"
        )
        self.assertFalse(resumed)
        same, resumed = create_or_resume_course(
            self.db, participant_id=self.participant.id, lesson_id="lesson-1"
        )
        self.assertTrue(resumed)
        self.assertEqual(same.id, conversation.id)
        self.assertEqual(conversation.agent_version, AGENT_VERSION)
        self.assertIn("7.5-two-lesson-backend", conversation.active_course_key)
        self.assertIsNone(conversation.scenario_snapshot_encrypted)

        conversation.agent_version = "course-v1"
        self.db.commit()
        with self.assertRaisesRegex(ValueError, "仅支持查看"):
            process_course_turn(
                self.db,
                conversation,
                content="不能继续",
                idempotency_key="foreign-freeform-001",
            )

    def test_full_history_success_idempotency_and_completion(self):
        conversation, _ = create_or_resume_course(
            self.db, participant_id=self.participant.id, lesson_id="lesson-1"
        )
        captured_histories = []

        class CompletingRuntime:
            def process(self, state, history):
                captured_histories.append(history)
                updated = dict(state)
                updated.update({"turn_count": 1, "completed": True})
                return TurnResult(
                    reply="本课结束，请按四要素记录日记。",
                    state=updated,
                    trace={"turn_count": 1, "completed": True},
                )

        first = process_course_turn(
            self.db,
            conversation,
            content="目标不用修改",
            idempotency_key="freeform-idempotent-001",
            runtime_factory=CompletingRuntime,
        )
        second = process_course_turn(
            self.db,
            conversation,
            content="不会重复保存",
            idempotency_key="freeform-idempotent-001",
            runtime_factory=CompletingRuntime,
        )
        self.assertEqual(captured_histories[0][0]["role"], "agent")
        self.assertEqual(captured_histories[0][-1]["content"], "目标不用修改")
        self.assertTrue(captured_histories[0][-1]["id"])
        self.assertTrue(first["course"]["completed"])
        self.assertTrue(second["deduplicated"])
        self.assertIsNone(first["safety_event"])
        self.db.expire_all()
        stored = self.db.get(Conversation, conversation.id)
        self.assertEqual(stored.status, "completed")
        self.assertIsNone(stored.active_course_key)
        self.assertTrue(decrypt_json(stored.agent_state_encrypted)["completed"])

    def test_failure_keeps_user_message_and_state(self):
        conversation, _ = create_or_resume_course(
            self.db, participant_id=self.participant.id, lesson_id="lesson-1"
        )
        initial = decrypt_json(conversation.agent_state_encrypted)

        class ErrorRuntime:
            def process(self, state, history):
                raise RuntimeError("provider unavailable")

        with self.assertRaisesRegex(RuntimeError, "provider unavailable"):
            process_course_turn(
                self.db,
                conversation,
                content="需要保留的回答",
                idempotency_key="freeform-error-001",
                runtime_factory=ErrorRuntime,
            )
        self.db.expire_all()
        stored = self.db.get(Conversation, conversation.id)
        self.assertEqual(decrypt_json(stored.agent_state_encrypted), initial)
        messages = self.db.scalars(select(Message).where(Message.conversation_id == conversation.id)).all()
        self.assertEqual(len(messages), 2)
        event = self.db.scalar(select(TurnEvent).where(TurnEvent.conversation_id == conversation.id))
        self.assertEqual(event.status, "error")
        self.assertEqual(event.error_type, "RuntimeError")

        captured_histories = []

        class RecoveryRuntime:
            def process(self, state, history):
                captured_histories.append(history)
                return TurnResult(reply="已经恢复。", state=state, trace={"recovered": True})

        process_course_turn(
            self.db,
            stored,
            content="新的有效回答",
            idempotency_key="freeform-recovery-001",
            runtime_factory=RecoveryRuntime,
        )
        sent_text = "\n".join(item["content"] for item in captured_histories[0])
        self.assertNotIn("需要保留的回答", sent_text)
        self.assertIn("新的有效回答", sent_text)

    def test_lesson_2_create_and_resume_uses_freeform_version(self):
        conversation, resumed = create_or_resume_course(
            self.db, participant_id=self.participant.id, lesson_id="lesson-2"
        )
        self.assertFalse(resumed)
        self.assertEqual(conversation.lesson_version, LESSON_2_VERSION)
        self.assertIn(f"lesson-2:{LESSON_2_VERSION}", conversation.active_course_key)
        messages = self.db.scalars(select(Message).where(Message.conversation_id == conversation.id)).all()
        self.assertEqual(len(messages), 1)
        self.assertIsNone(messages[0].attachment_encrypted)

        conversation.lesson_version = "2.0-llm-freeform-single-call"
        self.db.commit()
        with self.assertRaisesRegex(ValueError, "旧版课程 Prompt"):
            process_course_turn(
                self.db,
                conversation,
                content="不能混用新旧 Prompt",
                idempotency_key="lesson-2-old-prompt-001",
            )


if __name__ == "__main__":
    unittest.main()
