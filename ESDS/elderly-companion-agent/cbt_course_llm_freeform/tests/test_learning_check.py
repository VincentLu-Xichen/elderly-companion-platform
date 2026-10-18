from __future__ import annotations

import copy
import json
import unittest
import uuid
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from cbt_course_llm_freeform.agent import FreeformCourseAgent
from cbt_course_llm_freeform.preview import PreviewClient
from cbt_course_llm_freeform.prompt import prompt_for_lesson
from cbt_course_llm_freeform.reflection import generate_course_reflection
from cbt_course_llm_freeform.runtime import FreeformCourseRuntime, course_payload, new_course_state
from cbt_course_llm_freeform.services import create_or_resume_course, process_course_turn
from webapp.database import Base
from webapp.models import Message, Participant, TurnEvent
from webapp.security import decrypt_json, hash_secret


def runtime(client=None):
    return FreeformCourseRuntime(agent=FreeformCourseAgent(client=client or PreviewClient(), system_prompt=prompt_for_lesson("lesson-1")))


def step(state, text="", action="chat", client=None):
    return runtime(client).process(state, [{"id": uuid.uuid4().hex, "role": "learner", "content": text or action}], action=action)


def prepared():
    state = step(new_course_state("lesson-1", reflection_policy="none"), action="skip_checkin").state
    state = step(state, "这是他的想法，失落是心情。").state
    state = step(state, "事情：女儿没接电话；想法：她是不是嫌我烦；心情：失落；做法：没有再联系").state
    return step(state, action="confirm_record").state


class LearningCheckRuntimeTests(unittest.TestCase):
    def test_full_mixed_attempt_retry_and_confirmed_goal_preserve_first_answers(self):
        state = prepared()
        self.assertEqual(state["stage"], "assessment")
        self.assertEqual(len(course_payload(state)["stages"]), 9)
        with self.assertRaises(ValueError):
            step(state, action="continue_after_check")
        for answer in ("邻居向他问好", "怕对方觉得他没礼貌", "对方觉得他没礼貌"):
            state = step(state, answer).state
            self.assertNotIn("result", course_payload(state)["learning_check"])
            self.assertNotIn("紧张。", json.dumps(course_payload(state), ensure_ascii=False))
        state = step(state, action="request_check_hint").state
        state = step(state, "低头了").state
        first = copy.deepcopy(state["learning_check"]["answers"])
        self.assertEqual(first[2]["verdict"], "does_not_match")
        self.assertTrue(first[3]["assisted"])
        state = step(state, action="start_check_retry").state
        state = step(state, "今天的安排全乱了").state
        self.assertEqual(course_payload(state)["learning_check"]["result"]["retry_attempt"], [])
        state = step(state, "失望").state
        self.assertEqual(state["learning_check"]["answers"], first)
        state = step(state, action="continue_after_check").state
        state = step(state, "我想先分清等待回复时的事情与猜测。").state
        self.assertEqual(state["stage"], "learning_goal")
        self.assertNotIn("learning_goal", state)
        state = step(state, action="confirm_learning_goal").state
        state = step(state, action="decline_practice").state
        state = step(state, action="finish").state
        self.assertTrue(state["completed"])
        self.assertEqual(state["artifact"]["learning_result"]["first_attempt"][2]["verdict"], "does_not_match")
        self.assertEqual(state["learning_goal"]["status"], "confirmed")

    def test_no_answer_leak_skips_and_repeat_are_not_concept_help(self):
        state = prepared()
        with patch.dict("os.environ", {"CBT_PREVIEW_MODE": "false", "CBT_COURSE_PROVIDER": "dashscope"}):
            payload = course_payload(state)
            self.assertNotIn("assessment", payload["preview_examples"])
            self.assertNotIn("expected", json.dumps(payload["learning_check"]))
            self.assertNotIn("没礼貌？", payload["preview_examples"]["learning_goal"])
        state = step(state, "请再读一遍").state
        self.assertEqual(state["learning_check"]["hints"], [])
        for _ in range(4):
            state = step(state, action="skip_check_question").state
        self.assertTrue(all(item["verdict"] == "not_observed" for item in state["learning_check"]["answers"]))
        other = new_course_state("lesson-2")
        with self.assertRaises(ValueError):
            step(other, action="request_check_hint")

    def test_failed_or_forged_judgment_does_not_change_candidate(self):
        state = prepared()
        before = copy.deepcopy(state)
        class Forged(PreviewClient):
            @staticmethod
            def _check(context, latest):
                return {"verdict": "matches", "reason": "一个判读", "source_message_id": "foreign-answer"}
        with self.assertRaises(RuntimeError):
            step(state, "邻居向他问好", client=Forged())
        self.assertEqual(state, before)


class LearningCheckPersistenceTests(unittest.TestCase):
    def test_failed_grading_retry_idempotency_encryption_and_postcheck_reflection(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        sessions = sessionmaker(bind=engine, expire_on_commit=False)
        try:
            with sessions() as db:
                person = Participant(label=uuid.uuid4().hex, invite_hash=hash_secret("offline-check"))
                db.add(person); db.commit()
                conversation, _ = create_or_resume_course(db, participant_id=person.id, lesson_id="lesson-1")

                def turn(text="", action="chat", key=None, client=None):
                    return process_course_turn(db, conversation, content=text, action=action, idempotency_key=key or uuid.uuid4().hex,
                        runtime_factory=lambda: runtime(client))

                turn(action="skip_checkin")
                turn("这是想法，失落是心情。")
                turn("事情：女儿没回电话；想法：她是不是嫌我烦；心情：失落；做法：没再联系")
                turn(action="confirm_record")
                before = copy.deepcopy(decrypt_json(conversation.agent_state_encrypted))
                class Broken(PreviewClient):
                    def complete_with_metadata(self, messages, **kwargs):
                        if "COURSE_CHECK_ANSWER" in messages[0]["content"]:
                            raise TimeoutError("offline failed grading")
                        return super().complete_with_metadata(messages, **kwargs)
                key = uuid.uuid4().hex
                with self.assertRaises(TimeoutError):
                    turn("邻居向他问好", key=key, client=Broken())
                self.assertEqual(decrypt_json(conversation.agent_state_encrypted), before)
                event = db.scalar(select(TurnEvent).where(TurnEvent.idempotency_key == key))
                self.assertEqual(decrypt_json(event.trace_encrypted)["failed_attempts"][0]["model_calls"][0]["phase"], "learning_check")
                turn("邻居向他问好", key=key)
                self.assertTrue(turn("邻居向他问好", key=key)["deduplicated"])
                self.assertEqual(len(decrypt_json(conversation.agent_state_encrypted)["learning_check"]["answers"]), 1)
                for text in ("怕别人觉得自己没礼貌", "紧张", "低头，没有回应"):
                    turn(text)
                turn(action="continue_after_check")
                turn(action="skip_learning_goal")
                turn(action="decline_practice")
                turn(action="finish")
                generate_course_reflection(conversation.id, session_factory=sessions, client=PreviewClient())
                db.refresh(conversation)
                state = decrypt_json(conversation.agent_state_encrypted)
                self.assertEqual(state["reflection"]["status"], "ready")
                self.assertTrue(state["reflection"]["hypotheses"])
                self.assertNotIn("邻居向他问好", conversation.agent_state_encrypted)
                learner = db.get(Message, state["reflection"]["hypotheses"][0]["source_message_ids"][0])
                self.assertEqual(learner.role, "learner")
                self.assertEqual(conversation.status, "completed")
        finally:
            engine.dispose()
