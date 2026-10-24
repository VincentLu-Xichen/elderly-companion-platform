"""Preserve acknowledgement without changing activity boundaries or action guards."""

import copy
import unittest

from cbt_course_llm_freeform import lesson2_flow as flow
from cbt_course_llm_freeform.runtime import new_course_state
from cbt_course_llm_freeform.tests.test_lesson2_blueprint import Script, turn


class ContrastReplyTests(unittest.TestCase):
    def contrast(self):
        state = new_course_state("lesson-2")
        state["lesson2_flow"]["rain"]["fields"] = {
            key: {"value": value, "source_message_id": "rain-user"}
            for key, value in {"thought": "安排泡汤了", "emotion": "失望"}.items()
        }
        state["lesson2_flow"]["rain"]["tone"] = "negative"
        flow.make_contrast(state)
        return state

    def test_acknowledgement_survives_transition_without_personal_facts(self):
        state = self.contrast()
        before = copy.deepcopy(state)
        reply = "这不是给谁的心态打分，失望也可以先按原样留着。"
        result = turn(state, "我是不是想得太糟糕了？", client=Script(reply=reply))
        self.assertEqual(result.reply, reply + "\n" + flow.question(result.state))
        self.assertEqual(result.state["lesson2_flow"]["step"], "rain_insight")
        for key in ("rain", "contrast"):
            self.assertEqual(result.state["lesson2_flow"][key], before["lesson2_flow"][key])
        self.assertEqual(result.state["draft_record"], {})
        self.assertIsNone(result.state["confirmed_record"])
        self.assertFalse(result.state["completed"])
        self.assertEqual(state, before)
        self.assertEqual(len(result.trace["model_calls"]), 1)
        continued = turn(result.state, action="continue_lesson2")
        self.assertEqual(continued.state["lesson2_flow"]["step"], "personal")
        self.assertIn("三栏分别记录", continued.reply)

    def test_help_and_off_topic_keep_activity_and_acknowledgement(self):
        for intent in ("help", "not_answer"):
            with self.subTest(intent=intent):
                result = turn(self.contrast(), "我还没理解", client=Script(intent=intent))
                self.assertEqual(result.state["lesson2_flow"]["step"], "contrast")
                self.assertTrue(result.reply.startswith("先保留您的说法。"))

    def test_pause_and_continue_keep_real_action_receipts(self):
        for intent in ("pause", "continue"):
            with self.subTest(intent=intent):
                result = turn(
                    self.contrast(),
                    "先停一下" if intent == "pause" else "继续",
                    client=Script(intent=intent, reply="不应替换操作回执"),
                )
                self.assertNotIn("不应替换操作回执", result.reply)
                self.assertEqual(result.state["paused"], intent == "pause")
                self.assertEqual(
                    result.state["lesson2_flow"]["step"],
                    "contrast" if intent == "pause" else "rain_insight",
                )
                self.assertIsNone(result.state["confirmed_record"])

    def test_invalid_observation_does_not_escape_in_reply_or_mutate_input(self):
        state = self.contrast()
        before = copy.deepcopy(state)
        with self.assertRaises(ValueError):
            turn(state, "我还是失望", client=Script(values={"thought": "我还是失望"}))
        self.assertEqual(state, before)


if __name__ == "__main__":
    unittest.main()
