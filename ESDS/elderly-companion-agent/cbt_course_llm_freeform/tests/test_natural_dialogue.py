import unittest
from types import SimpleNamespace

from cbt_course_llm_freeform import dialogue, practice_flow
from cbt_course_llm_freeform.runtime import FreeformCourseRuntime, new_course_state
from cbt_course_llm_freeform.schemas import TeachingDecision, AgentResult
from cbt_course_llm_freeform.navigation import NavigationDecision
from cbt_course_llm_freeform.tests.test_blueprint import ready_state, apply


class NaturalTeacher:
    def reply(self, history, *, context):
        latest = history[-1]
        observations = ([dict(field="situation", value=latest["content"], source_message_id=latest["id"])]
                        if context["stage"] == "learn" else [])
        d = TeachingDecision(reply="这件事让您牵挂，我们慢慢整理。", observations=observations)
        return AgentResult(reply=d.reply, decision=d)


class NaturalDialogueTests(unittest.TestCase):
    def test_learn_keeps_model_reply_and_updates_cards_and_state(self):
        state = new_course_state("lesson-1", reflection_policy="none"); state["stage"] = "learn"
        result = apply(state, "朋友没回消息", agent=NaturalTeacher())
        self.assertEqual(result.reply, "这件事让您牵挂，我们慢慢整理。")
        self.assertEqual(result.state["stage"], "practice")
        self.assertEqual(result.state["draft_record"]["situation"]["value"], "朋友没回消息")
        self.assertTrue(result.state["teacher_flow"]["cards"])

    def test_review_does_not_replace_model_acknowledgement(self):
        result = apply(ready_state(), "没有补充", agent=NaturalTeacher())
        self.assertEqual(result.reply, "这件事让您牵挂，我们慢慢整理。")
        self.assertIsNone(result.state["confirmed_record"])

    def test_contextual_short_confirmation_needs_no_model(self):
        class NoModel:
            def reply(self, *args, **kwargs): raise AssertionError("unnecessary model call")
        result = apply(ready_state(), "准确。", agent=NoModel())
        self.assertIsNotNone(result.state["confirmed_record"])
        self.assertEqual(result.state["stage"], "assessment")
        self.assertEqual(result.state["workflow"]["last_model_call_count"], 0)

    def test_no_confirmation_from_negation_no_supplement_or_other_stage(self):
        state = ready_state()
        for text in ["没有补充", "不准确", "不是没问题", "他说准确", "准确吗", "准确，但心情需要修改"]:
            self.assertFalse(dialogue.confirms_record(state, text), text)
        state["stage"] = "practice"
        self.assertFalse(dialogue.confirms_record(state, "准确"))

    def test_confirmation_cannot_fill_missing_record(self):
        state = new_course_state("lesson-1", reflection_policy="none"); state["stage"] = "review"
        with self.assertRaises(ValueError): apply(state, "准确")
        self.assertIsNone(state["confirmed_record"])

    def test_navigation_keeps_model_acknowledgement_and_unconfirmed_draft(self):
        class Navigator:
            def navigate(self, history, *, context):
                return SimpleNamespace(completion=None, decision=NavigationDecision(
                    intent="goal", goal_items=[history[-1]["content"]],
                    reply="您希望少一些自责，我们可以从一项愿意尝试的练习开始。"))
        state = new_course_state("lesson-1", reflection_policy="none");state["stage"] = "learning_goal"
        result = apply(state, "每周记录一次", agent=Navigator())
        self.assertIn("少一些自责", result.reply)
        self.assertEqual(result.reply, "您希望少一些自责，我们可以从一项愿意尝试的练习开始。")
        self.assertIn("learning_goal_draft", result.state)
        self.assertEqual(result.state["learning_goal_draft"]["items"][0]["value"], "每周记录一次")
        self.assertNotIn("learning_goal", result.state)

    def test_unexecuted_model_claims_do_not_override_receipt(self):
        self.assertEqual(dialogue.navigation_reply("目标已确认", "请核对草稿"), "请核对草稿")

    def test_other_lessons_and_legacy_state_do_not_enable_policy(self):
        for n in (2,):self.assertFalse(dialogue.enabled(new_course_state(f"lesson-{n}")))
        state = new_course_state("lesson-1");state.pop("dialogue_policy")
        self.assertFalse(dialogue.enabled(state))
