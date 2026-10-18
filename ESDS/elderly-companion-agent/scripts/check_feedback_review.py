"""Bounded synthetic checks of semantic recovery and a sourced case recap."""
import copy
import json
import os
from pathlib import Path
import sys
import time


def main():
    project = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project))
    from dotenv import load_dotenv
    load_dotenv(project / ".env", encoding="utf-8-sig")
    os.environ["CBT_COURSE_PROVIDER"] = "deepseek"
    from cbt_course_llm_freeform.agent import FreeformCourseAgent
    from cbt_course_llm_freeform.runtime import FreeformCourseRuntime
    from cbt_course_llm_freeform.tests.test_feedback_review import checking, fictional_review
    rows, calls, outputs = [], [], []
    class RecordingClient:
        def __init__(self): self.client = FreeformCourseAgent._client_from_env()
        def complete_with_metadata(self, messages, **kwargs):
            response = self.client.complete_with_metadata(messages, **kwargs)
            outputs.append(dict(prompt_marker=messages[0]["content"][:50], text=response.text))
            return response
    def make_agent(): return FreeformCourseAgent(client=RecordingClient())
    for name, text, expected in (
        ("quantity", "我不想做这么多题目", "stop"),
        ("missed_candidate", "这一组练习就到这儿吧", "stop"),
        ("negation", "我不是不想做这么多题，我愿意继续", "stay"),
        ("reported", "朋友说他不想做这么多题目，我只是在转述", "stay"),
        ("length", "解释太长了，请说短一点", "stay"),
        ("difficulty", "好难，我需要一点提示", "hint"),
        ("pause", "我先休息，暂停课程", "pause"),
    ):
        runtime = FreeformCourseRuntime(agent=make_agent())
        started = time.perf_counter()
        try:
            result = runtime.process(checking(), [{"id": name, "role": "learner", "content": text}])
            state = result.state
            passed = (state["stage"] == "check_feedback" if expected == "stop" else state.get("paused") if expected == "pause" else state["stage"] == "assessment" and not state.get("paused") and state["learning_check"]["index"] == 1)
            if expected == "hint":
                passed = passed and bool(state["learning_check"]["hints"])
            rows.append(dict(case=name, passed=bool(passed), reply=result.reply, stage=state["stage"], check=state["learning_check"], trace=result.trace))
        except Exception as exc:
            rows.append(dict(case=name, passed=False, error_type=type(exc).__name__))
        calls.extend(copy.deepcopy(runtime.model_calls))
        rows[-1]["wall_ms"] = round((time.perf_counter() - started) * 1000)
        print(json.dumps({"case": name, "passed": rows[-1]["passed"]}), flush=True)
    agent = make_agent()
    for text, match in (("白跑了一堂", True), ("没有白跑，还是有收获", False)):
        try:
            result = agent.evaluate_answer([{"id": "typo", "role": "learner", "content": text}], context={"story": "小陈看到活动取消，想到白跑了一趟，感到失望，随后回家。", "question": "小陈当时想到什么？", "expected": "白跑了一趟", "field": "thought", "retry": False})
            passed = (result.decision.verdict == "matches") == match and result.decision.interaction is None
            rows.append(dict(case=text, passed=passed, decision=result.decision.model_dump()))
        except Exception as exc:
            rows.append(dict(case=text, passed=False, error_type=type(exc).__name__))
    calls.extend(copy.deepcopy(agent.call_log))
    runtime = FreeformCourseRuntime(agent=make_agent())
    result = runtime._result(fictional_review(), "old", "practice")
    recap = result.state["blueprint"]["case_review"]
    rows.append(dict(case="fictional_recap", passed=recap.get("status") == "ready" and "本次留空" not in result.reply and "白跑了一堂" == result.state["draft_record"]["thought"]["value"], reply=result.reply, recap=recap))
    calls.extend(copy.deepcopy(runtime.model_calls))
    usage = {"calls": len(calls), "total_tokens": sum(item.get("usage", {}).get("total_tokens", 0) for item in calls), "latency_ms": sum(item.get("latency_ms", 0) for item in calls)}
    output = dict(synthetic=True, cases=rows, calls=calls, outputs=outputs, usage=usage)
    (project / "test-results/feedback-review-deepseek.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": sum(row["passed"] for row in rows), "total": len(rows), "usage": usage}), flush=True)
    return 0 if all(row["passed"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
