from __future__ import annotations

import copy
import unittest
import uuid
from unittest.mock import Mock

from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from cbt_course_llm_freeform.catalog import COURSE_CATALOG
from cbt_course_llm_freeform.prompt import prompt_for_lesson
from cbt_course_llm_freeform.reflection import generate_course_reflection
from cbt_course_llm_freeform.runtime import FreeformCourseRuntime, course_payload, new_course_state
from cbt_course_llm_freeform.schemas import CourseMessageCreate, Evidence, TeachingDecision
from cbt_course_llm_freeform.services import AGENT_VERSION, course_conversation_payload, create_or_resume_course, process_course_turn
from webapp.database import Base
from webapp.models import Conversation, Message, Participant, TurnEvent
from webapp.security import decrypt_json, encrypt_json, encrypt_text, hash_secret
from webapp.services import full_export_payload


def historical_state(number):
    return {
        "implementation": "guided_cbt_v3", "lesson_id": f"lesson-{number}",
        "lesson_version": "historical-test-version", "stage": "summary", "revision": 8,
        "completed": True, "draft_record": {},
        "confirmed_record": {"fields": {"situation": {"value": "合成历史案例", "source_message_id": "old-user"}}, "revision": 7},
        "practice_plan": {"status": "declined", "text": "未安排"},
        "reflection": {"status": "ready", "observations": [], "suggestions": [], "applied": False},
        "artifact": {"kind": "learning_record", "unknown_saved_field": "保留原快照"},
    }


class TwoLessonScopeTests(unittest.TestCase):
    def test_catalog_and_new_runtime_only_support_first_two(self):
        self.assertEqual([item["id"] for item in COURSE_CATALOG], ["lesson-1", "lesson-2"])
        for lesson in ("lesson-1", "lesson-2"):
            self.assertTrue(new_course_state(lesson))
            self.assertTrue(prompt_for_lesson(lesson))
        for number in range(3, 9):
            with self.subTest(lesson=number):
                with self.assertRaises(ValueError):
                    new_course_state(f"lesson-{number}")
                with self.assertRaises(ValueError):
                    prompt_for_lesson(f"lesson-{number}")
                runtime = FreeformCourseRuntime(agent=Mock())
                with self.assertRaises(ValueError):
                    runtime.process(historical_state(number), [{"id": "u", "role": "learner", "content": "继续"}])
                self.assertEqual(runtime.model_calls, [])

    def test_removed_fields_and_actions_are_not_accepted(self):
        for field in ("awareness_note", "action_fit", "graded_steps", "balanced_thought", "sleep_habit", "early_signal"):
            with self.assertRaises(ValidationError):
                Evidence(field=field, value="原话", source_message_id="u")
        for action in ("continue_skill", "choose_activation", "choose_sleep", "accept_pattern", "change_path"):
            with self.assertRaises(ValidationError):
                CourseMessageCreate(action=action, idempotency_key="scope-test")
        with self.assertRaises(ValidationError):
            TeachingDecision(reply="继续", domain_candidates=[{"category": "mind_reading"}])

    def test_archived_payload_only_reads_saved_data(self):
        for number in range(3, 9):
            state = historical_state(number)
            state["carryover"] = {"status": "unavailable"}
            before = copy.deepcopy(state)
            result = course_payload(state)
            self.assertEqual(result["record"][0]["value"], "合成历史案例")
            self.assertTrue(result["archived"])
            self.assertFalse(result["lesson"]["available"])
            self.assertFalse(result["can_reuse_case"])
            self.assertEqual(result["stages"], [])
            self.assertEqual(state, before)


class RetiredLessonPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.db = self.sessions()
        self.person = Participant(label=uuid.uuid4().hex, invite_hash=hash_secret("offline-scope"))
        self.db.add(self.person)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def historical(self, number=3):
        state = historical_state(number)
        row = Conversation(participant_id=self.person.id, mode="cbt", agent_version=AGENT_VERSION,
            agent_prompt_hash="saved-prompt-fingerprint", lesson_id=state["lesson_id"],
            lesson_version=state["lesson_version"], status="completed", agent_state_encrypted=encrypt_json(state))
        self.db.add(row)
        self.db.flush()
        self.db.add(Message(id="old-user", conversation_id=row.id, role="learner", sequence=1, content_encrypted=encrypt_text("合成历史案例")))
        self.db.commit()
        return row

    def test_retired_creation_and_continuation_rejected_without_messages(self):
        for number in range(3, 9):
            with self.assertRaises(ValueError):
                create_or_resume_course(self.db, participant_id=self.person.id, lesson_id=f"lesson-{number}")
        row = self.historical()
        before = row.agent_state_encrypted
        factory = Mock()
        with self.assertRaisesRegex(ValueError, "仅支持查看"):
            process_course_turn(self.db, row, content="继续", idempotency_key="retired-retry", runtime_factory=factory)
        factory.assert_not_called()
        self.assertEqual(row.agent_state_encrypted, before)
        self.assertEqual(len(row.messages), 1)
        self.assertEqual(self.db.scalars(select(TurnEvent)).all(), [])

    def test_owned_history_export_and_delete_keep_saved_artifact(self):
        from cbt_course_llm_freeform.services import get_owned_course
        row = self.historical()
        before = decrypt_json(row.agent_state_encrypted)
        payload = course_conversation_payload(row)
        self.assertTrue(payload["read_only"])
        self.assertEqual(payload["messages"][0]["content"], "合成历史案例")
        self.assertEqual(full_export_payload(row)["course_learning_state"], before)
        self.assertIsNone(get_owned_course(self.db, conversation_id=row.id, participant_id="foreign-user"))
        row_id = row.id
        self.db.delete(row)
        self.db.commit()
        self.assertIsNone(self.db.get(Conversation, row_id))
        self.assertIsNone(self.db.get(Message, "old-user"))

    def test_retired_reflection_does_not_call_model_or_mutate_snapshot(self):
        row = self.historical()
        state = decrypt_json(row.agent_state_encrypted)
        state["reflection"] = {"status": "pending"}
        row.agent_state_encrypted = encrypt_json(state)
        self.db.commit()
        client = Mock()
        generate_course_reflection(row.id, session_factory=self.sessions, client=client)
        client.complete_with_metadata.assert_not_called()
        self.db.refresh(row)
        self.assertEqual(decrypt_json(row.agent_state_encrypted), state)
        self.assertEqual(self.db.scalars(select(TurnEvent)).all(), [])
