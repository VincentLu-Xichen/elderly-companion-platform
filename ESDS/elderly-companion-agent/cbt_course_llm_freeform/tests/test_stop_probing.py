import copy
import json
import unittest
from cbt_course_llm_freeform import boundaries
from cbt_course_llm_freeform.agent import FreeformCourseAgent
from cbt_course_llm_freeform.runtime import FreeformCourseRuntime, new_course_state, course_payload
from cbt_course_llm_freeform.tests.test_interaction_reflection import InteractionClient
from cbt_course_llm_freeform.tests.test_practice_flow import DecisionAgent, turn
from daily_agent.azure_chat_client import ChatCompletionResult


class StopClient(InteractionClient):
    def __init__(self, fail=False, verdict="feedback"):
        super().__init__(fail=fail, verdict=verdict, follow_up="stop")

    def complete_with_metadata(self, messages, **kwargs):
        if not messages[0]["content"].startswith("你是课程互动反馈"):
            from cbt_course_llm_freeform.preview import PreviewClient
            return PreviewClient().complete_with_metadata(messages, **kwargs)
        result = super().complete_with_metadata(messages, **kwargs)
        data = json.loads(result.text)
        data.update(response_type="review_current_case" if self.verdict == "feedback" else "neutral", tone="polite",
            personal_intent="none", reply="抱歉，刚才追问太多了。我们先不再补问，仍围绕您前面说的这件事回顾，没说到的先留空。")
        return ChatCompletionResult(text=json.dumps(data, ensure_ascii=False), model="stop-test", finish_reason="stop")


def practice():
    state = new_course_state("lesson-1", reflection_policy="none")
    state["stage"] = "practice"
    for key, value in (("situation", "上学路上听到一声响"), ("thought", "会不会撞到人"), ("emotion", "害怕")):
        state["draft_record"][key] = {"value": value, "source_message_id": "prior", "source_kind": "personal"}
    return state


def feedback(state, client, text="你为什么一直追问我，我三个要素都说了"):
    return FreeformCourseRuntime(agent=FreeformCourseAgent(client=client)).process(state,
        [{"id": "u", "role": "learner", "content": text}])


class StopProbingTests(unittest.TestCase):
    def test_stop_preserves_same_case_and_known_facts_without_private_boundary(self):
        state = practice()
        result = feedback(state, StopClient())
        self.assertEqual(result.state["case_id"], state["case_id"])
        self.assertEqual(result.state["draft_record"], state["draft_record"])
        self.assertEqual(result.state["stage"], "review")
        self.assertNotIn("disclosure_boundary", result.state)
        self.assertFalse(boundaries.fictional(result.state))
        self.assertEqual(result.state["practice_flow"]["deferred"]["behavior"]["status"], "not_observed")
        self.assertIsNone(result.state["confirmed_record"])
        self.assertIn("上学路上", result.reply)
        self.assertNotIn("？", result.reply)
        self.assertEqual(result.trace["model_calls"][0]["phase"], "interaction_reflection")
        self.assertEqual(result.state["interaction_memories"][0]["tone"], "polite")

    def test_failed_style_judge_never_becomes_personal_rejection_or_new_story(self):
        state = practice()
        result = feedback(state, StopClient(fail=True))
        self.assertEqual(result.state["case_id"], state["case_id"])
        self.assertEqual(result.state["draft_record"], state["draft_record"])
        self.assertFalse(result.state["privacy"].get("recovery", False))
        self.assertFalse(boundaries.blocked(result.state))
        self.assertEqual(result.state["interaction_memories"], [])
        self.assertEqual(result.trace["interaction_event"]["status"], "failed")
        self.assertIn("抱歉", result.reply)
        self.assertNotIn("收到您的表达", result.reply)

    def test_after_stop_model_question_is_replaced_with_current_record_review(self):
        result = feedback(practice(), StopClient())
        following = turn(result.state, "嗯", agent=DecisionAgent())
        self.assertEqual(following.state["stage"], "review")
        self.assertNotIn("？", following.reply)
        self.assertIn("上学路上", following.reply)

    def test_negation_or_reported_complaint_does_not_close_exercise(self):
        state = practice()
        result = feedback(state, StopClient(verdict="not_feedback"), "不是嫌你一直追问，我只是转述朋友的话")
        # Test the style verdict directly: normal teaching is outside this scripted client.
        self.assertNotEqual(result.trace.get("action"), "interaction_feedback")
        self.assertEqual(result.state["interaction_memories"], [])

    def test_new_ui_hides_field_buttons_and_legacy_contract_remains_available(self):
        state = practice()
        self.assertFalse(course_payload(state)["show_practice_controls"])
        state.pop("interaction_response_version")
        self.assertTrue(course_payload(state)["show_practice_controls"])

    def test_personal_story_cannot_become_fictional_case_answer(self):
        from cbt_course_llm_freeform.schemas import AgentResult, TeachingDecision, Evidence
        class OtherStoryAgent:
            def reply(self, history, *, context):
                return AgentResult(reply="请再说您的做法？", decision=TeachingDecision(reply="请再说您的做法？", practice_origin="personal_account",
                    observations=[Evidence(field="situation", value="我是去上学的路上", source_message_id="u")]))
        state = practice()
        boundaries.switch(state, "fictional")
        result = FreeformCourseRuntime(agent=OtherStoryAgent()).process(state, [{"id": "u", "role": "learner", "content": "我是去上学的路上"}])
        self.assertEqual(result.state["draft_record"], {})
        self.assertEqual(result.state["case_id"], state["case_id"])
        self.assertEqual(result.trace["action"], "case_source_mismatch")
        self.assertNotIn("？", result.reply)
