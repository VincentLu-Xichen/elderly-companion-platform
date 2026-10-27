import json
from pathlib import Path
import tempfile
import unittest

from daily_agent.azure_chat_client import ChatCompletionResult
from scripts.run_a1_style_eval import DurableRecorder, SharedBudget, SUITE, fixture
from scripts.run_dialogue_eval import RequestBudgetExceeded


class A1StyleEvalTests(unittest.TestCase):
    def test_failed_attempt_and_new_recorder_share_global_and_arm_limits(self):
        class Client:
            def __init__(self, fail=False):
                self.calls, self.fail = 0, fail

            def complete_with_metadata(self, messages, **kwargs):
                self.calls += 1
                if self.fail:
                    raise RuntimeError("synthetic transport failure")
                return ChatCompletionResult(text="{}", usage={"total_tokens": 3})

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "budget.json"
            path.write_text(json.dumps({"limit": 2, "arm_limit": 1, "attempts": []}))
            failed, successful = Client(True), Client()
            first = DurableRecorder(failed, SharedBudget(path), "before", "run-one", root)
            with self.assertRaises(RuntimeError):
                first.complete_with_metadata([])
            self.assertEqual(json.loads((root / "requests.json").read_text())[0]["status"], "error")
            restarted = DurableRecorder(successful, SharedBudget(path), "before", "run-two", root)
            with self.assertRaises(RequestBudgetExceeded):
                restarted.complete_with_metadata([])
            after = DurableRecorder(successful, SharedBudget(path), "after", "run-three", root)
            after.complete_with_metadata([])
            with self.assertRaises(RequestBudgetExceeded):
                after.complete_with_metadata([])
            self.assertEqual((failed.calls, successful.calls), (1, 1))
            self.assertEqual(len(json.loads(path.read_text())["attempts"]), 2)

    def test_busy_ledger_is_not_overwritten_or_unlocked_by_another_claim(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "budget.json"
            path.write_text(json.dumps({"limit": 12, "arm_limit": 6, "attempts": []}))
            lock = path.with_suffix(".lock")
            lock.write_text("another process")
            with self.assertRaises(FileExistsError):
                SharedBudget(path).claim("before", "run")
            self.assertTrue(lock.exists())
            self.assertFalse(json.loads(path.read_text())["attempts"])

    def test_scoring_fixtures_have_truthful_history_without_unprovided_numbers(self):
        from cbt_course_llm_freeform import practice_flow

        cases = json.loads(SUITE.read_text(encoding="utf-8"))["cases"]
        for case in cases[1:]:
            state, history = fixture(case)
            source = history[0]["content"]
            self.assertTrue(all(row["value"] in source for row in state["draft_record"].values()))
            self.assertNotIn("6分", source)
            self.assertNotIn("emotion_intensity", state["blueprint"]["ratings"])
            if case["id"] == "E01-R03":
                self.assertNotIn("7分", source)
                self.assertFalse(state["blueprint"]["ratings"])
                self.assertEqual(practice_flow.current_field(state), "thought_belief")
            else:
                self.assertEqual(state["blueprint"]["ratings"]["thought_belief"]["value"], 7)
                self.assertEqual(practice_flow.current_field(state), "emotion_intensity")


if __name__ == "__main__":
    unittest.main()
