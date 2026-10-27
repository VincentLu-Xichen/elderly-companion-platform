import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.run_dialogue_eval import digest
from scripts.run_a1_distress_eval import frozen_pair_prompts, main


class ResponsiveEvalGuards(unittest.TestCase):
    def test_frozen_prompt_rejects_tampering_and_stale_candidate(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "before.txt").write_text("reference", encoding="utf-8")
            (root / "after.txt").write_text("candidate", encoding="utf-8")
            (root / "provenance.json").write_text(json.dumps({
                "before": {"prompt_sha256": digest(b"reference")},
                "after": {"prompt_sha256": digest(b"candidate")},
            }), encoding="utf-8")
            with patch("cbt_course_llm_freeform.prompt.prompt_for_lesson", return_value="candidate"):
                self.assertEqual(frozen_pair_prompts(root)[0]["before"], "reference")
                (root / "before.txt").write_text("changed reference", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "fingerprint"):
                    frozen_pair_prompts(root)
            (root / "before.txt").write_text("reference", encoding="utf-8")
            with patch("cbt_course_llm_freeform.prompt.prompt_for_lesson", return_value="newer candidate"):
                with self.assertRaisesRegex(ValueError, "differs"):
                    frozen_pair_prompts(root)

    def test_multicase_live_cannot_silently_run_default_case_or_read_credentials(self):
        suite = Path(__file__).resolve().parents[1] / "evals/cbt/cases.a1-responsive.v1.json"
        with patch("sys.argv", ["eval", "--suite-file", str(suite), "--live",
                                "--arm", "before", "--turn", "1"]), \
             patch("scripts.run_a1_distress_eval.configure_eval_environment") as configure, \
             contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as stopped:
                main()
            self.assertEqual(stopped.exception.code, 2)
            configure.assert_not_called()


if __name__ == "__main__":
    unittest.main()
