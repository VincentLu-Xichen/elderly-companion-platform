from __future__ import annotations

import copy
import json
import unittest
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from cbt_course_llm_freeform.agent import FreeformCourseAgent
from cbt_course_llm_freeform.interaction import candidate
from cbt_course_llm_freeform.prompt import prompt_for_lesson
from cbt_course_llm_freeform.runtime import FreeformCourseRuntime, new_course_state
from cbt_course_llm_freeform.tests.test_practice_flow import DecisionAgent, turn
from daily_agent.azure_chat_client import ChatCompletionResult
from cbt_course_llm_freeform.interaction_memory import load_memories
from cbt_course_llm_freeform.services import create_or_resume_course, process_course_turn
from webapp.database import Base
from webapp.models import Conversation, InteractionReflectionMemory, Message, Participant, TurnEvent
from webapp.security import decrypt_json, encrypt_json, encrypt_text, hash_secret


class InteractionClient:
    def __init__(self, verdict="feedback", fail=False, invalid=False, scope="lesson", reply_length="short", follow_up="reduce"):
        self.verdict, self.fail, self.invalid, self.scope = verdict, fail, invalid, scope
        self.reply_length, self.follow_up = reply_length, follow_up
        self.calls = []

    def complete_with_metadata(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        if self.fail:
            raise TimeoutError("synthetic timeout")
        latest = json.loads(messages[-1]["content"])
        data = {"verdict": self.verdict, "source_message_id": "wrong" if self.invalid else latest["id"],
                "quote": latest["text"], "observation": "用户反对连续追问", "hypothesis": "追问可能造成负担",
                "alternative_explanation": "也可能只是本次话题不愿展开", "scope": self.scope,
                "reply_length": self.reply_length, "follow_up": self.follow_up, "reply": "收到，接下来按您的反馈调整讲法，继续当前练习。"}
        return ChatCompletionResult(text=json.dumps(data, ensure_ascii=False), model="test-model", finish_reason="stop")


class InteractionRuntimeTests(unittest.TestCase):
    def run_event(self, lesson="lesson-1", text="你烦不烦，一直追问", client=None, state=None):
        client = client or InteractionClient()
        state = state or new_course_state(lesson, reflection_policy="none")
        state["stage"] = "practice"
        result = FreeformCourseRuntime(agent=FreeformCourseAgent(client=client, system_prompt=prompt_for_lesson(lesson))).process(
            state, [{"id": "a", "role": "agent", "content": "为什么这样判断？"}, {"id": "u", "role": "learner", "content": text}])
        return result, client

    def test_feedback_uses_one_nonstreamed_llm_call_and_keeps_task_untouched_in_all_lessons(self):
        for n in (1, 2):
            with self.subTest(lesson=n):
                state = new_course_state(f"lesson-{n}", reflection_policy="per_turn")
                state["stage"] = "practice"
                before = copy.deepcopy(state)
                result, client = self.run_event(state=state)
                self.assertEqual(len(client.calls), 1)
                self.assertEqual(result.trace["model_calls"][0]["phase"], "interaction_reflection")
                for key in ("stage", "draft_record", "learning_evidence", "practice_flow", "learning_check"):
                    self.assertEqual(result.state.get(key), before.get(key))
                self.assertEqual(result.trace["interaction_event"]["status"], "accepted")
                self.assertNotIn("？", result.reply)
                self.assertEqual(result.state["interaction_memories"][0]["effect"], "not_measured")

    def test_ordinary_short_answers_and_plain_emotion_do_not_add_calls(self):
        for text in ("嗯", "不知道", "很烦", "今天很难受"):
            self.assertFalse(candidate(text))
        agent = DecisionAgent()
        state = new_course_state("lesson-1"); state["stage"] = "learn"
        result = turn(state, "嗯", agent=agent)
        self.assertEqual(agent.calls, 1)
        self.assertIsNone(result.trace["interaction_event"])

    def test_reported_and_negative_candidates_are_judged_not_assumed(self):
        for text in ("他问我你烦不烦", "我没有嫌你一直追问"):
            self.assertTrue(candidate(text))
            client = InteractionClient(verdict="not_feedback")
            # A rejected event returns to the ordinary teaching path.
            agent = FreeformCourseAgent(client=client)
            ordinary = DecisionAgent()
            agent.reply = ordinary.reply
            state = new_course_state("lesson-1", reflection_policy="none")
            state["stage"] = "learn"
            result = FreeformCourseRuntime(agent=agent).process(state, [{"id": "u", "role": "learner", "content": text}])
            self.assertEqual(ordinary.calls, 1)
            self.assertEqual(result.state["interaction_memories"], [])
            self.assertEqual(result.trace["interaction_event"]["verdict"], "not_feedback")

    def test_failure_or_invalid_source_does_not_create_memory_or_consume_answer(self):
        for client in (InteractionClient(fail=True), InteractionClient(invalid=True)):
            result, _ = self.run_event(client=client)
            self.assertEqual(result.trace["interaction_event"]["status"], "failed")
            self.assertEqual(result.state["interaction_memories"], [])
            self.assertEqual(result.state["practice_flow"]["unanswered"], {})
            self.assertEqual(result.state["draft_record"], {})

    def test_local_feedback_cannot_silently_become_cross_course(self):
        result, _ = self.run_event(client=InteractionClient(scope="cross_course"))
        self.assertEqual(result.state["interaction_memories"][0]["scope"], "lesson")
        result, _ = self.run_event(text="以后每节课都别一直追问", client=InteractionClient(scope="cross_course"))
        self.assertEqual(result.state["interaction_memories"][0]["scope"], "cross_course")

    def test_model_reply_receives_guidance_without_program_overwrite(self):
        result, _ = self.run_event()
        agent = DecisionAgent()
        followup = turn(result.state, "记不清", agent=agent)
        self.assertEqual(agent.context["interaction_guidance"]["follow_up"], "reduce")
        self.assertEqual(followup.reply, "会不会撞到人？身体一紧也算。")

    def test_safety_pause_happens_before_feedback_model(self):
        from cbt_course_llm_freeform.lesson_2 import HARD_SAFETY_SIGNALS
        client = InteractionClient()
        result, _ = self.run_event(text=HARD_SAFETY_SIGNALS[0] + "你烦不烦", client=client)
        self.assertEqual(client.calls, [])
        self.assertTrue(result.state["safety_paused"])


class InteractionPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="interaction-memory-test-")
        self.url = "sqlite:///" + (Path(self.directory.name) / "memory.db").as_posix()
        self.engine = create_engine(self.url)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.db = self.Session()
        self.person = Participant(label=uuid.uuid4().hex, invite_hash=hash_secret("offline"))
        self.db.add(self.person)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.directory.cleanup()

    def start(self, lesson="lesson-1", person=None):
        return create_or_resume_course(self.db, participant_id=(person or self.person).id, lesson_id=lesson)[0]

    def feedback(self, conversation, *, scope="lesson", key=None, fail=False, text=None, reply_length="short", follow_up="reduce"):
        client = InteractionClient(scope=scope, fail=fail, reply_length=reply_length, follow_up=follow_up)
        content = text or ("以后每节课都别一直追问" if scope == "cross_course" else "你烦不烦，一直追问")
        result = process_course_turn(self.db, conversation, content=content, idempotency_key=key or uuid.uuid4().hex,
            runtime_factory=lambda: FreeformCourseRuntime(agent=FreeformCourseAgent(client=client)))
        return result, client

    def test_encrypted_atomic_memory_and_idempotent_replay(self):
        conversation = self.start()
        key = uuid.uuid4().hex
        result, client = self.feedback(conversation, key=key)
        rows = self.db.scalars(select(InteractionReflectionMemory)).all()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertNotIn("追问", row.payload_encrypted)
        self.assertEqual(decrypt_json(row.payload_encrypted)["effect"], "not_measured")
        event = self.db.get(TurnEvent, row.turn_event_id)
        self.assertEqual(event.user_message_id, row.source_message_id)
        replay, client2 = self.feedback(conversation, key=key)
        self.assertEqual(client2.calls, [])
        self.assertEqual(result["reply"], replay["reply"])
        self.assertEqual(len(self.db.scalars(select(InteractionReflectionMemory)).all()), 1)

    def test_reopen_cross_course_isolation_and_source_deletion(self):
        first = self.start()
        self.feedback(first, scope="cross_course")
        second = self.start("lesson-2")
        other = Participant(label=uuid.uuid4().hex, invite_hash=hash_secret("other"))
        self.db.add(other); self.db.commit()
        other_course = self.start("lesson-2", other)
        self.assertEqual(load_memories(self.db, other_course), [])
        second_id, first_id = second.id, first.id
        self.db.close(); self.engine.dispose()
        self.engine = create_engine(self.url)
        self.db = sessionmaker(bind=self.engine, expire_on_commit=False)()
        second = self.db.get(Conversation, second_id)
        self.assertEqual(load_memories(self.db, second)[0]["follow_up"], "reduce")
        process_course_turn(self.db, second, content="", action="skip_checkin", idempotency_key=uuid.uuid4().hex)
        agent = DecisionAgent()
        process_course_turn(self.db, second, content="今天还好", idempotency_key=uuid.uuid4().hex,
            runtime_factory=lambda: FreeformCourseRuntime(agent=agent))
        self.assertEqual(agent.context["interaction_guidance"]["follow_up"], "reduce")
        self.db.delete(self.db.get(Conversation, first_id)); self.db.commit()
        self.assertEqual(load_memories(self.db, second), [])
        self.assertEqual(self.db.scalars(select(InteractionReflectionMemory)).all(), [])

    def test_local_feedback_not_carried_and_latest_guidance_wins(self):
        first = self.start()
        self.feedback(first)
        second = self.start("lesson-2")
        self.assertEqual(load_memories(self.db, second), [])
        self.feedback(first, scope="cross_course")
        old = load_memories(self.db, second)[0]["id"]
        self.feedback(second)
        current = load_memories(self.db, second)[0]
        self.assertNotEqual(current["id"], old)
        self.assertEqual(current["scope"], "lesson")

    def test_reflector_failure_is_audited_without_memory_write(self):
        conversation = self.start()
        self.feedback(conversation, fail=True)
        self.assertEqual(self.db.scalars(select(InteractionReflectionMemory)).all(), [])
        event = self.db.scalar(select(TurnEvent))
        trace = decrypt_json(event.trace_encrypted)
        self.assertEqual(trace["interaction_event"]["status"], "failed")
        self.assertEqual(trace["model_calls"][0]["status"], "error")

    def test_new_feedback_can_restore_normal_guidance_across_lessons(self):
        first = self.start()
        self.feedback(first, scope="cross_course")
        second = self.start("lesson-2")
        self.feedback(second, scope="cross_course", text="以后每节课可以讲详细一点，按需要正常问我",
                      reply_length="standard", follow_up="standard")
        memory = load_memories(self.db, first)[0]
        self.assertEqual(memory["reply_length"], "standard")
        self.assertEqual(memory["follow_up"], "standard")

    def test_overridden_task_actor_is_not_marked_as_displayed(self):
        from cbt_course_llm_freeform.preview import PreviewClient
        conversation = self.start()
        state = decrypt_json(conversation.agent_state_encrypted)
        state.pop("privacy")  # Legacy template override remains auditable; new practice keeps the Actor.
        state["stage"] = "practice"
        state["workflow"]["policy"] = "per_turn"
        conversation.agent_state_encrypted = encrypt_json(state); self.db.commit()
        process_course_turn(self.db, conversation, content="不知道", idempotency_key=uuid.uuid4().hex,
            runtime_factory=lambda: FreeformCourseRuntime(agent=FreeformCourseAgent(client=PreviewClient())))
        event = self.db.scalar(select(TurnEvent))
        trace = decrypt_json(event.trace_encrypted)
        self.assertTrue(trace["reflection_created"])
        self.assertFalse(trace["reflection_response_applied"])
        self.assertFalse(trace["guidance_reflection"]["applied"])
        self.assertNotIn("applied_to_message_id", trace["guidance_reflection"])

    def test_memory_and_assistant_reply_roll_back_together(self):
        from cbt_course_llm_freeform.interaction_memory import save_memory
        conversation = self.start()
        before = conversation.agent_state_encrypted
        def fail_after_add(*args):
            save_memory(*args)
            raise RuntimeError("synthetic storage failure")
        with patch("cbt_course_llm_freeform.services.save_memory", side_effect=fail_after_add):
            with self.assertRaises(RuntimeError):
                self.feedback(conversation)
        self.assertEqual(self.db.scalars(select(InteractionReflectionMemory)).all(), [])
        self.db.refresh(conversation)
        self.assertEqual(conversation.agent_state_encrypted, before)
        agents = self.db.scalars(select(Message).where(Message.conversation_id == conversation.id, Message.role == "agent")).all()
        self.assertEqual(len(agents), 1)  # Only the original introduction remains.

    def test_post_lesson_llm_keeps_older_feedback_and_its_context(self):
        from cbt_course_llm_freeform.reflection import generate_course_reflection
        conversation = self.start()
        self.feedback(conversation)
        memory = self.db.scalar(select(InteractionReflectionMemory))
        for index in range(44):
            self.db.add(Message(conversation_id=conversation.id, sequence=index + 4,
                role="learner" if index % 2 else "agent", content_encrypted=encrypt_text("后续合成对话")))
        state = decrypt_json(conversation.agent_state_encrypted)
        state.update(completed=True, reflection={"status": "pending"})
        conversation.status = "completed"
        conversation.agent_state_encrypted = encrypt_json(state)
        self.db.commit()
        class SummaryClient:
            data = None
            def complete_with_metadata(inner, messages, **kwargs):
                inner.data = json.loads(messages[-1]["content"])
                return ChatCompletionResult(text='{"observations":[],"suggestions":[],"hypotheses":[]}', model="summary-test", finish_reason="stop")
        client = SummaryClient()
        generate_course_reflection(conversation.id, session_factory=self.Session, client=client)
        self.assertIn(memory.source_message_id, {item["id"] for item in client.data["history"]})
        self.assertEqual(client.data["interaction_reflections"][0]["id"], memory.id)
        self.db.refresh(conversation)
        self.assertEqual(decrypt_json(conversation.agent_state_encrypted)["reflection"]["status"], "ready")
