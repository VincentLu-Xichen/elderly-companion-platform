from __future__ import annotations

import copy
import unittest

from cbt_course_llm_freeform import learning_check, practice_flow
from cbt_course_llm_freeform.runtime import course_payload, new_course_state
from cbt_course_llm_freeform.tests.test_practice_flow import DecisionAgent, turn


class FeedbackAdaptationTests(unittest.TestCase):
    def practice(self):
        state = new_course_state("lesson-1", reflection_policy="none")
        state.pop("privacy")  # These tests retain the historical explicit-button compatibility path.
        state.pop("blueprint")
        state["stage"] = "practice"
        state["draft_record"]["situation"] = {"value": "今天下雨了", "source_message_id": "s"}
        return state

    def test_feedback_does_not_become_a_personal_answer_or_consume_clarification(self):
        state = self.practice()
        # Historical rule-only state remains covered separately from the new LLM path.
        state.pop("interaction_reflection_version")
        state["practice_flow"]["unanswered"]["thought"] = ["prior"]
        before = copy.deepcopy(state)
        agent = DecisionAgent()
        result = turn(state, "一直让我解释，感觉像审问", agent=agent, message_id="feedback")
        self.assertEqual(agent.calls, 0)
        self.assertEqual(result.state["draft_record"], before["draft_record"])
        self.assertEqual(result.state["practice_flow"]["unanswered"], before["practice_flow"]["unanswered"])
        self.assertEqual(result.state["stage"], "practice")
        note = result.trace["interaction_feedback"]
        self.assertEqual(note["source_message_id"], "feedback")
        self.assertEqual(note["quote"], "一直让我解释，感觉像审问")
        self.assertEqual(note["effect"], "not_measured")
        self.assertEqual(note["kind"], "rule_based_feedback_note")
        self.assertEqual(course_payload(result.state)["interaction_adaptation"]["status"], "awaiting_choice")

    def test_negative_and_reported_phrases_do_not_trigger_this_narrow_pilot(self):
        for text in ("没有感觉像审问", "他一直让我解释，感觉像审问", "我不觉得你解释太多了", "很烦", "我害怕别人审问我"):
            with self.subTest(text=text):
                self.assertIsNone(practice_flow.feedback_action(text))

    def test_two_choices_are_different_and_neither_fills_or_skips_the_field(self):
        state = turn(self.practice(), action="request_less_probing").state
        explained = turn(state, action="show_brief_explanation", message_id="explain")
        continued = turn(state, action="continue_practice_dialogue", message_id="continue")
        self.assertIn("解释、判断或预测", explained.reply)
        self.assertNotIn("？", explained.reply)
        self.assertIn("脑中", continued.reply)
        self.assertNotIn("暂时想不起或不愿谈", continued.reply)
        for result in (explained, continued):
            self.assertEqual(result.state["draft_record"], state["draft_record"])
            self.assertEqual(result.state["practice_flow"]["unanswered"], {})
            self.assertEqual(result.trace["model_calls"], [])
            self.assertEqual(result.state["stage"], "practice")
            self.assertEqual(practice_flow.adaptation(result.state)["effect"], "not_measured")

    def test_direct_answer_resumes_and_model_receives_structured_local_adaptation(self):
        state = turn(self.practice(), action="request_less_probing").state
        answer = "我想到今天不能散步了"
        observations = [{"field": "thought", "value": answer, "source_message_id": "answer"}]
        agent = DecisionAgent(observations)
        result = turn(state, answer, message_id="answer", agent=agent)
        baseline = turn(self.practice(), answer, message_id="answer", agent=DecisionAgent(observations))
        self.assertEqual(agent.context["interaction_adaptation"]["parameters"], {"reply_length": "short", "follow_up": "offer_choice"})
        note = practice_flow.adaptation(result.state)
        self.assertEqual(note["choice"]["action"], "continued_by_answer")
        self.assertEqual(note["parameters"]["follow_up"], "one_question")
        self.assertLess(len(result.reply), len(baseline.reply))
        self.assertEqual(result.state["draft_record"]["thought"]["value"], answer)

    def test_expiry_review_and_edit_keep_feedback_separate_from_learner_facts(self):
        state = self.practice()
        state["draft_record"].update({key: {"value": key, "source_message_id": key} for key in ("emotion", "behavior")})
        state = turn(state, action="request_less_probing").state
        state = turn(state, action="show_brief_explanation").state
        reviewed = turn(state, action="defer_practice_field").state
        self.assertEqual(reviewed["stage"], "review")
        self.assertIsNone(practice_flow.adaptation(reviewed))
        self.assertEqual(learning_check.report(reviewed)["interaction_feedback"]["effect"], "not_measured")
        checked = turn(reviewed, action="confirm_record").state
        self.assertEqual(checked["stage"], "assessment")
        self.assertIsNone(course_payload(checked)["interaction_adaptation"])
        self.assertNotIn("interaction_feedback", checked["confirmed_record"])
        edited = turn(reviewed, action="edit_record").state
        self.assertIsNone(practice_flow.adaptation(edited))
        self.assertIsNone(practice_flow.adaptation(new_course_state("lesson-2")))

    def test_unsupported_stage_and_choice_without_feedback_are_rejected(self):
        for action in practice_flow.FEEDBACK_CONTROLS:
            for lesson, stage in (("lesson-2", "practice"), ("lesson-1", "learn"), ("lesson-1", "assessment")):
                state = new_course_state(lesson); state["stage"] = stage
                with self.subTest(action=action, lesson=lesson, stage=stage), self.assertRaises(ValueError):
                    turn(state, action=action)
        for action in ("show_brief_explanation", "continue_practice_dialogue"):
            with self.assertRaises(ValueError):
                turn(self.practice(), action=action)
