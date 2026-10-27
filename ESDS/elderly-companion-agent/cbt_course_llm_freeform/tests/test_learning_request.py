import copy
import json
import unittest
import uuid
from cbt_course_llm_freeform.agent import FreeformCourseAgent
from cbt_course_llm_freeform.learning_request import TeachingRequest
from cbt_course_llm_freeform.runtime import FreeformCourseRuntime
from cbt_course_llm_freeform.schemas import AgentResult, TeachingDecision
from daily_agent.azure_chat_client import ChatCompletionResult
from scripts.run_a1_style_eval import fixture


def request(latest, mode="listen", fields=(), **overrides):
    data = dict(mode=mode, deferred_rating_fields=list(fields), source_message_id=latest["id"], quote=latest["content"])
    data.update(overrides)
    return TeachingRequest(**data)


class RequestClient:
    def __init__(self):
        self.calls = []
    def complete_with_metadata(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        item = json.loads(messages[-1]["content"])
        latest = dict(id=item["id"], content=item["text"])
        directive = request(latest).model_dump()
        if messages[0]["content"].startswith("你是课程互动反馈"):
            data = dict(verdict="not_feedback", source_message_id=latest["id"], quote=latest["content"],
                        observation="本人希望先说说", hypothesis="可能暂时需要倾听", alternative_explanation="也可能短暂疲累",
                        scope="lesson", reply_length="short", follow_up="reduce", reply="可以，先听您说。",
                        personal_intent="none", task_action="continue", learning_request=directive)
        else:
            data = dict(reply="可以，先听您说。", learning_request=directive)
        return ChatCompletionResult(text=json.dumps(data, ensure_ascii=False), model="offline", finish_reason="stop")


class LearningRequestTests(unittest.TestCase):
    def setUp(self):
        self.state, self.history = fixture(dict(id="L-local", lesson="lesson-1", fixture="first-belief-rating"))
    def run_request(self, mode="listen", fields=(), text="先听我说。", reply="可以，先听您说。", **overrides):
        latest = dict(id=uuid.uuid4().hex, role="learner", content=text)
        decision = TeachingDecision(reply=reply, learning_request=request(latest, mode, fields, **overrides))
        class Stub:
            def reply(self, history, *, context):
                return AgentResult(reply=decision.reply, decision=decision)
        return FreeformCourseRuntime(agent=Stub()).process(self.state, self.history + [latest])
    def test_two_listening_turns_do_not_consume_answers_or_advance(self):
        before = copy.deepcopy(self.state)
        for _ in range(2):
            self.state = self.run_request().state
        for key in ("stage", "case_id", "draft_record", "practice_flow", "blueprint", "privacy"):
            self.assertEqual(self.state[key], before[key])
        self.assertFalse(self.state["paused"])
        self.assertEqual(self.state["interaction_memories"], [])
    def test_listening_and_rating_refusal_are_independent(self):
        for fields in (["thought_belief"], ["thought_belief", "emotion_intensity"]):
            with self.subTest(fields=fields):
                result = self.run_request(fields=fields, text="先听我说，今天先不评分。")
                self.assertEqual(set(result.state["practice_flow"]["deferred"]), set(fields))
                self.assertEqual(result.state["practice_flow"]["unanswered"], {})
                self.assertEqual(result.state["draft_record"], self.state["draft_record"])
                self.assertEqual(result.state["stage"], "practice")
                self.assertFalse(result.state["paused"])
    def test_concept_explanation_with_no_scoring_keeps_source_record(self):
        result = self.run_request("continue", ["thought_belief"], text="我想分清两部分，今天先不评分。", reply="事情是发生的内容，想法是对它的解释，这次先不评分。")
        self.assertEqual(result.state["draft_record"], self.state["draft_record"])
        self.assertEqual(result.trace["action"], "continue")
        self.assertIsNone(result.state["confirmed_record"])
    def test_refusal_does_not_erase_existing_zero(self):
        self.state["blueprint"]["ratings"]["thought_belief"] = dict(value=0, source_message_id="prior")
        result = self.run_request(fields=["thought_belief"], text="相信程度这项先不评分。")
        self.assertEqual(result.state["blueprint"]["ratings"], self.state["blueprint"]["ratings"])
        self.assertNotIn("thought_belief", result.state["practice_flow"]["deferred"])
    def test_pure_distress_cannot_authorize_model_proposed_score_deferral(self):
        result = self.run_request(fields=["thought_belief", "emotion_intensity"], text="我很难受，觉得自己没用，今天也不想见人。")
        self.assertEqual(result.state["practice_flow"], self.state["practice_flow"])
        memory = result.state["latest_interaction_event"]["memory"]
        self.assertEqual(memory["deferred_rating_fields"], [])
        self.assertEqual(memory["rejected_rating_fields"], ["thought_belief", "emotion_intensity"])
        self.assertFalse(result.state["paused"])
    def test_explicit_pause_preserves_record_and_has_real_receipt(self):
        result = self.run_request("pause_lesson", text="这节课先停在这里。")
        self.assertTrue(result.state["paused"])
        self.assertEqual(result.reply, "可以，先听您说。")
        self.assertEqual(result.state["draft_record"], self.state["draft_record"])
        self.assertEqual(result.state["practice_flow"], self.state["practice_flow"])
    def test_invalid_scope_and_sources_are_rejected_without_mutation(self):
        before = copy.deepcopy(self.state)
        attempts = [dict(source_message_id="other-user"), dict(quote="not present"),
                    dict(mode="continue"),
                    dict(fields=["thought_belief", "thought_belief"]), dict(reply="课程已完成")]
        for overrides in attempts:
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                self.run_request(**overrides)
            self.assertEqual(self.state, before)
        from cbt_course_llm_freeform.learning_request import apply
        latest = dict(id="u", content="不是暂停课程")
        with self.assertRaisesRegex(ValueError, "negation"):
            apply(self.state, request(latest, "pause_lesson", quote="暂停课程").model_dump(), latest, "先休息。")
        self.assertEqual(self.state, before)
    def test_requests_cannot_submit_new_or_historical_answers(self):
        before = copy.deepcopy(self.state)
        latest = dict(id="u", role="learner", content="先听我说，我很难受")
        for evidence in (dict(field="emotion", value="很难受", source_message_id="u"),
                         dict(field="thought", value="别人肯定都会，只有我不会", source_message_id="seed-user")):
            decision = TeachingDecision(reply="先听您说。", learning_request=request(latest), observations=[evidence])
            class Stub:
                def reply(self, history, *, context):
                    return AgentResult(reply=decision.reply, decision=decision)
            with self.assertRaises(ValueError):
                FreeformCourseRuntime(agent=Stub()).process(self.state, self.history+[latest])
            self.assertEqual(self.state, before)
    def test_auxiliary_route_uses_same_request_with_one_call(self):
        client = RequestClient()
        latest = dict(id="u", role="learner", content="我不是要暂停课程，只是想让你先听我说。")
        result = FreeformCourseRuntime(agent=FreeformCourseAgent(client=client)).process(self.state, self.history+[latest])
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(result.trace["action"], "listen")
        self.assertFalse(result.state["paused"])
        self.assertEqual(result.state["practice_flow"], self.state["practice_flow"])
    def test_legacy_inconsistent_action_is_not_coerced(self):
        from cbt_course_llm_freeform.interaction import InteractionReflection
        latest = dict(id="u", role="learner", content="先听我说")
        note = InteractionReflection(verdict="not_feedback", source_message_id="u", quote=latest["content"],
            observation="当前诉求", hypothesis="可能需要倾听", alternative_explanation="可能疲累",
            scope="lesson", reply_length="short", follow_up="stop", reply="先听您说。", personal_intent="pause", task_action="pause")
        with self.assertRaises(ValueError):
            FreeformCourseRuntime()._accept_interaction(self.state, note.model_dump(), latest, "practice")
        self.assertFalse(self.state["paused"])
    def test_aligned_auxiliary_pause_is_legal_but_local_pause_conflict_is_not(self):
        from cbt_course_llm_freeform.learning_request import LearningInteraction
        latest = dict(id="u", role="learner", content="今天这节课先停在这里吧，我现在不想继续课程了。")
        base = dict(verdict="not_feedback", source_message_id="u", quote=latest["content"],
                    observation="本人要求停课", hypothesis="可能希望休息", alternative_explanation="也可能需要处理别的事",
                    scope="lesson", reply_length="short", follow_up="standard", reply="好，这节课先停在这里。",
                    personal_intent="pause", task_action="pause")
        note = LearningInteraction(**base, learning_request=request(latest, "pause_lesson"))
        result = FreeformCourseRuntime()._accept_interaction(copy.deepcopy(self.state), note.model_dump(), latest, "practice")
        self.assertTrue(result.state["paused"])
        self.assertEqual(result.reply, base["reply"])
        note = LearningInteraction(**base, learning_request=request(latest, "listen"))
        with self.assertRaisesRegex(ValueError, "conflicts"):
            FreeformCourseRuntime()._accept_interaction(self.state, note.model_dump(), latest, "practice")
        self.assertFalse(self.state["paused"])
    def test_pause_extra_rating_proposals_are_audited_without_changing_scores(self):
        before = copy.deepcopy(self.state)
        result = self.run_request("pause_lesson", fields=["thought_belief", "emotion_intensity"], text="今天这节课先停在这里吧。")
        self.assertTrue(result.state["paused"])
        self.assertEqual(result.state["practice_flow"], before["practice_flow"])
        self.assertEqual(result.state["blueprint"], before["blueprint"])
        self.assertEqual(result.state["latest_interaction_event"]["memory"]["action_guard"], "pause_does_not_change_rating_scope")
    def test_observed_request_is_encrypted_idempotent_and_inactive(self):
        from cbt_course_llm_freeform.tests.test_interaction_reflection import InteractionPersistenceTests
        from cbt_course_llm_freeform.services import process_course_turn
        from cbt_course_llm_freeform.interaction_memory import load_memories
        from webapp.models import InteractionReflectionMemory
        from webapp.security import decrypt_json, encrypt_json
        from sqlalchemy import select
        harness = InteractionPersistenceTests(); harness.setUp()
        try:
            conversation = harness.start()
            conversation.agent_state_encrypted = encrypt_json(self.state); harness.db.commit()
            client = RequestClient(); key = uuid.uuid4().hex
            result = process_course_turn(harness.db, conversation, content="先听我说。", idempotency_key=key,
                runtime_factory=lambda: FreeformCourseRuntime(agent=FreeformCourseAgent(client=client)))
            row = harness.db.scalar(select(InteractionReflectionMemory))
            self.assertEqual(row.status, "observed")
            self.assertNotIn("先听", row.payload_encrypted)
            self.assertEqual(decrypt_json(row.payload_encrypted)["mode"], "listen")
            self.assertEqual(load_memories(harness.db, conversation), [])
            replay = process_course_turn(harness.db, conversation, content="先听我说。", idempotency_key=key)
            self.assertEqual(replay["reply"], result["reply"])
            self.assertEqual(len(client.calls), 1)
        finally:
            harness.tearDown()
