import copy
import json
import tempfile
import unittest
import uuid
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from cbt_course_llm_freeform import case_review, interaction, learning_check
from cbt_course_llm_freeform.agent import FreeformCourseAgent
from cbt_course_llm_freeform.runtime import FreeformCourseRuntime, new_course_state
from cbt_course_llm_freeform.schemas import CaseReviewDecision
from cbt_course_llm_freeform.services import create_or_resume_course, process_course_turn
from daily_agent.azure_chat_client import ChatCompletionResult
from webapp.database import Base
from webapp.models import InteractionReflectionMemory, Participant
from webapp.security import decrypt_json, encrypt_json, hash_secret


def checking():
    state = new_course_state("lesson-1", reflection_policy="none")
    learning_check.begin(state)
    learning_check.save_answer(state, {"id": "first", "content": "别人打招呼时没有想到回应"}, "matches", "含义符合")
    return state


class Client:
    def __init__(self, action="stop_check", verdict="feedback", fail=False, missed=False, summary=None):
        self.action, self.verdict, self.fail, self.missed = action, verdict, fail, missed
        self.summary, self.calls = summary, []

    def complete_with_metadata(self, messages, **kwargs):
        prompt = messages[0]["content"]
        self.calls.append(prompt)
        if self.fail:
            raise TimeoutError("synthetic failure")
        if "COURSE_CASE_REVIEW" in prompt:
            output = self.summary or {"summary": "小陈看到活动取消，觉得白跑了一趟，感到失落，随后回家。", "source_message_ids": ["source"]}
        else:
            latest = json.loads(messages[-1]["content"])
            note = dict(verdict=self.verdict, source_message_id=latest["id"], quote=latest["text"],
                observation="本人表达本次题量负担", hypothesis="继续做题可能造成负担", alternative_explanation="也可能只是本次想休息",
                scope="lesson", reply_length="short", follow_up="standard", reply="抱歉让您觉得负担重了，我们先不继续剩下的题。",
                task_action=self.action, tone="polite")
            output = dict(verdict="unclear", reason="这是流程反馈", source_message_id=latest["id"], interaction=note) if "COURSE_CHECK_ANSWER" in prompt and self.missed else note
        return ChatCompletionResult(text=json.dumps(output, ensure_ascii=False), model="scripted", finish_reason="stop")


def run(state, text, client, action="chat"):
    return FreeformCourseRuntime(agent=FreeformCourseAgent(client=client)).process(state,
        [{"id": "current", "role": "learner", "content": text}], action=action)


def fictional_review():
    state = new_course_state("lesson-1", reflection_policy="none")
    state["stage"] = "review"
    state["practice_source"] = {"kind": "fictional", "material_id": "test", "story": "小陈参加活动，看到活动取消，想到白跑了一趟，失落，回家。"}
    state["draft_record"] = {key: {"value": value, "source_message_id": "source", "source_kind": "fictional", "case_id": state["case_id"]}
        for key, value in dict(situation="活动取消", thought="白跑了一堂", emotion="失落", behavior="回家").items()}
    return state


class FeedbackReviewTests(unittest.TestCase):
    def test_stop_remaining_keeps_prior_answer_and_adds_no_hint_or_wrong_answer(self):
        state = checking()
        first = copy.deepcopy(state["learning_check"]["answers"][0])
        result = run(state, "我不想做这么多题目", Client())
        check = result.state["learning_check"]
        self.assertEqual(result.state["stage"], "check_feedback")
        self.assertEqual(check["answers"][0], first)
        self.assertEqual([item["verdict"] for item in check["answers"]], ["matches"] + ["not_observed"] * 3)
        self.assertEqual(check["hints"], [])
        self.assertEqual(check["stopped_by"]["source_message_id"], "current")
        self.assertEqual(len(result.trace["model_calls"]), 1)
        self.assertEqual(result.trace["interaction_event"]["memory"]["applied_action"], "stop_check")
        self.assertNotIn("第 2/4", result.reply)

    def test_judge_can_report_a_candidate_miss_without_second_reflection(self):
        text = "这套练习就到这儿吧"
        self.assertFalse(interaction.candidate(text, task_feedback=True))
        result = run(checking(), text, Client(missed=True))
        self.assertEqual(result.state["stage"], "check_feedback")
        self.assertEqual([call["phase"] for call in result.trace["model_calls"]], ["learning_check"])
        self.assertEqual(result.state["learning_check"]["hints"], [])

    def test_only_style_adjustment_does_not_skip_or_count_as_answer(self):
        state = checking()
        result = run(state, "解释太长了", Client(action="continue"))
        self.assertEqual(result.state["learning_check"], state["learning_check"])
        self.assertEqual(result.state["stage"], "assessment")

    def test_pause_keeps_current_question_and_resume_restores_it(self):
        state = checking()
        result = run(state, "我先休息，暂停课程", Client(action="pause"))
        self.assertTrue(result.state["paused"])
        self.assertEqual(result.state["learning_check"], state["learning_check"])
        resumed = run(result.state, "resume", Client(), action="resume")
        self.assertFalse(resumed.state["paused"])
        self.assertEqual(resumed.state["learning_check"]["index"], 1)

    def test_not_feedback_is_not_permission_to_stop(self):
        # Reported or negated feedback may enter candidate detection; the judge
        # returns not_feedback and the answer judge must not turn it into a stop.
        state = checking()
        client = Client(verdict="not_feedback", action="continue", missed=True)
        result = run(state, "我没有说不想做这么多题，是转述别人", client)
        self.assertEqual(result.state["learning_check"], state["learning_check"])
        self.assertEqual(result.state["interaction_memories"], [])

    def test_failed_event_does_not_consume_answer_or_write_memory(self):
        state = checking()
        result = run(state, "我不想做这么多题目", Client(fail=True))
        self.assertEqual(result.state["learning_check"], state["learning_check"])
        self.assertEqual(result.state["interaction_memories"], [])
        self.assertEqual(result.trace["interaction_event"]["status"], "failed")

    def test_one_sentence_recap_keeps_typo_in_original_and_omits_missing_scores(self):
        state = fictional_review()
        client = Client()
        runtime = FreeformCourseRuntime(agent=FreeformCourseAgent(client=client))
        result = runtime._result(state, "old", "practice")
        self.assertIn("白跑了一趟", result.reply)
        self.assertEqual(result.state["draft_record"]["thought"]["value"], "白跑了一堂")
        self.assertNotIn("本次留空", result.reply)
        self.assertNotIn("相信程度", result.reply)
        runtime._result(result.state, "unchanged", "review")
        self.assertEqual(len(client.calls), 1)
        result.state["draft_record"]["thought"]["value"] = "没有白跑"
        runtime._result(result.state, "changed", "review")
        self.assertEqual(len(client.calls), 2)

    def test_invalid_recap_source_or_personal_identity_fails_without_modifying_facts(self):
        for output in ({"summary": "您白跑一趟。", "source_message_ids": ["source"]},
                       {"summary": "小陈失落。", "source_message_ids": ["foreign"]}):
            with self.subTest(output=output):
                state = fictional_review()
                original = copy.deepcopy(state["draft_record"])
                result = FreeformCourseRuntime(agent=FreeformCourseAgent(client=Client(summary=output)))._result(state, "old", "practice")
                self.assertEqual(result.state["draft_record"], original)
                self.assertEqual(result.state["blueprint"]["case_review"]["status"], "failed")
                self.assertEqual(result.trace["model_calls"][0]["status"], "error")
                self.assertNotIn("本次留空", result.reply)

    def test_new_task_candidates_are_not_enabled_for_other_lessons(self):
        self.assertFalse(interaction.candidate("我不想做这么多题"))
        self.assertTrue(interaction.candidate("我不想做这么多题", task_feedback=True))

    def test_database_dedup_restart_keeps_separate_encrypted_reflection_and_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = create_engine("sqlite:///" + (Path(directory) / "test.db").as_posix())
            Base.metadata.create_all(engine)
            factory = sessionmaker(bind=engine, expire_on_commit=False)
            client = Client()
            with factory() as db:
                person = Participant(label=uuid.uuid4().hex, invite_hash=hash_secret("test"))
                db.add(person); db.commit()
                course = create_or_resume_course(db, participant_id=person.id, lesson_id="lesson-1")[0]
                state = decrypt_json(course.agent_state_encrypted)
                learning_check.begin(state)
                course.agent_state_encrypted = encrypt_json(state); db.commit()
                kwargs = dict(content="我不想做这么多题", idempotency_key="same-feedback-123",
                    runtime_factory=lambda: FreeformCourseRuntime(agent=FreeformCourseAgent(client=client)))
                first = process_course_turn(db, course, **kwargs)
                second = process_course_turn(db, course, **kwargs)
                self.assertTrue(second["deduplicated"])
                self.assertEqual(len(client.calls), 1)
                rows = db.scalars(select(InteractionReflectionMemory)).all()
                self.assertEqual(len(rows), 1)
                self.assertNotIn("不想", rows[0].payload_encrypted)
                self.assertEqual(decrypt_json(rows[0].payload_encrypted)["task_action"], "stop_check")
                cid = course.id
            engine.dispose()
            from webapp.models import Conversation
            with factory() as reopened:
                saved = decrypt_json(reopened.get(Conversation, cid).agent_state_encrypted)
                self.assertEqual(saved["stage"], "check_feedback")
                self.assertTrue(all(item["verdict"] == "not_observed" for item in saved["learning_check"]["answers"]))
            engine.dispose()
