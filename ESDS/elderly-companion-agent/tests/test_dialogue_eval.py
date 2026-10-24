import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from daily_agent.azure_chat_client import ChatCompletionResult
from scripts.run_dialogue_eval import (
    Recorder,
    RequestBudgetExceeded,
    SUITE,
    checks,
    fixture,
    totals,
    configure_eval_environment,
)


class DialogueEvalTests(unittest.TestCase):
    def test_explicit_file_selects_client_key_and_model_without_secret_audit(self):
        from cbt_course_llm_freeform.agent import FreeformCourseAgent

        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text(
                "CBT_COURSE_PROVIDER=deepseek\nCBT_COURSE_MODEL=new-test-model\n"
                "DEEPSEEK_API_KEY=new-synthetic-key\nAPP_SECRET=must-not-be-loaded\n",
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {
                    "CBT_COURSE_PROVIDER": "azure",
                    "CBT_COURSE_MODEL": "old-model",
                    "DEEPSEEK_API_KEY": "old-synthetic-key",
                    "APP_SECRET": "keep-app-setting",
                },
            ):
                audit = configure_eval_environment(env_file)
                client = FreeformCourseAgent._client_from_env()
                self.assertEqual(client.api_key, "new-synthetic-key")
                self.assertEqual(client.model, "new-test-model")
                self.assertEqual(os.environ["APP_SECRET"], "keep-app-setting")
                self.assertIn("DEEPSEEK_API_KEY", audit["inherited_conflict_setting_names"])
                self.assertNotIn("synthetic-key", json.dumps(audit))

    def test_missing_file_credentials_never_fall_back_to_inherited_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text(
                "CBT_COURSE_PROVIDER=deepseek\nCBT_COURSE_MODEL=test\n", encoding="utf-8"
            )
            with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "inherited-synthetic-key"}):
                before = dict(os.environ)
                with self.assertRaisesRegex(ValueError, "no inherited fallback"):
                    configure_eval_environment(env_file)
                self.assertEqual(dict(os.environ), before)

    def test_provider_conflict_and_interpolation_fail_before_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            for key_value, provider in (("test-key", "azure"), ("${INHERITED_KEY}", None)):
                with self.subTest(provider=provider):
                    env_file.write_text(
                        "CBT_COURSE_PROVIDER=deepseek\nCBT_COURSE_MODEL=test\nDEEPSEEK_API_KEY="
                        + key_value
                        + "\n",
                        encoding="utf-8",
                    )
                    before = dict(os.environ)
                    with self.assertRaises(ValueError):
                        configure_eval_environment(env_file, provider)
                    self.assertEqual(dict(os.environ), before)

    def test_optional_azure_api_settings_do_not_leak_from_inherited_process(self):
        from cbt_course_llm_freeform.agent import FreeformCourseAgent

        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text(
                "CBT_COURSE_PROVIDER=azure\nAZURE_OPENAI_API_KEY=test-key\n"
                "AZURE_OPENAI_ENDPOINT=https://synthetic.invalid\n"
                "AZURE_OPENAI_DEPLOYMENT=new-deployment\n",
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {
                    "AZURE_OPENAI_COURSE_DEPLOYMENT": "stale-course-deployment",
                    "AZURE_OPENAI_API_VERSION": "stale-api-version",
                    "CBT_COURSE_MODEL": "stale-model",
                },
            ):
                configure_eval_environment(env_file)
                client = FreeformCourseAgent._client_from_env()
                self.assertEqual(client.deployment, "new-deployment")
                self.assertNotIn("AZURE_OPENAI_COURSE_DEPLOYMENT", os.environ)
                self.assertNotEqual(client.api_version, "stale-api-version")
                self.assertNotIn("CBT_COURSE_MODEL", os.environ)

    def test_budget_counts_failed_requests_and_retains_unknown_usage(self):
        class Client:
            calls = 0

            def complete_with_metadata(self, messages, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("synthetic failure")
                return ChatCompletionResult(text="{}", usage={"total_tokens": 5})

        client = Client()
        recorder = Recorder(client, 2)
        with self.assertRaises(RuntimeError):
            recorder.complete_with_metadata([])
        recorder.complete_with_metadata([])
        with self.assertRaises(RequestBudgetExceeded):
            recorder.complete_with_metadata([])
        self.assertEqual(client.calls, 2)
        self.assertEqual([r["status"] for r in recorder.requests], ["error", "success"])
        self.assertEqual(totals(recorder.requests)["usage_missing_calls"], 1)
        self.assertEqual(totals(recorder.requests)["known_tokens"]["total_tokens"], 5)
        self.assertIsNone(totals(recorder.requests)["cost"])

    def test_starting_points_are_repeatable_and_evidence_has_real_seed_sources(self):
        for case in json.loads(SUITE.read_text(encoding="utf-8"))["cases"]:
            with self.subTest(case=case["id"]):
                state, history = fixture(case)
                self.assertEqual((state, history), fixture(case))
                sources = {m["id"]: m["content"] for m in history if m["role"] == "learner"}
                for field in state["draft_record"].values():
                    self.assertIn(field["value"], sources[field["source_message_id"]])
                for rating in state.get("blueprint", {}).get("ratings", {}).values():
                    self.assertIn(rating["quote"], sources[rating["source_message_id"]])

    def test_preset_rain_is_not_a_personal_record_or_automatic_confirmation(self):
        cases = json.loads(SUITE.read_text(encoding="utf-8"))["cases"]
        case = next(c for c in cases if c["id"] == "E07-a")
        state, _ = fixture(case)
        self.assertTrue(all(checks(case, state, state, []).values()))
        state["draft_record"]["thought"] = {"value": "安排泡汤了", "source_message_id": "rain-user"}
        self.assertFalse(checks(case, state, state, [])["rain_not_personal"])


if __name__ == "__main__":
    unittest.main()
