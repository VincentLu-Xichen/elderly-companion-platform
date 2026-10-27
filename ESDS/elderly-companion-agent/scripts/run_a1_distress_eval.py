"""Bounded A/A1 observation, one reviewed turn at a time; no product mutation/DB."""
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

SUITE = ROOT / "evals/cbt/cases.a1-distress.v1.json"
REFERENCES = ROOT / "test-results/dialogue-evals/20261024-A1-style-pair-6de712"


def reference_prompts(reference_root):
    from cbt_course_llm_freeform.prompt import prompt_for_lesson

    scope = json.loads((reference_root / "scope-verification.json").read_text(encoding="utf-8"))
    prompts, provenance = {}, {}
    for arm in ("before", "after"):
        pointer = json.loads((reference_root / (arm + "-initial.json")).read_text(encoding="utf-8"))
        target = Path(pointer["target"])
        prompt = (target / "prompt.txt").read_text(encoding="utf-8")
        fingerprint = digest(prompt.encode())
        if fingerprint != scope[arm + "_prompt_sha256"]:
            raise ValueError("Archived prompt fingerprint mismatch")
        prompts[arm] = prompt
        provenance[arm] = {"run_id": pointer["run_id"], "prompt_sha256": fingerprint}
    if prompts["before"] != prompt_for_lesson("lesson-1"):
        raise ValueError("Current reference prompt differs from the frozen A prompt")
    return prompts, provenance


def program_checks(initial, state, branch):
    values = {
        "same_case": initial["case_id"] == state["case_id"],
        "no_invented_scores": not state["blueprint"]["ratings"],
        "not_confirmed": state.get("confirmed_record") is None,
        "not_completed": not state.get("completed"),
    }
    if branch == "pause":
        values["paused_as_requested"] = bool(state.get("paused"))
    return values


def frozen_pair_prompts(folder):
    """Explicit paired override for a later revision; old 028 defaults stay strict."""
    from cbt_course_llm_freeform.prompt import prompt_for_lesson

    provenance = json.loads((folder / "provenance.json").read_text(encoding="utf-8"))
    prompts = {arm: (folder / (arm + ".txt")).read_text(encoding="utf-8") for arm in ("before", "after")}
    for arm, prompt in prompts.items():
        if digest(prompt.encode()) != provenance[arm]["prompt_sha256"]:
            raise ValueError("Frozen paired prompt fingerprint mismatch")
    if prompts["after"] != prompt_for_lesson("lesson-1"):
        raise ValueError("Current candidate prompt differs from frozen paired prompt")
    return prompts, provenance


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--arm", choices=("before", "after"))
    parser.add_argument("--turn", type=int, choices=(1, 2, 3))
    parser.add_argument("--branch", choices=("continue", "pause"))
    parser.add_argument("--gate-note")
    parser.add_argument("--experiment", type=Path)
    parser.add_argument("--reference-root", type=Path, default=REFERENCES)
    parser.add_argument("--suite-file", type=Path, default=SUITE)
    parser.add_argument("--case")
    parser.add_argument("--prompt-dir", type=Path)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    args = parser.parse_args()
    suite = json.loads(args.suite_file.read_text(encoding="utf-8"))
    cases = suite.get("cases", [suite])
    if args.case and args.case not in {case["id"] for case in cases}:
        parser.error("case not present in selected suite")
    if len(cases) > 1 and not args.case and args.live:
        parser.error("choose exactly one case for each live invocation")
    for case in cases:
        fixture(case)
    case = next((case for case in cases if case["id"] == args.case), cases[0])
    seed, history = fixture(case)
    prompts, provenance = frozen_pair_prompts(args.prompt_dir) if args.prompt_dir else reference_prompts(args.reference_root)
    if not args.live:
        print(json.dumps({"validated": [item["id"] for item in cases], "api_calls": 0,
                          "initial_history": history, "prompt_sources": provenance}, ensure_ascii=False))
        return 0
    if not args.arm or not args.turn or not args.experiment:
        parser.error("live requires arm, turn and experiment")
    if args.turn > 1 and not args.gate_note:
        parser.error("later turns require an offline review gate note")
    if (args.turn == 3) != bool(args.branch):
        parser.error("choose exactly one branch for turn 3 only")
    key = str(args.turn) if args.turn < 3 else "3-" + args.branch
    if key not in case["turns"]:
        parser.error("turn not present in selected case")
    allowed = (ROOT / "test-results/dialogue-evals").resolve()
    experiment = args.experiment.resolve()
    if not experiment.is_relative_to(allowed):
        parser.error("experiment must be in ignored synthetic dialogue-evals")
    experiment.mkdir(parents=True, exist_ok=True)
    ledger = experiment / "budget.json"
    case_prefix = case["id"] + "-" if "cases" in suite else ""
    pointer = experiment / f"{args.arm}-{case_prefix}turn{args.turn}.json"
    if pointer.exists():
        parser.error("turn already attempted; no automatic reruns")
    if not ledger.exists():
        if args.arm != "before" or args.turn != 1:
            parser.error("begin with before turn 1")
        save(ledger, {"limit": 12, "arm_limit": 6, "attempts": [],
                      "authorization": "User selected a new paired observation, at most 12 total requests; separate from any closed budget"})
        save(experiment / "suite.json", suite)
        save(experiment / "prompt-provenance.json", provenance)
    if json.loads((experiment / "suite.json").read_text(encoding="utf-8")) != suite:
        parser.error("suite changed within experiment")
    if json.loads((experiment / "prompt-provenance.json").read_text(encoding="utf-8")) != provenance:
        parser.error("prompt sources changed within experiment")
    if json.loads(ledger.read_text(encoding="utf-8")).get("closed_at"):
        parser.error("experiment budget is closed")

    initial = copy.deepcopy(seed)
    # Isolated experiment metadata only; source catalog and application stay unchanged.
    initial["lesson_version"] = provenance[args.arm].get("lesson_version") or (
        "7.5-two-lesson-backend" if args.arm == "before" else "7.6-a1-communication-style")
    state = copy.deepcopy(initial)
    initial_history = copy.deepcopy(history)
    if args.turn > 1:
        previous_pointer = experiment / f"{args.arm}-{case_prefix}turn{args.turn - 1}.json"
        previous_ref = json.loads(previous_pointer.read_text(encoding="utf-8"))
        previous = json.loads((Path(previous_ref["target"]) / "results.json").read_text(encoding="utf-8"))
        if previous["turn"]["status"] != "success":
            parser.error("cannot continue a failed turn")
        state, history = previous["state"], previous["history"]
        if state.get("paused") or state.get("safety_paused") or state.get("completed"):
            parser.error("previous state is paused or complete; stop this card")

    from cbt_course_llm_freeform.agent import FreeformCourseAgent
    from cbt_course_llm_freeform.design import MODEL_TOKEN_LIMITS
    from cbt_course_llm_freeform.presentation import course_payload
    from cbt_course_llm_freeform.runtime import FreeformCourseRuntime

    api_configuration = configure_eval_environment(args.env_file)
    public_config = {"provider": api_configuration["provider"], "model": os.getenv("CBT_COURSE_MODEL"),
                     "temperature": 1.0, "thinking": "disabled", "max_completion_tokens": MODEL_TOKEN_LIMITS["lesson-1"]}
    old_config = json.loads((args.reference_root / "public-config.json").read_text(encoding="utf-8"))
    if public_config != old_config:
        parser.error("model/parameters differ from 028; no request sent")
    config_path = experiment / "public-config.json"
    if config_path.exists() and json.loads(config_path.read_text(encoding="utf-8")) != public_config:
        parser.error("model/parameters changed between turns")
    save(config_path, public_config)
    env_bytes = args.env_file.read_bytes()
    client = FreeformCourseAgent._client_from_env()
    run_id = (datetime.now().strftime("%Y%m%d-%H%M%S") + f"-{case['id']}-{args.arm}-t{args.turn}-" + uuid.uuid4().hex[:6])
    target = allowed / run_id
    target.mkdir(exist_ok=False)
    save(pointer, {"run_id": run_id, "target": str(target)})
    prompt = prompts[args.arm]
    save(target / "manifest.json", {"run_id": run_id, "started_at": datetime.now().astimezone().isoformat(),
         "arm": args.arm, "turn": args.turn, "branch": args.branch, "gate_note": args.gate_note,
         "suite_version": suite["suite_version"], "fixture_version": suite["fixture_version"],
         "api_configuration": api_configuration, "parameters": public_config,
         "prompt_source": provenance[args.arm], "prompt_hash": digest(prompt.encode()),
         "policy": "none", "interaction_reflection": "enabled", "transport": "non-streaming",
         "candidate_injected_only_into_eval_agent": True, "product_source_changed_by_capture": False,
         "code": freeze_code(target)})
    (target / "prompt.txt").write_text(prompt, encoding="utf-8")
    save(target / "cases.json", suite)
    latest = {"id": f"{case['id']}-user-{args.turn}", "role": "learner", "content": case["turns"][key]}
    before = copy.deepcopy(state)
    history.append(latest)
    recorder = DurableRecorder(client, SharedBudget(ledger), args.arm, run_id, target)
    runtime = FreeformCourseRuntime(agent=FreeformCourseAgent(client=recorder, system_prompt=prompt,
                                                             max_completion_tokens=MODEL_TOKEN_LIMITS["lesson-1"]))
    turn = {"input": latest, "before_state": before, "request_offset": 0}
    save(target / "results.json", {"initial_state": initial, "initial_history": initial_history,
                                   "turn": {**turn, "status": "pending"}, "state": before, "history": history})
    started = time.perf_counter()
    try:
        result = runtime.process(state, history)
        state = result.state
        history.append({"id": f"{case['id']}-agent-{args.turn}", "role": "agent", "content": result.reply})
        turn.update(status="success", reply=result.reply, trace=result.trace,
                    attachment=result.attachment, payload=course_payload(state))
    except Exception as exc:
        turn.update(status="error", error_type=type(exc).__name__, error_message=str(exc),
                    unchanged_input_state=state == before)
    turn.update(elapsed_ms=round((time.perf_counter() - started) * 1000),
                model_calls=copy.deepcopy(runtime.model_calls))
    checks = program_checks(initial, state, args.branch)
    row = {"id": case["id"], "initial_state": initial, "initial_history": initial_history,
           "turn": turn, "state": state, "history": history, "program_checks": checks,
           "observed_facts": {"paused": bool(state.get("paused")),
                              "safety_paused": bool(state.get("safety_paused")),
                              "deferred": state.get("practice_flow", {}).get("deferred"),
                              "stop_probing": state.get("practice_flow", {}).get("stop_probing")},
           "human_review": "pending"}
    save(target / "results.json", row)
    save(target / "requests.json", recorder.requests)
    summary = {"run_id": run_id, **totals(recorder.requests), "elapsed_ms": turn["elapsed_ms"],
               "env_file_unchanged": args.env_file.read_bytes() == env_bytes,
               "turn_status": turn["status"], "program_checks": checks,
               "first_token_wait_ms": None, "automatic_retries": 0}
    save(target / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 0 if turn["status"] == "success" and all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
