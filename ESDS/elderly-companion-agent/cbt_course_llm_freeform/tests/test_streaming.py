from __future__ import annotations

import io
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from threading import Event
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from cbt_course_llm_freeform.agent import FreeformCourseAgent
from cbt_course_llm_freeform.deepseek_chat_client import DeepSeekChatCompletionsClient
from cbt_course_llm_freeform.preview import PreviewClient
from cbt_course_llm_freeform.reply_stream import ReplyProjector
from cbt_course_llm_freeform.runtime import FreeformCourseRuntime, new_course_state
from cbt_course_llm_freeform.services import create_or_resume_course, process_course_turn
from cbt_course_llm_freeform.streaming import stream_course_turn
from daily_agent.azure_chat_client import ChatCompletionResult, ChatCompletionStreamChunk
from webapp.config import settings
from webapp.database import Base
from webapp.models import Consent, Conversation, Message, Participant, TurnEvent
from webapp.security import decrypt_json, hash_secret


class Response(io.BytesIO):
    headers = {"x-request-id": "offline-request"}


class StreamClient(PreviewClient):
    def __init__(self, *, gate=None, forged=False):
        self.gate, self.forged, self.stream_calls = gate, forged, 0

    def stream_with_metadata(self, messages, **kwargs):
        self.stream_calls += 1
        completion = super().complete_with_metadata(messages, **kwargs)
        if self.forged:
            data = json.loads(completion.text)
            data["observations"][0]["source_message_id"] = "forged"
            completion.text = json.dumps(data, ensure_ascii=False)
        split = completion.text.index('"observations"') if '"observations"' in completion.text else len(completion.text) // 2
        yield ChatCompletionStreamChunk(delta=completion.text[:split])
        if self.gate is not None and not self.gate.wait(3):
            raise TimeoutError("test consumer did not release the gate")
        yield ChatCompletionStreamChunk(delta=completion.text[split:])
        yield ChatCompletionStreamChunk(completion=completion)


class ReplyStreamingTests(unittest.TestCase):
    def test_json_projection_handles_every_boundary_and_hides_nested_fields(self):
        text = '说“你好”\n再说\\路径 😀'
        raw = json.dumps({"metadata": {"reply": "secret nested reply"}, "other": 'literal "reply"', "reply": text, "observations": ["never emit"]}, ensure_ascii=True)
        for width in (1, 2, 7, 31):
            projector = ReplyProjector()
            parts = [projector.feed(raw[index:index + width]) for index in range(0, len(raw), width)]
            self.assertEqual("".join(parts), text)
            self.assertTrue(any(parts[:-1]))

    def test_agent_emits_before_full_validation_but_never_streams_judgment(self):
        deltas, completed = [], []
        class Client:
            def stream_with_metadata(self, messages, **kwargs):
                yield ChatCompletionStreamChunk(delta='{"reply":"先听您说')
                self_test.assertEqual(deltas, ["先听您说"])
                yield ChatCompletionStreamChunk(delta='。","observations":[]}')
                completed.append(True)
                yield ChatCompletionStreamChunk(completion=ChatCompletionResult(text='{"reply":"先听您说。","observations":[]}', finish_reason="stop"))
            def complete_with_metadata(self, messages, **kwargs):
                self_test.assertTrue(any("json" in item["content"].lower() for item in messages))
                return ChatCompletionResult(text='{"verdict":"matches","reason":"对应参考含义","source_message_id":"u1"}', finish_reason="stop")
        self_test = self
        agent = FreeformCourseAgent(client=Client(), on_reply=lambda text: (self.assertFalse(completed), deltas.append(text)))
        agent.reply([{"id": "u1", "role": "learner", "content": "例子"}])
        self.assertEqual("".join(deltas), "先听您说。")
        self.assertEqual(agent.call_log[0]["reply_delta_count"], 2)
        agent.evaluate_answer([{"id": "u1", "role": "learner", "content": "紧张"}], context={})
        self.assertEqual("".join(deltas), "先听您说。")

    def test_possible_reflection_hides_teaching_draft_streams_actor_only(self):
        client, deltas = StreamClient(), []
        runtime = FreeformCourseRuntime(agent=FreeformCourseAgent(client=client), on_reply=deltas.append)
        result = runtime.process(new_course_state("lesson-1", reflection_policy="per_turn"), [{"id": "u1", "role": "learner", "content": "5"}])
        self.assertTrue(result.trace["reflection_created"])
        self.assertEqual(client.stream_calls, 1)
        self.assertEqual([item["phase"] for item in runtime.model_calls if item.get("transport") == "stream"], ["guidance_actor"])
        self.assertTrue(deltas)

    def test_incomplete_model_stream_has_no_success(self):
        class Broken:
            def stream_with_metadata(self, *args, **kwargs):
                yield ChatCompletionStreamChunk(delta='{"reply":"还没有结束')
        agent = FreeformCourseAgent(client=Broken(), on_reply=lambda _: None)
        with self.assertRaises(RuntimeError):
            agent.reply([])
        self.assertEqual(agent.call_log[0]["status"], "error")


class DeepSeekTransportTests(unittest.TestCase):
    def test_nonstream_and_stream_use_json_mode_without_thinking_and_retain_usage(self):
        requests = []
        def opener(request, **kwargs):
            body = json.loads(request.data)
            requests.append(body)
            if body.get("stream"):
                events = [
                    {"choices": [{"delta": {"reasoning_content": "must never forward"}}]},
                    {"choices": [{"delta": {"content": '{"reply":"您好"}'}}]},
                    {"choices": [{"delta": {}, "finish_reason": "stop"}], "usage": {"total_tokens": 12}, "model": "deepseek-flash"},
                ]
                return Response(("".join("data: " + json.dumps(item) + "\n\n" for item in events) + "data: [DONE]\n\n").encode())
            return Response(json.dumps({"choices": [{"message": {"content": '{"reply":"您好"}'}, "finish_reason": "stop"}], "usage": {"total_tokens": 12}}).encode())
        client = DeepSeekChatCompletionsClient(api_key="offline-key", opener=opener)
        plain = client.complete_with_metadata([], response_format={"type": "json_object"})
        chunks = list(client.stream_with_metadata([], response_format={"type": "json_object"}))
        self.assertEqual(chunks[-1].completion.text, plain.text)
        self.assertEqual(chunks[-1].completion.usage["total_tokens"], 12)
        self.assertNotIn("must never forward", "".join(item.delta for item in chunks))
        for request in requests:
            self.assertEqual(request["thinking"], {"type": "disabled"})
            self.assertEqual(request["response_format"], {"type": "json_object"})
        self.assertTrue(requests[-1]["stream_options"]["include_usage"])

    def test_historical_assistant_format_cannot_override_reply_contract(self):
        client = DeepSeekChatCompletionsClient(api_key="offline")
        messages = [{"role": "assistant", "content": json.dumps({"id": "a1", "text": "先说一件小事"})},
                    {"role": "user", "content": json.dumps({"id": "u1", "text": "朋友没回消息"})}]
        original = json.loads(json.dumps(messages))
        body = json.loads(client._request(messages, temperature=1, max_completion_tokens=1200, response_format={"type": "json_object"}).data)
        self.assertFalse(any(item["role"] == "assistant" for item in body["messages"]))
        history = json.loads(body["messages"][-1]["content"])["messages"]
        self.assertEqual(history[0], {"id": "a1", "role": "agent", "content": "先说一件小事"})
        self.assertEqual(history[1]["id"], "u1")
        self.assertEqual(history[1]["role"], "learner")
        self.assertEqual(messages, original)

    def test_truncated_stream_and_missing_key_fail_without_fallback(self):
        client = DeepSeekChatCompletionsClient(api_key="offline", opener=lambda *a, **k: Response(b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'))
        with self.assertRaises(RuntimeError):
            list(client.stream_with_metadata([]))
        with patch.dict("os.environ", {"CBT_COURSE_PROVIDER": "deepseek", "DEEPSEEK_API_KEY": ""}):
            with self.assertRaisesRegex(RuntimeError, "DEEPSEEK_API_KEY"):
                FreeformCourseAgent._client_from_env()


class CourseStreamPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.engine = create_engine("sqlite:///" + (Path(self.directory.name) / "stream.db").as_posix(), connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        with self.sessions() as db:
            participant = Participant(label=uuid.uuid4().hex, invite_hash=hash_secret("offline-stream"))
            db.add(participant); db.flush()
            db.add(Consent(participant_id=participant.id, version=settings.consent_version))
            db.commit()
            conversation, _ = create_or_resume_course(db, participant_id=participant.id, lesson_id="lesson-1")
            self.participant_id, self.conversation_id = participant.id, conversation.id
            self.before = decrypt_json(conversation.agent_state_encrypted)

    def tearDown(self):
        self.engine.dispose()
        self.directory.cleanup()

    def events(self, client, key):
        return stream_course_turn(conversation_id=self.conversation_id, participant_id=self.participant_id,
            content="5", idempotency_key=key, session_factory=self.sessions,
            runtime_factory=lambda: FreeformCourseRuntime(agent=FreeformCourseAgent(client=client)))

    def test_real_time_projection_precedes_commit_then_success_and_idempotent_replay(self):
        gate, key = Event(), uuid.uuid4().hex
        client = StreamClient(gate=gate)
        stream = self.events(client, key)
        self.assertEqual(next(stream)["type"], "start")
        self.assertEqual(next(stream)["type"], "reply_delta")
        try:
            with self.sessions() as db:
                self.assertEqual(decrypt_json(db.get(Conversation, self.conversation_id).agent_state_encrypted), self.before)
                event = db.scalar(select(TurnEvent).where(TurnEvent.idempotency_key == key))
                self.assertEqual(event.status, "pending")
        finally:
            gate.set()
        result = list(stream)[-1]
        self.assertEqual(result["type"], "result")
        self.assertEqual(result["data"]["course"]["current_step"], "learn")
        replay = list(self.events(client, key))
        self.assertTrue(replay[-1]["data"]["deduplicated"])
        self.assertEqual(client.stream_calls, 1)
        self.assertNotIn("reply_delta", [item["type"] for item in replay])

    def test_forged_sources_emit_error_and_leave_no_assistant_or_state_commit(self):
        key = uuid.uuid4().hex
        events = list(self.events(StreamClient(forged=True), key))
        self.assertIn("reply_delta", [item["type"] for item in events])
        self.assertEqual(events[-1]["type"], "error")
        with self.sessions() as db:
            conversation = db.get(Conversation, self.conversation_id)
            self.assertEqual(decrypt_json(conversation.agent_state_encrypted), self.before)
            event = db.scalar(select(TurnEvent).where(TurnEvent.idempotency_key == key))
            self.assertEqual(event.status, "error")
            self.assertIsNone(event.assistant_message_id)
        retry = list(self.events(StreamClient(), key))[-1]
        self.assertEqual(retry["type"], "result")

    def test_disconnection_does_not_hang_worker_and_same_key_recovers_saved_turn(self):
        gate, committed, key = Event(), Event(), uuid.uuid4().hex
        client = StreamClient(gate=gate)
        def tracked(*args, **kwargs):
            result = process_course_turn(*args, **kwargs)
            committed.set()
            return result
        with patch("cbt_course_llm_freeform.streaming.process_course_turn", side_effect=tracked):
            stream = self.events(client, key)
            next(stream); next(stream)
            stream.close()
            gate.set()
            self.assertTrue(committed.wait(3))
        self.assertTrue(list(self.events(client, key))[-1]["data"]["deduplicated"])
        with self.sessions() as db:
            messages = db.scalars(select(Message).where(Message.conversation_id == self.conversation_id)).all()
            self.assertEqual(len(messages), 3)
