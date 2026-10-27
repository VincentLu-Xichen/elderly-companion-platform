"""028 bounded paired capture. Offline by default; no product database access."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime
import json
import os
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.run_dialogue_eval import (
    Recorder, RequestBudgetExceeded, configure_eval_environment, digest,
    fixture as original_fixture, freeze_code, save, totals,
)

SUITE = ROOT / "evals/cbt/cases.a1-style.v1.json"


class SharedBudget:
    """Reserve each real attempt durably before dispatch, across both arms."""
    def __init__(self, path):
        self.path = Path(path)

    def claim(self, arm, run_id):
        lock = self.path.with_suffix(".lock")
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            used = sum(item["arm"] == arm for item in data["attempts"])
            if len(data["attempts"]) >= data["limit"] or used >= data["arm_limit"]:
                raise RequestBudgetExceeded("Shared A1 budget exhausted")
            item = {"arm": arm, "run_id": run_id, "attempt": len(data["attempts"]) + 1,
                    "reserved_at": datetime.now().astimezone().isoformat()}
            data["attempts"].append(item)
            save(self.path, data)
            return item["attempt"]
        finally:
            os.close(descriptor)
            lock.unlink()


class DurableRecorder(Recorder):
    def __init__(self, client, budget, arm, run_id, target):
        super().__init__(client, 6)
        self.budget, self.arm, self.run_id, self.target = budget, arm, run_id, target

    def complete_with_metadata(self, messages, **kwargs):
        if len(self.requests) >= self.max_calls:
            raise RequestBudgetExceeded("Local A1 budget exhausted")
        attempt = self.budget.claim(self.arm, self.run_id)
        try:
            return super().complete_with_metadata(messages, **kwargs)
        finally:
            if self.requests:
                self.requests[-1]["shared_attempt"] = attempt
            save(self.target / "requests.json", self.requests)


def fixture(case):
    if case["fixture"] == "first-learn":
        return original_fixture(case)
    from cbt_course_llm_freeform import practice_flow
    state, history = original_fixture({**case, "fixture": "first-review"})
    state["stage"] = "practice"
    state["blueprint"]["ratings"].pop("emotion_intensity")
    if case["fixture"] == "first-belief-rating":
        state["blueprint"]["ratings"].pop("thought_belief")
        history[0]["content"] = "昨天数学考试最后一道题没做出来；别人肯定都会，只有我不会；担心；考完一直翻答案"
        question = "对于‘别人肯定都会，只有我不会’这条想法，您当时有多相信？0分是不相信，10分是非常相信，也可以暂不评分。"
        expected = "thought_belief"
    elif case["fixture"] == "first-emotion-rating":
        history[0]["content"] = "昨天数学考试最后一道题没做出来；别人肯定都会，只有我不会；担心；考完一直翻答案；相信程度7分"
        question = "刚才这份担心当时有多强烈？0分是不强烈，10分是非常强烈，也可以暂不评分。"
        expected = "emotion_intensity"
    else:
        raise ValueError("Unknown A1 fixture")
    history[-1]["content"] = question
    assert practice_flow.current_field(state) == expected
    assert all(item["value"] in history[0]["content"] for item in state["draft_record"].values())
    return state, history


def program_checks(case, initial, state):
    record = state["draft_record"]
    ratings = state["blueprint"]["ratings"]
    common = {"not_confirmed": state.get("confirmed_record") is None,
              "not_completed": not state["completed"]}
    if case["id"] == "E01-a":
        common.update(four_fields=all(key in record for key in ("situation", "thought", "emotion", "behavior")),
                      zero_rating=ratings.get("thought_belief", {}).get("value") == 0)
    elif case["id"] == "E01-R03":
        common.update(same_record=record == initial["draft_record"])
    else:
        common.update(same_record=record == initial["draft_record"],
                      intensity_not_invented="emotion_intensity" not in ratings,
                      field_deferred="emotion_intensity" in state["practice_flow"]["deferred"])
    return common


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--arm", choices=("before", "after"))
    parser.add_argument("--experiment", type=Path)
    parser.add_argument("--continue-case", choices=("E01-R03",))
    parser.add_argument("--gate-approved", action="store_true")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    args = parser.parse_args()
    suite = json.loads(SUITE.read_text(encoding="utf-8"))
    for case in suite["cases"]:
        fixture(case)
    if not args.live:
        print(json.dumps({"validated": [c["id"] for c in suite["cases"]], "api_calls": 0}))
        return 0
    if not args.arm or not args.experiment:
        parser.error("live requires --arm and --experiment")
    if args.continue_case and not args.gate_approved:
        parser.error("continuation requires an explicit offline review gate")
    experiment = args.experiment.resolve()
    allowed = (ROOT / "test-results/dialogue-evals").resolve()
    if not experiment.is_relative_to(allowed):
        parser.error("experiment must be in ignored synthetic dialogue-evals")
    experiment.mkdir(parents=True, exist_ok=True)
    ledger = experiment / "budget.json"
    if not ledger.exists():
        if args.arm != "before" or args.continue_case:
            parser.error("initial before arm must establish the shared experiment")
        save(ledger, {"limit": 12, "arm_limit": 6, "attempts": []})
        save(experiment / "suite.json", suite)
    if json.loads((experiment / "suite.json").read_text(encoding="utf-8")) != suite:
        parser.error("suite changed during the paired experiment")
    pointer = experiment / (args.arm + "-initial.json")
    continuation_pointer = experiment / (args.arm + "-continuation.json")
    if (not args.continue_case and pointer.exists()) or (args.continue_case and continuation_pointer.exists()):
        parser.error("arm already attempted; no automatic reruns")

    from cbt_course_llm_freeform.agent import FreeformCourseAgent
    from cbt_course_llm_freeform.design import MODEL_TOKEN_LIMITS
    from cbt_course_llm_freeform.prompt import prompt_for_lesson
    from cbt_course_llm_freeform.runtime import FreeformCourseRuntime
    from cbt_course_llm_freeform.presentation import course_payload

    api_configuration = configure_eval_environment(args.env_file)
    client = FreeformCourseAgent._client_from_env()
    configured_model = os.getenv("CBT_COURSE_MODEL") or "provider default"
    public_config = {"provider": api_configuration["provider"], "model": configured_model,
                     "temperature": 1.0, "thinking": "disabled", "max_completion_tokens": MODEL_TOKEN_LIMITS["lesson-1"]}
    config_path = experiment / "public-config.json"
    if config_path.exists():
        if json.loads(config_path.read_text(encoding="utf-8")) != public_config:
            parser.error("model/parameters changed between arms")
    else:
        save(config_path, public_config)
    env_bytes = args.env_file.read_bytes()
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-A1-" + args.arm + ("-continue" if args.continue_case else "") + "-" + uuid.uuid4().hex[:6]
    target = allowed / run_id
    target.mkdir(exist_ok=False)
    save(continuation_pointer if args.continue_case else pointer, {"run_id": run_id, "target": str(target)})
    prompt = prompt_for_lesson("lesson-1")
    save(target / "manifest.json", {"run_id": run_id, "started_at": datetime.now().astimezone().isoformat(),
         "arm": args.arm, "api_configuration": api_configuration, "parameters": public_config,
         "prompt_hash": digest(prompt.encode()), "suite_version": suite["suite_version"],
         "fixture_version": suite["fixture_version"], "policy": "none", "interaction_reflection": "enabled",
         "post_course_reflection": "retained, not exercised", "transport": "non-streaming",
         "continuation_gate": bool(args.gate_approved), "code": freeze_code(target)})
    (target / "prompt.txt").write_text(prompt, encoding="utf-8")
    save(target / "cases.json", suite)
    recorder = DurableRecorder(client, SharedBudget(ledger), args.arm, run_id, target)
    cases = [c for c in suite["cases"] if not args.continue_case or c["id"] == args.continue_case]
    previous_rows = None
    if args.continue_case:
        source = json.loads(pointer.read_text(encoding="utf-8"))
        previous_rows = json.loads((Path(source["target"]) / "results.json").read_text(encoding="utf-8"))
    rows = []
    for case in cases:
        initial, history = fixture(case)
        state = copy.deepcopy(initial)
        if previous_rows is not None:
            previous = next(row for row in previous_rows if row["id"] == case["id"])
            if previous["turn"]["status"] != "success":
                raise ValueError("Cannot continue a failed turn")
            state, history = previous["state"], previous["history"]
            from cbt_course_llm_freeform import practice_flow
            if practice_flow.current_field(state) != "thought_belief":
                raise ValueError("Continuation no longer matches the current question")
        text = case["continuation"] if args.continue_case else case["turns"][0]
        index = 1 if args.continue_case else 0
        latest = {"id": f"{case['id']}-user-{index}", "role": "learner", "content": text}
        before = copy.deepcopy(state)
        history.append(latest)
        runtime = FreeformCourseRuntime(agent=FreeformCourseAgent(client=recorder, system_prompt=prompt, max_completion_tokens=MODEL_TOKEN_LIMITS["lesson-1"]))
        turn = {"input": latest, "before_state": before, "request_offset": len(recorder.requests)}
        started = time.perf_counter()
        try:
            result = runtime.process(state, history)
            state = result.state
            history.append({"id": f"{case['id']}-agent-{index}", "role": "agent", "content": result.reply})
            turn.update(status="success", reply=result.reply, trace=result.trace,
                        attachment=result.attachment, payload=course_payload(state))
        except Exception as exc:
            turn.update(status="error", error_type=type(exc).__name__, unchanged_input_state=state == before)
        turn.update(elapsed_ms=round((time.perf_counter() - started) * 1000), model_calls=copy.deepcopy(runtime.model_calls))
        row = {"id": case["id"], "initial_state": initial, "initial_history": fixture(case)[1],
               "turn": turn, "state": state, "history": history,
               "program_checks": program_checks(case, initial, state), "human_review": "pending"}
        if case["id"] == "E01-R03" and not args.continue_case:
            row["program_checks"]["no_unprovided_score"] = "thought_belief" not in state["blueprint"]["ratings"]
        elif args.continue_case:
            row["program_checks"]["belief_seven"] = state["blueprint"]["ratings"].get("thought_belief", {}).get("value") == 7
        rows.append(row)
        save(target / "results.json", rows)
        save(target / "requests.json", recorder.requests)
        print(json.dumps({"case": case["id"], "status": turn["status"], "checks": row["program_checks"]}, ensure_ascii=False), flush=True)
    summary = {"run_id": run_id, **totals(recorder.requests),
               "elapsed_ms": sum(row["turn"]["elapsed_ms"] for row in rows),
               "env_file_unchanged": args.env_file.read_bytes() == env_bytes,
               "program_checks_passed": sum(row["turn"]["status"] == "success" and all(row["program_checks"].values()) for row in rows)}
    save(target / "summary.json", summary)
    print(json.dumps({**summary, "shared_attempts": len(json.loads(ledger.read_text(encoding="utf-8"))["attempts"])}, ensure_ascii=False))
    return 0 if summary["program_checks_passed"] == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
