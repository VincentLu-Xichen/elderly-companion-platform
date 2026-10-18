"""Bounded fictional DeepSeek semantic checks; never loads existing course histories."""
from __future__ import annotations
import copy
import json
import os
import re
from pathlib import Path
import sys
from dotenv import load_dotenv


def main():
    project = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project))
    load_dotenv(project / ".env", encoding="utf-8-sig")
    os.environ["CBT_COURSE_PROVIDER"] = "deepseek"
    from cbt_course_llm_freeform.runtime import FreeformCourseRuntime, new_course_state
    cases = [("whole_refusal", "我不是很想说关于我的事情", "refuse_personal"),
             ("negative", "我没有不想谈自己的事情，愿意继续", None),
             ("reported", "朋友说他不想谈自己的事情，我只是转述", None),
             ("field_only", "这一项不愿回答，其他部分可以继续", "refuse_field")]
    focus_only = "--focus-only" in sys.argv
    if focus_only:
        cases = cases[:1]
    report = {"fictional_input": True, "cases": []}
    first_state = None
    for name, text, expected in cases:
        state = new_course_state("lesson-1", reflection_policy="none")
        state["stage"] = "practice"
        history = [{"id": "fictional-guide", "role": "agent", "content": "最近有没有愿意聊的个人经历？"},
                   {"id": name, "role": "learner", "content": text}]
        row = {"case": name}
        try:
            result = FreeformCourseRuntime().process(state, history)
            actual = (result.trace.get("boundary_event") or {}).get("intent")
            valid_reply = expected is not None or not any(word in result.reply for word in ("用虚构", "虚构的小例子", "虚构案例"))
            row.update(passed=actual == expected and valid_reply, intent=actual, reply=result.reply, model_calls=result.trace["model_calls"],
                       boundary_event=result.trace.get("boundary_event"),
                       event_status=(result.trace.get("interaction_event") or {}).get("status"), interaction_event=result.trace.get("interaction_event"))
            if name == "whole_refusal" and actual == expected:
                first_state = (result.state, history + [{"id": "confirmation-question", "role": "agent", "content": result.reply}])
        except Exception as exc:
            row.update(passed=False, error_type=type(exc).__name__)
        report["cases"].append(row)
        print(json.dumps({key: value for key, value in row.items() if key in {"case", "passed", "intent", "reply", "event_status", "error_type"}}, ensure_ascii=True), flush=True)
    if first_state:
        for name, text, expected_scope in (("confirmed", "好，以后都用虚构例子", "cross_course"), ("ambiguous", "嗯随便，继续吧", "lesson")):
            state, history = copy.deepcopy(first_state)
            row = {"case": name}
            try:
                result = FreeformCourseRuntime().process(state, history + [{"id": name, "role": "learner", "content": text}])
                note = (result.trace.get("boundary_event") or {}).get("memory", {})
                focused = not re.search(r"(?:事情是|遇到的事情是).*属于|想法.*影响.*情绪|接下来会", result.reply)
                row.update(passed=note.get("scope") == expected_scope and result.state["privacy"]["pending"] is None and focused,
                           scope=note.get("scope"), reply=result.reply, model_calls=result.trace["model_calls"])
            except Exception as exc:
                row.update(passed=False, error_type=type(exc).__name__)
            report["cases"].append(row)
            print(json.dumps({key: value for key, value in row.items() if key != "model_calls"}, ensure_ascii=True), flush=True)
    report["passed"] = len(report["cases"]) == (3 if focus_only else 6) and all(row["passed"] for row in report["cases"])
    report["call_count"] = sum(len(row.get("model_calls", [])) for row in report["cases"])
    report["total_tokens"] = sum(call.get("usage", {}).get("total_tokens", 0) for row in report["cases"] for call in row.get("model_calls", []))
    target = project / "test-results" / ("personal-boundary-deepseek-final-focus.json" if focus_only else "personal-boundary-deepseek.json")
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
