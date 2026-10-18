from __future__ import annotations

import copy
import json
import unittest
import uuid
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from cbt_course_llm_freeform.agent import FreeformCourseAgent
from cbt_course_llm_freeform.catalog import COURSE_CATALOG, lesson_version
from cbt_course_llm_freeform.design import PATHS, preview_examples
from cbt_course_llm_freeform.feedback import active_guidance
from cbt_course_llm_freeform.preview import PreviewClient
from cbt_course_llm_freeform.prompt import prompt_for_lesson
from cbt_course_llm_freeform.reflection import generate_course_reflection
from cbt_course_llm_freeform.runtime import FreeformCourseRuntime, can_reuse_case, course_payload, new_course_state
from cbt_course_llm_freeform.services import create_or_resume_course, process_course_turn, course_conversation_payload
from webapp.database import Base
from webapp.models import Participant
from webapp.security import decrypt_json, hash_secret
from webapp.services import full_export_payload


def runtime(lesson, client=None):
    return FreeformCourseRuntime(agent=FreeformCourseAgent(client=client or PreviewClient(), system_prompt=prompt_for_lesson(lesson)))


def step(state, text="", action="chat", client=None):
    return runtime(state["lesson_id"], client).process(state, [{"id": uuid.uuid4().hex, "role": "learner", "content": text or action}], action=action)


class EightLessonRuntimeTests(unittest.TestCase):
    def test_all_eight_are_available_with_distinct_prompts_and_versioned_state(self):
        prompts = set()
        for course in COURSE_CATALOG:
            self.assertTrue(course["available"])
            state = new_course_state(course["id"])
            self.assertEqual(state["lesson_version"], lesson_version(course["id"]))
            prompts.add(prompt_for_lesson(course["id"]))
        self.assertEqual(len(prompts), 8)

    def test_path_choice_is_required_but_checkin_can_be_answered_first(self):
        for lesson in PATHS:
            state = step(new_course_state(lesson), "最近六分").state
            self.assertTrue(course_payload(state)["needs_path_choice"])
            original = copy.deepcopy(state)
            with self.assertRaisesRegex(ValueError, "路径"):
                step(state, "我替系统选一条路径")
            self.assertEqual(state, original)
            choice = next(iter(PATHS[lesson].values()))
            result = step(state, action=choice["action"])
            self.assertEqual(result.trace["model_calls"], [])
            self.assertFalse(course_payload(result.state)["needs_path_choice"])

    def test_wrong_course_choice_and_silent_switch_are_rejected(self):
        state = step(new_course_state("lesson-5"), action="skip_checkin").state
        with self.assertRaises(ValueError):
            step(state, action="choose_sleep")
        selected = step(state, action="choose_activation").state
        with self.assertRaises(ValueError):
            step(selected, action="choose_exposure")
        self.assertEqual(selected["path"], "activation")

    def test_summary_authorization_does_not_promise_unavailable_case_copying(self):
        state = new_course_state("lesson-7")
        state["carryover"] = {"status": "offered", "summary": {"record": {"situation": {"value": "一件旧事"}}}}
        result = step(state, action="accept_carryover")
        self.assertNotIn("沿用这件事", result.reply)
        eighth = new_course_state("lesson-8")
        eighth["carryover"] = {"status": "offered", "kind": "course_review", "sources": []}
        self.assertIn("只作回顾", step(eighth, action="accept_carryover").reply)

    def test_other_path_fields_cannot_be_written_even_with_a_true_quote(self):
        state = step(step(new_course_state("lesson-7"), action="skip_checkin").state, action="choose_relaxation").state
        state["stage"] = "practice"
        class MixedPath(PreviewClient):
            @staticmethod
            def _teaching(context, latest):
                return {"reply": "继续。", "observations": [{"field": "sleep_pattern", "value": latest["text"], "source_message_id": latest["id"]}]}
        with self.assertRaisesRegex(RuntimeError, "字段"):
            step(state, "最近睡前反复看时间", client=MixedPath())
        self.assertEqual(state["draft_record"], {})

    def test_reflection_focus_must_belong_to_selected_path(self):
        state = new_course_state("lesson-7", reflection_policy="per_turn")
        state.update(stage="practice", path="relaxation")
        class WrongFocus(PreviewClient):
            @staticmethod
            def _reflection(context, latest):
                result = PreviewClient._reflection(context, latest)
                result["reflection"].update(strategy="clarify_missing_field", focus_field="sleep_habit")
                return result
        with self.assertRaisesRegex(RuntimeError, "字段"):
            step(state, "信号：我想放松一下", client=WrongFocus())
        self.assertEqual(state["draft_record"], {})
        state["workflow"]["active_reflection"] = {"id": "old-sleep", "stage": "practice", "path": "sleep", "case_id": state["case_id"], "ordinary_turn": 0, "strategy": "rephrase_plainly"}
        self.assertIsNone(active_guidance(state))

    def test_all_eight_local_safety_precedes_models_and_path_selection(self):
        for number in range(1, 9):
            result = step(new_course_state(f"lesson-{number}"), "我不想活了")
            self.assertTrue(result.state["safety_paused"])
            self.assertEqual(result.trace["model_calls"], [])


class EightLessonPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.db = self.Session()
        self.person = Participant(label=uuid.uuid4().hex, invite_hash=hash_secret("offline-eight"))
        self.db.add(self.person); self.db.commit()

    def tearDown(self):
        self.db.close(); self.engine.dispose()

    def start(self, lesson, policy="none", person=None):
        with patch.dict("os.environ", {"CBT_REFLECTION_POLICY": policy}):
            return create_or_resume_course(self.db, participant_id=(person or self.person).id, lesson_id=lesson)[0]

    def state(self, conversation):
        return decrypt_json(conversation.agent_state_encrypted)

    def turn(self, conversation, text="", action="chat", client=None):
        return process_course_turn(self.db, conversation, content=text, action=action, idempotency_key=uuid.uuid4().hex,
            expected_revision=self.state(conversation)["revision"], runtime_factory=lambda: runtime(conversation.lesson_id, client))

    def prepare(self, lesson, path=None, reference=False, policy="none"):
        conversation = self.start(lesson, policy)
        if reference and self.state(conversation)["carryover"]["status"] == "offered":
            self.turn(conversation, action="accept_carryover")
        self.turn(conversation, action="skip_checkin")
        if lesson in PATHS:
            path = path or next(iter(PATHS[lesson]))
            self.turn(conversation, action=PATHS[lesson][path]["action"])
        self.turn(conversation, preview_examples(self.state(conversation))["learn"])
        if reference and can_reuse_case(self.state(conversation)):
            self.turn(conversation, action="reuse_case")
        for _ in range(8):
            state = self.state(conversation)
            if state["stage"] != "practice":
                break
            self.turn(conversation, preview_examples(state)["practice"])
        self.assertEqual(self.state(conversation)["stage"], "review")
        if lesson == "lesson-3":
            self.turn(conversation, action="unsure_pattern")
        return conversation

    def finish(self, lesson, path=None, reference=False, policy="none"):
        conversation = self.prepare(lesson, path, reference, policy)
        self.turn(conversation, action="confirm_record")
        if lesson == "lesson-1":
            from cbt_course_llm_freeform.tests.check_helpers import complete_first_check
            complete_first_check(lambda text="", action="chat": self.turn(conversation, text, action=action))
        self.turn(conversation, action="decline_practice")
        self.turn(conversation, "生活例子比较容易懂，之后愿意按自己的节奏回看。")
        self.turn(conversation, action="finish")
        return conversation

    def test_every_course_and_both_paths_complete_without_prerequisites(self):
        for number in range(8, 0, -1):
            lesson = f"lesson-{number}"
            for path in PATHS.get(lesson, {None: {}}):
                with self.subTest(lesson=lesson, path=path):
                    conversation = self.finish(lesson, path)
                    artifact = self.state(conversation)["artifact"]
                    self.assertEqual(conversation.status, "completed")
                    self.assertEqual(artifact["path"], path)
                    self.assertEqual(artifact["record"]["path"], path)
                    self.assertEqual(artifact["application_status"], "not_measured")
                    self.assertEqual(artifact["schema_version"], "course-artifact/2")
                    if lesson in {"lesson-5", "lesson-7"}:
                        self.assertEqual(artifact["kind"], "action_plan")
                    self.assertNotIn("生活例子", conversation.agent_state_encrypted)

    def test_eight_course_chain_references_seven_current_confirmed_artifacts(self):
        sources = [self.finish(f"lesson-{number}", reference=True) for number in range(1, 8)]
        eighth = self.finish("lesson-8", reference=True)
        state = self.state(eighth)
        self.assertEqual(len(state["carryover"]["sources"]), 7)
        self.assertEqual(set(state["artifact"]["referenced_artifact_ids"]), {self.state(source)["artifact"]["artifact_id"] for source in sources})
        self.assertTrue(all(item["summary"]["reference_only"] for item in state["carryover"]["sources"]))
        self.assertTrue(all(item["summary"]["application_status"] == "not_measured" for item in state["carryover"]["sources"]))
        exported = full_export_payload(eighth)
        self.assertEqual(exported["course_learning_state"]["artifact"]["referenced_artifact_ids"], state["artifact"]["referenced_artifact_ids"])

    def test_case_reuse_does_not_convert_an_old_plan_into_a_new_action(self):
        source = self.finish("lesson-4")
        fifth = self.start("lesson-5")
        self.turn(fifth, action="accept_carryover")
        self.turn(fifth, action="skip_checkin")
        self.turn(fifth, action="choose_activation")
        self.turn(fifth, preview_examples(self.state(fifth))["learn"])
        self.turn(fifth, action="reuse_case")
        record = self.state(fifth)["draft_record"]
        self.assertEqual(set(record), {"situation"})
        self.assertEqual(record["situation"]["source_artifact_id"], self.state(source)["artifact"]["artifact_id"])
        self.assertIn("adopted_by_message_id", record["situation"])
        self.assertNotIn("first_step", record)

    def test_change_path_withdraws_confirmation_plan_and_old_guidance(self):
        fifth = self.prepare("lesson-5", "activation", policy="per_turn")
        self.turn(fifth, action="confirm_record")
        self.turn(fifth, action="accept_practice")
        old_case = self.state(fifth)["case_id"]
        self.turn(fifth, action="change_path")
        state = self.state(fifth)
        self.assertEqual((state["stage"], state["path"], state["draft_record"]), ("learn", None, {}))
        self.assertIsNone(state["confirmed_record"])
        self.assertEqual(state["learning_evidence"], [])
        self.assertEqual(state["practice_plan"]["status"], "undecided")
        self.assertIsNone(state["workflow"]["active_reflection"])
        self.assertNotEqual(state["case_id"], old_case)
        self.turn(fifth, action="choose_exposure")
        self.turn(fifth, preview_examples(self.state(fifth))["learn"])
        while self.state(fifth)["stage"] == "practice":
            self.turn(fifth, preview_examples(self.state(fifth))["practice"])
        self.turn(fifth, action="confirm_record")
        self.turn(fifth, action="decline_practice")
        self.turn(fifth, action="finish")
        self.assertEqual(self.state(fifth)["artifact"]["path"], "exposure")
        with self.assertRaises(ValueError):
            self.turn(fifth, action="change_path")

    def test_multi_source_review_revokes_deleted_and_old_version_sources(self):
        first = self.finish("lesson-1")
        second = self.finish("lesson-2")
        eighth = self.start("lesson-8")
        self.turn(eighth, action="accept_carryover")
        self.assertEqual(len(self.state(eighth)["carryover"]["sources"]), 2)
        self.db.delete(first); self.db.commit()
        refreshed = course_conversation_payload(eighth)["course"]["carryover"]
        self.assertEqual([item["summary"]["lesson_id"] for item in refreshed["sources"]], ["lesson-2"])
        second.lesson_version = "old-version"; self.db.commit()
        self.assertEqual(course_conversation_payload(eighth)["course"]["carryover"]["status"], "unavailable")

    def test_declined_review_is_not_in_model_context_or_artifact(self):
        self.finish("lesson-1")
        eighth = self.start("lesson-8")
        self.turn(eighth, action="decline_carryover")
        self.turn(eighth, action="skip_checkin")
        class Capture(PreviewClient):
            def complete_with_metadata(self, messages, **kwargs):
                self.context = json.loads(messages[1]["content"])["data"]
                return super().complete_with_metadata(messages, **kwargs)
        client = Capture()
        self.turn(eighth, preview_examples(self.state(eighth))["learn"], client=client)
        self.assertEqual(client.context["authorized_previous_lesson_summaries"], [])
        self.assertIsNone(client.context["authorized_previous_lesson_summary"])
        while self.state(eighth)["stage"] == "practice":
            self.turn(eighth, preview_examples(self.state(eighth))["practice"])
        self.turn(eighth, action="confirm_record")
        self.turn(eighth, action="decline_practice")
        self.turn(eighth, action="finish")
        self.assertEqual(self.state(eighth)["artifact"]["referenced_artifact_ids"], [])

    def test_foreign_and_v2_records_never_enter_review(self):
        first = self.finish("lesson-1")
        foreign = Participant(label=uuid.uuid4().hex, invite_hash=hash_secret("foreign"))
        self.db.add(foreign); self.db.commit()
        self.assertEqual(self.state(self.start("lesson-8", person=foreign))["carryover"]["status"], "unavailable")
        first.agent_version = "course-guided-v2"; first.lesson_version = "4.0-feedback-flow"
        self.db.commit()
        self.assertEqual(self.state(self.start("lesson-8"))["carryover"]["status"], "unavailable")
        with self.assertRaisesRegex(ValueError, "其他实现"):
            self.turn(first, "不能把旧课程继续写成新协议")

    def test_post_lesson_reflection_stays_independent_for_new_course(self):
        eighth = self.finish("lesson-8")
        before = copy.deepcopy(self.state(eighth)["artifact"])
        generate_course_reflection(eighth.id, session_factory=self.Session, client=PreviewClient())
        self.db.refresh(eighth)
        self.assertEqual(self.state(eighth)["reflection"]["status"], "ready")
        self.assertFalse(self.state(eighth)["reflection"]["applied"])
        self.assertEqual(self.state(eighth)["artifact"], before)
