"""Capture bounded synthetic dialogue trials; never touches the application DB."""

from __future__ import annotations

import argparse
import copy
from dataclasses import asdict
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SUITE = ROOT / "evals/cbt/cases.v1.json"


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fixture(case):
    """Versioned semantic starting points, not transcripts of a full course."""
    from cbt_course_llm_freeform import blueprint, learning_check, lesson2_flow
    from cbt_course_llm_freeform.state import new_course_state

    index = iter(range(1, 100))
    with patch(
        "uuid.uuid4",
        side_effect=lambda: uuid.uuid5(uuid.NAMESPACE_URL, case["id"] + str(next(index))),
    ):
        state = new_course_state(case["lesson"], reflection_policy="none")
    history = []
    kind = case["fixture"]
    if kind == "first-learn":
        state["stage"] = "learn"
        question = "这节课一起学习整理事情、想法、心情和做法。可以先说一件愿意讨论的小事。"
    elif kind in {"first-practice", "first-review"}:
        fields = {
            "situation": "数学考试最后一道题没做出来",
            "thought": "别人肯定都会，只有我不会",
            "emotion": "担心",
        }
        if kind == "first-review":
            fields["behavior"] = "考完一直翻答案"
        text = "；".join(fields.values()) + "；相信程度7分；情绪强度6分"
        latest = {"id": "seed-user", "role": "learner", "content": text}
        history.append(latest)
        state["draft_record"] = {
            k: {"value": v, "source_message_id": latest["id"], "source_kind": "personal"}
            for k, v in fields.items()
        }
        from types import SimpleNamespace

        for key, quote in [
            ("thought_belief", "相信程度7分"),
            ("emotion_intensity", "情绪强度6分"),
        ]:
            assert blueprint.accept_rating(
                state, SimpleNamespace(field=key, value=quote), latest, key
            )
        state["stage"] = "review" if kind == "first-review" else "practice"
        question = (
            blueprint.review_text(state, invite=False)
            if kind == "first-review"
            else "带着担心，您当时做了什么，或没有做什么？"
        )
    elif kind == "first-check-feedback":
        learning_check.begin(state)
        for i, text in enumerate(
            ["有人打招呼时没想到回应", "担心对方觉得没礼貌影响关系", "紧张", "不断找话题和对方说话"]
        ):
            latest = {"id": f"seed-answer-{i}", "role": "learner", "content": text}
            history.append(latest)
            learning_check.save_answer(state, latest, "matches", "这是该题相应部分。")
        question = learning_check.feedback_text(state)
    elif kind == "second-contrast":
        flow = state["lesson2_flow"]
        text = "想象出游下雨取消时，我想到安排泡汤了，感到失望。"
        history.append({"id": "rain-user", "role": "learner", "content": text})
        flow["rain"]["fields"] = {
            k: {"value": v, "source_message_id": "rain-user"}
            for k, v in {"thought": "安排泡汤了", "emotion": "失望"}.items()
        }
        flow["rain"]["tone"] = "negative"
        question = lesson2_flow.make_contrast(state)
    else:
        raise ValueError("Unknown fixture: " + kind)
    history.append({"id": "seed-agent", "role": "agent", "content": question})
    return state, history


class RequestBudgetExceeded(RuntimeError):
    pass


class Recorder:
    """Count actual attempts, including failed calls; keep judgments out of model input."""

    def __init__(self, client, max_calls):
        self.client, self.max_calls = client, max_calls
        self.requests = []

    def complete_with_metadata(self, messages, **kwargs):
        if len(self.requests) >= self.max_calls:
            raise RequestBudgetExceeded("Evaluation request limit reached")
        entry = {
            "messages": copy.deepcopy(messages),
            "parameters": copy.deepcopy(kwargs),
            "status": "pending",
        }
        self.requests.append(entry)
        start = time.perf_counter()
        try:
            result = self.client.complete_with_metadata(messages, **kwargs)
            entry.update(status="success", response=asdict(result))
            return result
        except Exception as exc:
            entry.update(status="error", error_type=type(exc).__name__)
            raise
        finally:
            entry["elapsed_ms"] = round((time.perf_counter() - start) * 1000)


def checks(case, before, state, requests):
    record = state["draft_record"]
    goal = state.get("learning_goal_draft")
    ratings = state.get("blueprint", {}).get("ratings", {})
    values = {
        "four_fields": all(k in record for k in ("situation", "thought", "emotion", "behavior")),
        "zero_rating": ratings.get("thought_belief", {}).get("value") == 0,
        "same_case": state["case_id"] == before["case_id"],
        "same_situation": record.get("situation") == before["draft_record"].get("situation"),
        "not_confirmed": state.get("confirmed_record") is None,
        "record_confirmed": state.get("confirmed_record") is not None,
        "assessment_stage": state["stage"] == "assessment",
        "zero_calls": not requests,
        "stopped_probing": bool(state.get("practice_flow", {}).get("stop_probing")),
        "no_invented_behavior": "behavior" not in record,
        "goal_stage": state["stage"] == "learning_goal",
        "goal_recorded": bool(state.get("blueprint", {}).get("goal_direction") or goal),
        "goal_not_confirmed": "learning_goal" not in state,
        "rain_not_personal": case["lesson"] == "lesson-2"
        and not record
        and state["lesson2_flow"]["rain"]["fields"]["thought"]["value"] == "安排泡汤了",
    }
    return {name: values[name] for name in case["checks"]}


def freeze_code(target):
    workspace = Path(
        subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"], cwd=ROOT, text=True
        ).strip()
    )
    names = (
        subprocess.check_output(
            ["git", "ls-files", "-c", "-o", "--exclude-standard", "-z"], cwd=workspace
        )
        .decode("utf-8")
        .split("\0")
    )
    hashes = {}
    with zipfile.ZipFile(target / "source.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(set(names)):
            path = workspace / name
            if (
                not name
                or not path.is_file()
                or not (path.is_relative_to(ROOT) or name in {"AGENTS.md", ".gitignore"})
            ):
                continue
            if path.name.startswith(".env") and path.name != ".env.example":
                continue
            data = path.read_bytes()
            hashes[name] = digest(data)
            archive.writestr(name, data)
    return {
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "branch": subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=ROOT, text=True
        ).strip(),
        "status": subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).decode(
            "utf-8"
        ),
        "files": hashes,
        "source_fingerprint": digest(json.dumps(hashes, sort_keys=True).encode()),
        "archive_sha256": digest((target / "source.zip").read_bytes()),
    }


def totals(requests):
    usage = [r.get("response", {}).get("usage", {}) for r in requests]
    return {
        "attempted_calls": len(requests),
        "usage_missing_calls": sum(not u for u in usage),
        "known_tokens": {
            k: sum(u.get(k, 0) for u in usage)
            for k in ("prompt_tokens", "completion_tokens", "total_tokens")
        },
        "cost": None,
        "cost_note": "Not priced; no verified per-request cache/pricing breakdown. Missing usage is unknown, not zero.",
    }


def configure_eval_environment(env_file, provider=None):
    """Use the selected file as the sole API source; never inherit stale credentials."""
    from dotenv import dotenv_values

    env_file = Path(env_file).resolve()
    if not env_file.is_file():
        raise ValueError("Evaluation API configuration file does not exist.")
    config = dotenv_values(env_file, encoding="utf-8-sig", interpolate=False)
    selected = (config.get("CBT_COURSE_PROVIDER") or "").strip().lower()
    settings = {
        "deepseek": ("DEEPSEEK_API_KEY",),
        "dashscope": ("DASHSCOPE_API_KEY", "DASHSCOPE_CHAT_BASE_URL"),
        "azure": (
            "AZURE_OPENAI_API_KEY",
            "AZURE_OPENAI_ENDPOINT",
            "AZURE_OPENAI_COURSE_DEPLOYMENT",
            "AZURE_OPENAI_DEPLOYMENT",
            "AZURE_OPENAI_API_VERSION",
        ),
    }
    if selected not in settings:
        raise ValueError("Set CBT_COURSE_PROVIDER explicitly in the selected API file.")
    if provider and provider != selected:
        raise ValueError("--provider conflicts with the selected API file; no request was sent.")
    names = ("CBT_COURSE_PROVIDER", "CBT_COURSE_MODEL", *settings[selected])
    if any("${" in (config.get(name) or "") for name in names):
        raise ValueError("Evaluation API settings must be literal values, without interpolation.")
    required = {
        "deepseek": ("DEEPSEEK_API_KEY", "CBT_COURSE_MODEL"),
        "dashscope": ("DASHSCOPE_API_KEY", "CBT_COURSE_MODEL"),
        "azure": ("AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT"),
    }[selected]
    if any(not (config.get(name) or "").strip() for name in required):
        raise ValueError(
            "Required API settings are missing from the selected file; no inherited fallback."
        )
    if selected == "azure" and not (
        config.get("AZURE_OPENAI_COURSE_DEPLOYMENT") or config.get("AZURE_OPENAI_DEPLOYMENT")
    ):
        raise ValueError("An Azure deployment must be specified in the selected API file.")
    conflicts = [
        name for name in names if name in os.environ and os.environ[name] != config.get(name)
    ]
    # This affects only the short-lived evaluation process, never the file or app host.
    for name in names:
        os.environ.pop(name, None)
        if config.get(name):
            os.environ[name] = config[name]
    os.environ["CBT_COURSE_PROVIDER"] = selected
    return {
        "source": "explicit_env_file",
        "env_file": str(env_file),
        "provider": selected,
        "inherited_conflict_setting_names": conflicts,
        "credentials_recorded": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Make real model requests; default only validates fixtures",
    )
    parser.add_argument(
        "--provider",
        choices=["deepseek", "dashscope", "azure"],
        help="Optional assertion: must match the selected API file",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=ROOT / ".env",
        help="Authoritative API configuration file; inherited credentials are ignored",
    )
    parser.add_argument("--case", action="append", help="Run only these case IDs")
    parser.add_argument("--max-calls", type=int, default=12)
    parser.add_argument(
        "--label", default="baseline", help="Short label; raw runs always get a unique directory"
    )
    args = parser.parse_args()
    suite = json.loads(SUITE.read_text(encoding="utf-8"))
    cases = [c for c in suite["cases"] if not args.case or c["id"] in args.case]
    if not cases or args.case and set(args.case) - {c["id"] for c in cases}:
        parser.error("Unknown or empty case selection")
    if not 1 <= args.max_calls <= 100:
        parser.error("max-calls must be between 1 and 100")
    if not args.label.replace("-", "").replace("_", "").isalnum():
        parser.error("label must contain letters, digits, - or _")
    for case in cases:
        fixture(case)
    if not args.live:
        print(
            json.dumps(
                {
                    "validated": [c["id"] for c in cases],
                    "suite": suite["suite_version"],
                    "api_calls": 0,
                }
            )
        )
        return 0

    from cbt_course_llm_freeform.agent import FreeformCourseAgent
    from cbt_course_llm_freeform.design import MODEL_TOKEN_LIMITS
    from cbt_course_llm_freeform.prompt import prompt_for_lesson
    from cbt_course_llm_freeform.runtime import FreeformCourseRuntime
    from cbt_course_llm_freeform.presentation import course_payload

    try:
        api_configuration = configure_eval_environment(args.env_file, args.provider)
    except ValueError as exc:
        parser.error(str(exc))
    recorder = Recorder(FreeformCourseAgent._client_from_env(), args.max_calls)
    timestamp = datetime.now().astimezone().isoformat()
    run_id = (
        datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + args.label + "-" + uuid.uuid4().hex[:6]
    )
    target = ROOT / "test-results/dialogue-evals" / run_id
    target.mkdir(parents=True, exist_ok=False)
    manifest = {
        "run_id": run_id,
        "started_at": timestamp,
        "suite_version": suite["suite_version"],
        "suite_sha256": digest(SUITE.read_bytes()),
        "provider": api_configuration["provider"],
        "api_configuration": api_configuration,
        "configured_model": os.getenv("CBT_COURSE_MODEL") or "provider default",
        "policy": "none",
        "transport": "non-streaming",
        "max_calls": args.max_calls,
        "python": sys.version,
        "code": freeze_code(target),
    }
    save(target / "manifest.json", manifest)
    save(target / "cases.json", cases)
    rows = []
    for case in cases:
        state, history = fixture(case)
        before = copy.deepcopy(state)
        agent = FreeformCourseAgent(
            client=recorder,
            system_prompt=prompt_for_lesson(case["lesson"]),
            max_completion_tokens=MODEL_TOKEN_LIMITS[case["lesson"]],
        )
        runtime = FreeformCourseRuntime(agent=agent)
        row = {
            "id": case["id"],
            "title": case["title"],
            "initial_state": before,
            "initial_history": copy.deepcopy(history),
            "turns": [],
            "human_review": {
                "status": "pending",
                "criteria": case["human_review"],
                "decision": None,
                "evidence": [],
            },
        }
        start_case = len(recorder.requests)
        for index, text in enumerate(case["turns"]):
            latest = {"id": f"{case['id']}-user-{index}", "role": "learner", "content": text}
            history.append(latest)
            start = time.perf_counter()
            turn = {
                "input": latest,
                "before_state": copy.deepcopy(state),
                "request_offset": len(recorder.requests),
            }
            try:
                result = runtime.process(state, history)
                state = result.state
                history.append(
                    {"id": f"{case['id']}-agent-{index}", "role": "agent", "content": result.reply}
                )
                turn.update(
                    status="success",
                    reply=result.reply,
                    state=state,
                    attachment=result.attachment,
                    trace=result.trace,
                    payload=course_payload(state),
                )
            except Exception as exc:
                # Product clients sanitize provider errors; do not dump exception bodies/env.
                turn.update(
                    status="error",
                    error_type=type(exc).__name__,
                    unchanged_input_state=state == turn["before_state"],
                )
            turn.update(
                elapsed_ms=round((time.perf_counter() - start) * 1000),
                model_calls=copy.deepcopy(runtime.model_calls),
            )
            row["turns"].append(turn)
            save(target / "requests.json", recorder.requests)
            if turn["status"] == "error":
                break  # Failure is evidence; do not invent a continuation or silently retry.
        row["program_checks"] = checks(case, before, state, recorder.requests[start_case:])
        row["completed_inputs"] = len(row["turns"]) == len(case["turns"]) and all(
            t["status"] == "success" for t in row["turns"]
        )
        rows.append(row)
        save(target / "results.json", rows)
        print(
            json.dumps(
                {
                    "case": case["id"],
                    "completed_inputs": row["completed_inputs"],
                    "program_checks": row["program_checks"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
    summary = {
        "run_id": run_id,
        "cases": len(rows),
        "completed_cases": sum(r["completed_inputs"] for r in rows),
        "program_checks_passed": sum(
            all(r["program_checks"].values()) and r["completed_inputs"] for r in rows
        ),
        "human_review": "pending",
        **totals(recorder.requests),
        "elapsed_ms": sum(t["elapsed_ms"] for r in rows for t in r["turns"]),
    }
    save(target / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary["program_checks_passed"] == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
