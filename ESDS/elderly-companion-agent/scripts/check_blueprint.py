"""Three bounded synthetic DeepSeek scenarios; writes local evidence, never keys."""
import json
import os
import sys
import time
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=("normal", "privacy", "stop_and_goal_edit"))
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project))
    from dotenv import load_dotenv
    load_dotenv(project / ".env", encoding="utf-8-sig")
    os.environ["CBT_COURSE_PROVIDER"] = "deepseek"
    from cbt_course_llm_freeform.runtime import FreeformCourseRuntime, new_course_state
    from cbt_course_llm_freeform import boundaries, practice_flow
    rows = []
    for name in ([args.case] if args.case else ("normal", "privacy", "stop_and_goal_edit")):
        state = new_course_state("lesson-1", reflection_policy="none")
        history, steps = [], []
        runtime = FreeformCourseRuntime()
        def turn(text="", action="chat"):
            nonlocal state
            mid = f"{name}:{len(steps)}"
            history.append({"id": mid, "role": "learner", "content": text or action})
            started = time.perf_counter()
            result = runtime.process(state, history, action=action)
            state = result.state
            history.append({"id": mid + ":a", "role": "agent", "content": result.reply})
            steps.append({"input": text or action, "stage": state["stage"], "reply": result.reply,
                "elapsed_ms": round((time.perf_counter() - started) * 1000), "trace": result.trace})
            return result
        try:
            turn(action="skip_checkin")
            if name == "privacy":
                turn("我不想谈自己的事情")
                assert state["privacy"]["pending"] and boundaries.fictional(state)
                turn("好的，以后所有课程都用虚构案例，不主动问我的私事")
                assert state["disclosure_boundary"]["scope"] == "cross_course"
                turn("事情是活动取消；想法是白跑一趟；心情是失望；做法是回家")
                assert not state["blueprint"]["ratings"]
            else:
                turn("我想分析昨天下午散步时，邻居没回应我的招呼这件事。")
                case_id = state["case_id"]
                turn("我想到他是不是不愿理我，心里失落，后来继续散步，没有再叫他。")
                if name == "stop_and_goal_edit":
                    turn("你为什么要一直追问我，我已经说了这么多，别再问了")
                    assert state["case_id"] == case_id and state["stage"] == "review" and not boundaries.fictional(state)
                else:
                    assert practice_flow.current_field(state) == "thought_belief"
                    turn("0分")
                    assert state["blueprint"]["ratings"]["thought_belief"]["value"] == 0
                    turn("6分")
                    assert state["blueprint"]["ratings"]["emotion_intensity"]["value"] == 6
            assert state["stage"] == "review"
            if name == "normal":
                turn("现在我看到，没回应是发生的事，不愿理我只是我当时的解释。")
            turn(action="confirm_record")
            for answer in ("有人和我打招呼，我一时没想到合适的回应", "担心不回应会让对方觉得不礼貌，影响关系", "紧张", "不断找话题，接着和对方说话"):
                turn(answer)
            assert state["learning_check"]["status"] == "completed"
            turn(action="continue_after_check")
            if name == "privacy":
                turn("目标先不设，也不安排课后练习，直接总结吧")
            else:
                turn("每周用四要素记录一件事；每周留意一次当时的情绪")
                assert len(state["learning_goal_draft"]["items"]) == 2
                turn(action="confirm_learning_goal")
                if name == "stop_and_goal_edit":
                    original_first = state["learning_goal"]["items"][0]
                    turn("第二项目标改为每周记录两次情绪，第一项不变")
                    assert state["stage"] == "learning_goal" and not state.get("learning_goal")
                    assert state["learning_goal_draft"]["items"][0] == original_first
                    assert len(state["learning_goal_draft"]["items"]) == 2
                    turn(action="confirm_learning_goal")
                turn(action="decline_practice")
            turn("没有补充了，结束本课吧")
            assert state["completed"]
            passed, error = True, None
        except Exception as exc:
            passed, error = False, type(exc).__name__
        rows.append({"case": name, "passed": passed, "error_type": error, "steps": steps, "state": state})
        print(json.dumps({"case": name, "passed": passed, "error_type": error, "steps": len(steps)}, ensure_ascii=True), flush=True)
    calls = [call for row in rows for step in row["steps"] for call in step["trace"].get("model_calls", [])]
    usage = {"calls": len(calls), "total_tokens": sum(call.get("usage", {}).get("total_tokens", 0) for call in calls),
        "model_elapsed_ms": sum(call.get("elapsed_ms", call.get("latency_ms", 0)) for call in calls)}
    output = {"synthetic": True, "usage": usage, "cases": rows}
    destination = f"blueprint-deepseek-{args.case}.json" if args.case else "blueprint-deepseek.json"
    (project / "test-results" / destination).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(usage), flush=True)
    return 0 if all(row["passed"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
