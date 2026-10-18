"""Small, synthetic real-DeepSeek navigation check; includes usage and latency."""
import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv


def main():
    project = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project))
    load_dotenv(project / ".env", encoding="utf-8-sig")
    os.environ["CBT_COURSE_PROVIDER"] = "deepseek"
    from cbt_course_llm_freeform.runtime import new_course_state, FreeformCourseRuntime
    cases = [("two_choices", "learning_goal", "目标先不设，也不安排课后练习，直接总结吧", "summary"),
        ("ambiguous_done", "learning_goal", "我觉得已经完成了", "learning_goal"),
        ("negated", "learning_goal", "我不是说不设目标，我想练习分清事实和猜测", "learning_goal"),
        ("reported", "learning_goal", "朋友说他不设置目标，我还没想好", "learning_goal"),
        ("plan_done", "plan", "我觉得已经完成了", "plan"),
        ("skip_goal", "learning_goal", "先不设置目标，继续吧", "plan")]
    rows = []
    for name, stage, text, expected in cases:
        state = new_course_state("lesson-1", reflection_policy="none")
        state["stage"] = stage
        state["learning_check"]["status"] = "completed"
        if name == "ambiguous_done":
            state["learning_goal_draft"] = {"value": "练习分清事实和猜测", "source_message_id": "draft"}
        result = FreeformCourseRuntime().process(state, [{"id": "guide", "role": "agent", "content": "请表达当前环节的选择。"},
            {"id": name, "role": "learner", "content": text}])
        event = result.trace.get("navigation_event", {})
        passed = result.state["stage"] == expected and event.get("status") == "accepted"
        if name in {"ambiguous_done", "reported", "plan_done"}:
            passed = passed and event.get("intent") == "clarify"
        row = {"case": name, "passed": passed, "stage": result.state["stage"], "reply": result.reply,
            "navigation_event": event, "model_calls": result.trace["model_calls"]}
        rows.append(row)
        print(json.dumps({k: row[k] for k in ("case", "passed", "stage", "reply")}, ensure_ascii=True), flush=True)
    report = {"synthetic_inputs": True, "cases": rows, "passed": all(r["passed"] for r in rows)}
    (project / "test-results/course-navigation-deepseek.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
