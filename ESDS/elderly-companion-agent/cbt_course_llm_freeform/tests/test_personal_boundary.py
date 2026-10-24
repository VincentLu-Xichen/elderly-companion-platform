from __future__ import annotations

import json
import tempfile
import unittest
import uuid
from collections import deque
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from cbt_course_llm_freeform import boundaries
from cbt_course_llm_freeform.agent import FreeformCourseAgent
from cbt_course_llm_freeform.interaction_memory import load_boundary, load_memories
from cbt_course_llm_freeform.memory import offer_previous_summary
from cbt_course_llm_freeform.preview import PreviewClient
from cbt_course_llm_freeform.runtime import FreeformCourseRuntime, new_course_state
from cbt_course_llm_freeform.services import AGENT_VERSION, create_or_resume_course, process_course_turn
from daily_agent.azure_chat_client import ChatCompletionResult
from webapp.database import Base
from webapp.models import Conversation, InteractionReflectionMemory, Message, Participant, TurnEvent
from webapp.security import decrypt_json, encrypt_json, hash_secret


class BoundaryClient(PreviewClient):
    """Scripted semantic verdicts exercise the real model protocol, not a rule simulation claim."""
    def __init__(self, intents=(), fallback_intent=None, fail=False):
        self.intents = deque(intents)
        self.calls = []
        self.fallback_intent, self.fail = fallback_intent, fail

    def decision(self, latest, context, intent):
        pending = context.get("personal_disclosure", {}).get("pending")
        if intent == "refuse_personal" and not pending:
            reply = "可以，这件事先不谈。以后课程也用虚构例子，不主动问您的个人经历，可以吗？"
        elif intent == "unclear" and not context["personal_disclosure"]["clarified"]:
            reply = "您是只想略过这一项，还是这次不想谈自己的经历？"
        elif intent in {"allow_all", "use_personal_once"}:
            reply = "明白，我们按您这次的意愿练习。您愿意用哪件小事来练习？"
        elif intent == "pause":
            reply = "我们先暂停，之后准备好再继续。"
        elif intent == "refuse_field":
            reply = "这一项先留空，我们接着看下一部分。"
        else:
            reply = "我们用虚构案例继续：" + boundaries.STORY + "案例中发生了什么事？"
        return {"verdict": "not_feedback" if intent == "none" else "feedback", "personal_intent": intent,
                "source_message_id": latest["id"], "quote": latest["text"],
                "observation": "本轮表达了需要核对的交流边界", "hypothesis": "个人经历询问可能造成负担",
                "alternative_explanation": "也可能仅是这次话题不愿展开", "scope": "cross_course" if intent in {"confirm_all", "allow_all"} else "lesson",
                "reply_length": "standard", "follow_up": "standard", "reply": reply}

    def complete_with_metadata(self, messages, **kwargs):
        context = json.loads(messages[1]["content"])["data"]
        latest = json.loads(messages[-1]["content"])
        phase = "judge" if messages[0]["content"].startswith("你是课程互动反馈") else "teaching"
        self.calls.append(phase)
        if phase == "judge":
            if self.fail:
                raise TimeoutError("synthetic failure")
            data = self.decision(latest, context, self.intents.popleft() if self.intents else "none")
            return ChatCompletionResult(text=json.dumps(data, ensure_ascii=False), model="boundary-test", finish_reason="stop")
        if self.fallback_intent:
            data = {"reply": "本轮不作为课程答案。", "interaction": self.decision(latest, context, self.fallback_intent)}
            return ChatCompletionResult(text=json.dumps(data, ensure_ascii=False), model="boundary-test", finish_reason="stop")
        return super().complete_with_metadata(messages, **kwargs)


def run(state, text, client, message_id="u"):
    return FreeformCourseRuntime(agent=FreeformCourseAgent(client=client)).process(state,
        [{"id": "a", "role": "agent", "content": "最近有没有愿意聊的个人经历？"}, {"id": message_id, "role": "learner", "content": text}])


class BoundaryRuntimeTests(unittest.TestCase):
    def practice(self):
        state = new_course_state("lesson-1", reflection_policy="none")
        state["stage"] = "practice"
        return state

    def test_refusal_replaces_whole_case_and_preserves_history_without_consuming_answer(self):
        state = self.practice()
        state["draft_record"] = {"situation": {"value": "私事", "source_message_id": "old"}}
        old_case = state["case_id"]
        result = run(state, "我不是很想说关于我的事情", BoundaryClient(["refuse_personal"]))
        self.assertTrue(result.state["privacy"]["pending"])
        self.assertEqual(result.state["draft_record"], {})
        self.assertNotEqual(result.state["case_id"], old_case)
        self.assertEqual(result.state["privacy"]["archived"][0]["record"]["situation"]["value"], "私事")
        self.assertEqual(result.state["practice_flow"]["unanswered"], {})
        self.assertTrue(boundaries.fictional(result.state))
        self.assertEqual(result.trace["boundary_event"]["memory"]["status"], "pending")

    def test_confirmation_uses_two_sources_and_no_second_judge(self):
        state = run(self.practice(), "不想说自己的事", BoundaryClient(["refuse_personal"]), "refusal").state
        client = BoundaryClient(["confirm_all"])
        result = run(state, "好，以后都用虚构例子", client, "confirmation")
        self.assertEqual(client.calls, ["judge"])
        note = result.trace["boundary_event"]["memory"]
        self.assertEqual([item["message_id"] for item in note["evidence"]], ["refusal", "confirmation"])
        self.assertEqual(note["scope"], "cross_course")
        self.assertIsNone(result.state["privacy"]["pending"])
        self.assertIn(boundaries.STORY, result.reply)

    def test_ignored_and_local_confirmation_never_grant_global_scope(self):
        for intent, text in (("local_only", "只是这次不想说"), ("none", "继续吧"), ("unclear", "嗯随便")):
            state = run(self.practice(), "不想谈自己的事", BoundaryClient(["refuse_personal"]), "refusal").state
            result = run(state, text, BoundaryClient([intent]))
            self.assertIsNone(result.state["privacy"]["pending"])
            self.assertEqual(result.trace["boundary_event"]["memory"]["scope"], "lesson")
            self.assertEqual(result.state.get("disclosure_boundary"), None)

    def test_ambiguous_model_global_classification_is_not_accepted_as_consent(self):
        state = run(self.practice(), "不想谈自己的事", BoundaryClient(["refuse_personal"]), "refusal").state
        result = run(state, "嗯随便", BoundaryClient(["confirm_all"]))
        self.assertEqual(result.trace["boundary_event"]["memory"]["scope"], "lesson")
        self.assertIsNone(result.state.get("disclosure_boundary"))

    def test_unasked_confirmation_never_creates_a_pending_question(self):
        class MissingQuestion(BoundaryClient):
            def decision(self, latest, context, intent):
                data = super().decision(latest, context, intent)
                data["reply"] = "我们改用案例继续。"
                return data
        result = run(self.practice(), "不想谈自己的事", MissingQuestion(["refuse_personal"]))
        self.assertEqual(result.trace["interaction_event"]["status"], "failed")
        self.assertIn("not actually asked", result.trace["interaction_event"]["validation_reason"])
        self.assertIsNone(result.state["privacy"]["pending"])

    def test_unclear_only_clarifies_once_then_uses_fictional_case(self):
        first = run(self.practice(), "不想说这个", BoundaryClient(["unclear"]))
        self.assertTrue(first.state["privacy"]["clarified"])
        second = run(first.state, "不想说这个", BoundaryClient(["unclear"]))
        self.assertTrue(boundaries.fictional(second.state))
        self.assertEqual(second.trace["boundary_event"]["memory"]["scope"], "lesson")
        self.assertIsNone(second.state["privacy"]["pending"])

    def test_single_field_is_not_a_whole_case_boundary(self):
        result = run(self.practice(), "这一项不愿回答，但可以继续聊这件事", BoundaryClient(["refuse_field"]))
        self.assertFalse(boundaries.fictional(result.state))
        self.assertEqual(set(result.state["practice_flow"]["deferred"]), {"situation"})
        self.assertFalse(result.state["privacy"]["local_block"])

    def test_direct_global_and_revoke_and_once_authorization(self):
        first = run(self.practice(), "以后每节课都不想谈自己的经历", BoundaryClient(["confirm_all"]))
        self.assertIsNone(first.state["privacy"]["pending"])
        once = run(first.state, "我愿意用我这次的经历练习", BoundaryClient(["use_personal_once"]))
        self.assertFalse(boundaries.blocked(once.state))
        self.assertEqual(once.state["disclosure_boundary"]["behavior"], "do_not_solicit")
        revoked = run(first.state, "以后也可以问我的经历", BoundaryClient(["allow_all"]))
        self.assertEqual(revoked.state["disclosure_boundary"]["behavior"], "allow_invitation")
        self.assertFalse(boundaries.fictional(revoked.state))

    def test_negation_and_report_are_judged_without_creating_boundary(self):
        for text in ("我没有不想谈自己的事情", "朋友说他不想谈自己的事情"):
            client = BoundaryClient(["none"])
            result = run(self.practice(), text, client)
            self.assertEqual(client.calls, ["judge", "teaching"])
            self.assertNotIn("boundary_event", result.state)
            self.assertFalse(boundaries.blocked(result.state))

    def test_ordinary_teaching_can_report_a_missed_candidate_without_another_call(self):
        client = BoundaryClient(fallback_intent="refuse_personal")
        result = run(self.practice(), "我们换成别人的故事吧", client)
        self.assertEqual(client.calls, ["teaching"])
        self.assertTrue(boundaries.fictional(result.state))
        self.assertEqual(result.state["draft_record"], {})

    def test_a_judged_message_is_not_reclassified_by_the_teaching_model(self):
        client = BoundaryClient(["none"], fallback_intent="refuse_personal")
        result = run(self.practice(), "我没有不想谈自己的事情", client)
        self.assertEqual(client.calls, ["judge", "teaching"])
        self.assertNotIn("boundary_event", result.state)
        self.assertFalse(boundaries.blocked(result.state))

    def test_judge_failure_does_not_write_or_resume_sensitive_questioning(self):
        result = run(self.practice(), "不想谈自己的事", BoundaryClient(fail=True))
        self.assertEqual(result.trace["interaction_event"]["status"], "failed")
        self.assertIsNone(result.trace["boundary_event"])
        self.assertTrue(boundaries.blocked(result.state))
        self.assertEqual(result.state["draft_record"], {})

    def test_pause_and_model_reply_are_preserved(self):
        result = run(self.practice(), "不想聊这个了，先暂停", BoundaryClient(["pause"]))
        self.assertTrue(result.state["paused"])
        state = self.practice()
        from cbt_course_llm_freeform.tests.test_practice_flow import DecisionAgent
        from cbt_course_llm_freeform.schemas import AgentResult, TeachingDecision
        model = DecisionAgent()
        model.reply = lambda history, context: AgentResult(reply="我们先留意这件事里实际发生的部分。", decision=TeachingDecision(reply="我们先留意这件事里实际发生的部分。"))
        result = FreeformCourseRuntime(agent=model).process(state, [{"id": "u", "role": "learner", "content": "我在想"}])
        self.assertEqual(result.reply, "我们先留意这件事里实际发生的部分。")

    def test_boundary_changes_after_practice_do_not_rewrite_confirmed_material(self):
        state = self.practice()
        state["disclosure_boundary"] = {"id": "prior", "behavior": "do_not_solicit", "scope": "cross_course"}
        boundaries.ensure(state)
        state["confirmed_record"] = {"source_kind": "fictional", "fields": {"situation": {"value": "活动取消"}}}
        state["stage"] = "assessment"
        before = json.loads(json.dumps(state["confirmed_record"]))
        result = run(state, "以后也可以问我的经历", BoundaryClient(["allow_all"]))
        self.assertEqual(result.state["confirmed_record"], before)
        self.assertTrue(boundaries.fictional(result.state))
        self.assertEqual(result.state["disclosure_boundary"]["behavior"], "allow_invitation")

    def test_other_lessons_use_sourced_material_and_cannot_import_a_personal_case(self):
        from cbt_course_llm_freeform.runtime import can_reuse_case
        from cbt_course_llm_freeform.schemas import AgentResult, TeachingDecision
        class CaptureAgent:
            def lesson2_turn(inner, history, *, context):
                from cbt_course_llm_freeform.lesson2_flow import Decision
                from cbt_course_llm_freeform.schemas import StageResult
                inner.context = context
                return StageResult(completion=None, decision=Decision(reply="继续当前案例。"))
            def reply(inner, history, *, context):
                inner.context = context
                return AgentResult(reply="我们继续辨认案例内容。", decision=TeachingDecision(reply="我们继续辨认案例内容。"))
        for number in (2,):
            state = new_course_state(f"lesson-{number}", reflection_policy="none")
            state["stage"] = "practice"
            state["disclosure_boundary"] = {"id": "boundary", "scope": "cross_course", "behavior": "do_not_solicit"}
            state["carryover"] = {"status": "accepted", "summary": {"record": {"situation": {"value": "旧私事"}}}}
            agent = CaptureAgent()
            result = FreeformCourseRuntime(agent=agent).process(state, [{"id": "u", "role": "learner", "content": "可以继续"}])
            self.assertTrue(boundaries.fictional(result.state))
            self.assertFalse(can_reuse_case(result.state))
            self.assertEqual(agent.context["practice_source"]["kind"], "fictional")


class BoundaryPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="boundary-tests-")
        self.engine = create_engine("sqlite:///" + (Path(self.temp.name) / "db.sqlite").as_posix())
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.db = self.Session()
        self.person = Participant(label=uuid.uuid4().hex, invite_hash=hash_secret("test"))
        self.db.add(self.person); self.db.commit()
        self.course = create_or_resume_course(self.db, participant_id=self.person.id, lesson_id="lesson-1")[0]
        state = decrypt_json(self.course.agent_state_encrypted)
        state["stage"] = "practice"
        self.course.agent_state_encrypted = encrypt_json(state); self.db.commit()

    def tearDown(self):
        self.db.close(); self.engine.dispose(); self.temp.cleanup()

    def send(self, text="", intent=None, action="chat", key=None, conversation=None):
        client = BoundaryClient([intent] if intent else [])
        response = process_course_turn(self.db, conversation or self.course, content=text, action=action,
            idempotency_key=key or uuid.uuid4().hex, runtime_factory=lambda: FreeformCourseRuntime(agent=FreeformCourseAgent(client=client)))
        return response

    def test_pending_local_confirmed_memory_restart_dedup_and_isolation(self):
        self.send("不想说自己的事", "refuse_personal")
        second = create_or_resume_course(self.db, participant_id=self.person.id, lesson_id="lesson-2")[0]
        self.assertIsNone(load_boundary(self.db, second))
        key = uuid.uuid4().hex
        self.send("好，以后都用虚构例子", "confirm_all", key=key)
        self.assertTrue(self.send("好，以后都用虚构例子", "confirm_all", key=key)["deduplicated"])
        rows = self.db.scalars(select(InteractionReflectionMemory)).all()
        self.assertEqual(len(rows), 2)
        self.assertNotIn("不想", rows[0].payload_encrypted)
        other = Participant(label=uuid.uuid4().hex, invite_hash=hash_secret("other"))
        self.db.add(other); self.db.commit()
        other_course = create_or_resume_course(self.db, participant_id=other.id, lesson_id="lesson-2")[0]
        self.assertIsNone(load_boundary(self.db, other_course))
        with self.Session() as reopened:
            self.assertEqual(load_boundary(reopened, reopened.get(Conversation, second.id))["behavior"], "do_not_solicit")
        self.send(action="skip_checkin", conversation=second)
        self.send("想法不同心情也会不同", conversation=second)
        state = decrypt_json(second.agent_state_encrypted)
        self.assertTrue(boundaries.fictional(state))

    def test_style_records_cannot_displace_boundary_and_missing_original_invalidates_confirmation(self):
        self.send("不想说自己的事", "refuse_personal")
        self.send("以后都这样", "confirm_all")
        original = self.db.scalar(select(InteractionReflectionMemory).where(InteractionReflectionMemory.status == "pending"))
        for _ in range(5):
            from cbt_course_llm_freeform.tests.test_interaction_reflection import InteractionClient
            process_course_turn(self.db, self.course, content="你烦不烦，一直追问", idempotency_key=uuid.uuid4().hex,
                runtime_factory=lambda: FreeformCourseRuntime(agent=FreeformCourseAgent(client=InteractionClient())))
        self.assertEqual(len(load_memories(self.db, self.course)), 3)
        self.assertEqual(load_boundary(self.db, self.course)["behavior"], "do_not_solicit")
        self.db.delete(self.db.get(Message, original.source_message_id)); self.db.commit()
        self.assertIsNone(load_boundary(self.db, self.course))

    def test_new_course_opening_already_obeys_confirmed_boundary(self):
        from webapp.security import decrypt_text
        self.send("以后都不想说自己的事", "confirm_all")
        course = create_or_resume_course(self.db, participant_id=self.person.id, lesson_id="lesson-2")[0]
        state = decrypt_json(course.agent_state_encrypted)
        self.assertTrue(boundaries.fictional(state))
        greeting = self.db.scalar(select(Message).where(Message.conversation_id == course.id))
        self.assertIn("虚构案例", decrypt_text(greeting.content_encrypted))
        self.assertNotIn("最近一周", decrypt_text(greeting.content_encrypted))

    def test_fictional_record_finishes_and_is_not_imported_as_personal_context(self):
        self.send("以后都不想说自己的事", "confirm_all")
        self.send("事情：活动取消；想法：白跑一趟了；心情：失望；做法：回家")
        state = decrypt_json(self.course.agent_state_encrypted)
        self.assertEqual(state["stage"], "review")
        self.assertTrue(all(item["source_kind"] == "fictional" for item in state["draft_record"].values()))
        self.send(action="confirm_record")
        for _ in range(4):
            self.send(action="skip_check_question")
        goal = self.send(action="continue_after_check")
        self.assertNotIn("哪件生活小事", goal["reply"])
        for action in ("skip_learning_goal", "decline_practice", "finish"):
            self.send(action=action)
        state = decrypt_json(self.course.agent_state_encrypted)
        self.assertIsNone(state["learning_result"]["personal_record"])
        self.assertEqual(state["learning_result"]["guided_practice_result"]["source_kind"], "fictional")
        self.assertEqual(offer_previous_summary(self.db, self.person.id, AGENT_VERSION, "lesson-2")["status"], "unavailable")
