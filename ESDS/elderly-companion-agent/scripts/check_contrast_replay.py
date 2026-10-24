"""Replay a recorded synthetic E07 response through old and current presentation code.

No network or product database. Requires the local ignored 023 baseline directory.
"""

import ast
import copy
from datetime import datetime
import json
import sys
from unittest.mock import patch
import uuid
import zipfile

import run_dialogue_eval as evaluation

sys.path.insert(0, str(evaluation.ROOT))
from cbt_course_llm_freeform import lesson2_flow
from cbt_course_llm_freeform.agent import FreeformCourseAgent
from cbt_course_llm_freeform.runtime import FreeformCourseRuntime
from daily_agent.azure_chat_client import ChatCompletionResult


def main():
    baseline = evaluation.ROOT / "test-results/dialogue-evals/20261023-221700-baseline-022-27128e"
    manifest = json.loads((baseline / "manifest.json").read_text(encoding="utf-8"))
    assert (
        evaluation.digest((baseline / "source.zip").read_bytes())
        == manifest["code"]["archive_sha256"]
    )
    row = next(
        r
        for r in json.loads((baseline / "results.json").read_text(encoding="utf-8"))
        if r["id"] == "E07-a"
    )
    recorded_turn = row["turns"][0]
    request = json.loads((baseline / "requests.json").read_text(encoding="utf-8"))[
        recorded_turn["request_offset"]
    ]
    source_name = "ESDS/elderly-companion-agent/cbt_course_llm_freeform/lesson2_flow.py"
    with zipfile.ZipFile(baseline / "source.zip") as archive:
        source = archive.read(source_name)
    assert evaluation.digest(source) == manifest["code"]["files"][source_name]
    tree = ast.parse(source.decode("utf-8-sig"))
    function = next(
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "_reply_after_observations"
    )
    namespace = dict(vars(lesson2_flow))
    exec(
        compile(ast.Module(body=[function], type_ignores=[]), "023-frozen-function", "exec"),
        namespace,
    )

    class RecordedClient:
        def __init__(self):
            self.calls = []

        def complete_with_metadata(self, messages, **kwargs):
            assert messages == request["messages"], "Replay request context changed"
            assert kwargs == request["parameters"], "Replay parameters changed"
            self.calls.append({"messages": copy.deepcopy(messages), "parameters": kwargs})
            return ChatCompletionResult(**request["response"])

    outputs = {}
    for name, handler in (
        ("baseline", namespace[function.name]),
        ("candidate", lesson2_flow._reply_after_observations),
    ):
        client = RecordedClient()
        runtime = FreeformCourseRuntime(agent=FreeformCourseAgent(client=client))
        # Keep the exact recorded state/version for causal replay only. Live runs use new fixtures/version.
        with patch.object(lesson2_flow, function.name, handler):
            result = runtime.process(
                copy.deepcopy(row["initial_state"]),
                copy.deepcopy(row["initial_history"]) + [recorded_turn["input"]],
            )
        assert len(client.calls) == 1
        outputs[name] = {
            "reply": result.reply,
            "state": result.state,
            "trace": result.trace,
            "requests": client.calls,
        }
    assert outputs["baseline"]["reply"] == recorded_turn["reply"]
    assert outputs["baseline"]["state"] == recorded_turn["state"]
    assert outputs["candidate"]["state"] == outputs["baseline"]["state"]
    raw_reply = json.loads(request["response"]["text"])["reply"]
    assert outputs["candidate"]["reply"] == raw_reply + "\n" + outputs["baseline"]["reply"]
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-E07-replay-" + uuid.uuid4().hex[:6]
    target = evaluation.ROOT / "test-results/dialogue-evals" / run_id
    target.mkdir()
    evaluation.save(
        target / "manifest.json",
        {
            "run_id": run_id,
            "kind": "recorded-response-replay",
            "api_calls": 0,
            "baseline_run_id": manifest["run_id"],
            "code": evaluation.freeze_code(target),
            "state_version_note": "Exact old state used only for causal replay; no application DB or version migration.",
        },
    )
    evaluation.save(
        target / "comparison.json",
        {
            "input": recorded_turn["input"],
            "recorded_response": request["response"],
            "outputs": outputs,
            "checks": {
                "same_requests": True,
                "same_states": True,
                "old_reply_reproduced": True,
                "acknowledgement_preserved": True,
            },
            "api_calls": 0,
            "usage_note": "Response usage belongs to 023, not new consumption.",
        },
    )
    print(
        json.dumps(
            {
                "run_id": run_id,
                "api_calls": 0,
                "same_requests": True,
                "same_states": True,
                "old_reply_reproduced": True,
                "acknowledgement_preserved": True,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
