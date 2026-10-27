"""One reviewed synthetic turn per invocation, explicit live mode, shared hard budget."""
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
from scripts.run_a1_style_eval import DurableRecorder, SharedBudget, fixture
from scripts.run_dialogue_eval import configure_eval_environment, digest, freeze_code, save, totals

SUITE = ROOT / "evals/cbt/cases.scoped-requests.v1.json"


def program_checks(initial, state, expected):
    scores = state["blueprint"]["ratings"]
    values = {
        "same_case": initial["case_id"] == state["case_id"],
        "same_record": initial["draft_record"] == state["draft_record"],
        "not_confirmed": state.get("confirmed_record") is None,
        "not_completed": not state.get("completed"),
        "no_personal_boundary": state["privacy"] == initial["privacy"],
        "pause_scope": bool(state.get("paused")) == (expected == "pause_lesson"),
    }
    if expected in {"listen", "defer_both"}:
        values["no_answer_attempts"] = state["practice_flow"]["unanswered"] == {}
        values["same_stage"] = state["stage"] == initial["stage"]
    if expected == "listen":
        values["no_automatic_deferrals"] = state["practice_flow"]["deferred"] == {}
    if expected == "defer_both":
        values["only_ratings_deferred"] = set(state["practice_flow"]["deferred"]) == {"thought_belief", "emotion_intensity"}
        values["withheld_not_inferred"] = all(item["status"] == "withheld" for item in state["practice_flow"]["deferred"].values())
    if expected in {"belief_zero", "both_scores"}:
        values["zero_not_missing"] = scores.get("thought_belief", {}).get("value") == 0
    if expected == "both_scores":
        values["intensity_six"] = scores.get("emotion_intensity", {}).get("value") == 6
    elif expected != "belief_zero":
        values["no_invented_scores"] = not scores
    return values


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--case")
    parser.add_argument("--turn", type=int)
    parser.add_argument("--review-note")
    parser.add_argument("--series", choices=("after", "repair2", "repair3", "repair4", "repair5"), default="after")
    parser.add_argument("--snapshot", choices=("candidate-snapshot", "candidate-r2-snapshot", "candidate-r3-snapshot", "candidate-r4-snapshot", "candidate-r5-snapshot"), default="candidate-snapshot")
    parser.add_argument("--prefix-series", choices=("repair4",))
    parser.add_argument("--experiment", type=Path)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    args = parser.parse_args()
    suite = json.loads(SUITE.read_text(encoding="utf-8"))
    for item in suite["cases"]:
        fixture(item)
    if not args.live:
        print(json.dumps({"api_calls": 0, "cases": {item["id"]: len(item["turns"]) for item in suite["cases"]}}, ensure_ascii=False))
        return 0
    cases = {item["id"]: item for item in suite["cases"]}
    if args.case not in cases or not args.turn or not args.experiment:
        parser.error("live requires an explicit case, positive turn and frozen experiment")
    case = cases[args.case]
    if args.turn < 1 or args.turn > len(case["turns"]) or args.turn > 1 and not args.review_note:
        parser.error("invalid turn or missing review of prior output")
    if args.prefix_series and (args.series != "repair5" or args.case != "A1-D01" or args.turn != 4):
        parser.error("explicit frozen-prefix adaptation is only approved for repair5 D01 turn4")
    if args.env_file.resolve() != (ROOT / ".env").resolve():
        parser.error("this authorized observation uses only the module .env")
    experiment = args.experiment.resolve()
    if not experiment.is_relative_to((ROOT / "test-results/dialogue-evals").resolve()):
        parser.error("raw synthetic evidence must stay in ignored dialogue-evals")
    ledger = experiment / "budget.json"
    budget = json.loads(ledger.read_text(encoding="utf-8"))
    if budget.get("closed_at") or budget["limit"] != 12 or budget["arm_limit"] != 12:
        parser.error("closed or unauthorized budget")
    if json.loads((experiment / "suite.json").read_text(encoding="utf-8")) != suite:
        parser.error("suite changed after freeze")
    pointer = experiment / f"{args.series}-{case['id']}-turn{args.turn}.json"
    if pointer.exists():
        parser.error("turn already attempted; no implicit retry")
    from cbt_course_llm_freeform.agent import FreeformCourseAgent
    from cbt_course_llm_freeform.catalog import LESSON_1_VERSION
    from cbt_course_llm_freeform.design import MODEL_TOKEN_LIMITS
    from cbt_course_llm_freeform.prompt import prompt_for_lesson
    from cbt_course_llm_freeform.runtime import FreeformCourseRuntime

    frozen = json.loads((experiment / args.snapshot / "manifest.json").read_text(encoding="utf-8"))
    workspace = ROOT.parents[1]
    for name, fingerprint in frozen["files"].items():
        if name.endswith(".py") and digest((workspace / name).read_bytes()) != fingerprint:
            parser.error("Python source drift after candidate freeze: " + name)
    prompt = prompt_for_lesson("lesson-1")
    if prompt != (experiment / args.snapshot / "lesson-1-prompt.txt").read_text(encoding="utf-8"):
        parser.error("candidate prompt drift")
    initial, initial_history = fixture(case)
    state, history = copy.deepcopy(initial), copy.deepcopy(initial_history)
    prefix_source = None
    if args.turn > 1:
        previous_series = args.prefix_series or args.series
        ref = json.loads((experiment / f"{previous_series}-{case['id']}-turn{args.turn-1}.json").read_text(encoding="utf-8"))
        previous = json.loads((Path(ref["target"]) / "results.json").read_text(encoding="utf-8"))
        if previous["turn"]["status"] != "success" or not all(previous["program_checks"].values()):
            parser.error("previous turn failed; stop this card")
        state, history = previous["state"], previous["history"]
        if args.prefix_series:
            prefix_source = dict(**ref, original_lesson_version=state["lesson_version"], adaptation="same successful state/history; lesson-version metadata updated for aligned-pause controller repair")
            state["lesson_version"] = LESSON_1_VERSION
        if state.get("paused") or state.get("safety_paused") or state.get("completed"):
            parser.error("previous turn paused or completed; stop this card")
    configuration = configure_eval_environment(args.env_file)
    parameters = dict(provider=configuration["provider"], model=os.getenv("CBT_COURSE_MODEL"),
                      temperature=1.0, thinking="disabled", max_completion_tokens=MODEL_TOKEN_LIMITS["lesson-1"])
    if parameters != json.loads((experiment / "public-config.json").read_text(encoding="utf-8")):
        parser.error("model or parameter drift; no call sent")
    env_bytes = args.env_file.read_bytes()
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + f"-030-{args.series}-{case['id']}-t{args.turn}-" + uuid.uuid4().hex[:6]
    target = experiment.parent / run_id
    target.mkdir(exist_ok=False)
    save(pointer, dict(run_id=run_id, target=str(target)))
    save(target / "manifest.json", dict(run_id=run_id, started_at=datetime.now().astimezone().isoformat(),
         lesson_version=LESSON_1_VERSION, api_configuration=configuration, parameters=parameters,
         suite_version=suite["suite_version"], fixture_version=suite["fixture_version"],
         prompt_hash=digest(prompt.encode()), policy="none", interaction_reflection="enabled",
         post_course_reflection="retained, not exercised", transport="non-streaming",
         series=args.series, snapshot=args.snapshot, prefix_source=prefix_source, review_note=args.review_note, command_arguments=sys.argv[1:], code=freeze_code(target)))
    (target / "prompt.txt").write_text(prompt, encoding="utf-8")
    item = case["turns"][args.turn-1]
    latest = dict(id=f"{case['id']}-user-{args.turn}", role="learner", content=item["input"])
    before = copy.deepcopy(state)
    history.append(latest)
    recorder = DurableRecorder(FreeformCourseAgent._client_from_env(), SharedBudget(ledger), "after", run_id, target)
    runtime = FreeformCourseRuntime(agent=FreeformCourseAgent(client=recorder, system_prompt=prompt,
                                                            max_completion_tokens=MODEL_TOKEN_LIMITS["lesson-1"]))
    turn = dict(input=latest, before_state=before, status="pending")
    save(target / "results.json", dict(initial_state=initial, initial_history=initial_history, turn=turn, state=state, history=history))
    started = time.perf_counter()
    try:
        result = runtime.process(state, history)
        state = result.state
        history.append(dict(id=f"{case['id']}-agent-{args.turn}", role="agent", content=result.reply))
        turn.update(status="success", reply=result.reply, trace=result.trace, attachment=result.attachment)
    except Exception as exc:
        turn.update(status="error", error_type=type(exc).__name__, error_message=str(exc), unchanged_input_state=state == before)
    turn.update(elapsed_ms=round((time.perf_counter()-started)*1000), model_calls=copy.deepcopy(runtime.model_calls))
    checks = program_checks(initial, state, item["expect"])
    save(target / "results.json", dict(id=case["id"], initial_state=initial, initial_history=initial_history,
         turn=turn, state=state, history=history, program_checks=checks, human_review="pending"))
    summary = dict(run_id=run_id, **totals(recorder.requests), elapsed_ms=turn["elapsed_ms"],
                   turn_status=turn["status"], program_checks=checks, first_token_wait_ms=None,
                   automatic_retries=0, env_file_unchanged=args.env_file.read_bytes() == env_bytes)
    save(target / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 0 if turn["status"] == "success" and all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
