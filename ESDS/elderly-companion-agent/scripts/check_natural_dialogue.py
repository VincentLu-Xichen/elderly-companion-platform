"""Bounded synthetic checks; raw replies and costs stay in ignored test-results."""
import json
import os
from pathlib import Path
import sys
import time
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    load_dotenv(ROOT / ".env", encoding="utf-8-sig")
    os.environ["CBT_COURSE_PROVIDER"] = "deepseek"
    from cbt_course_llm_freeform.runtime import FreeformCourseRuntime, new_course_state
    from cbt_course_llm_freeform.tests.test_blueprint import ready_state
    records = []

    def run(name, state, text, check):
        runtime = FreeformCourseRuntime(); start = time.perf_counter()
        try:
            result = runtime.process(state, [{"id": "synthetic-"+name, "role": "learner", "content": text}])
            records.append(dict(name=name, input=text, passed=bool(check(result)), reply=result.reply,
                stage=result.state["stage"], calls=runtime.model_calls, elapsed_ms=round((time.perf_counter()-start)*1000)))
        except Exception as exc:
            records.append(dict(name=name, input=text, passed=False, error_type=type(exc).__name__,
                calls=runtime.model_calls, elapsed_ms=round((time.perf_counter()-start)*1000)))

    state=new_course_state("lesson-1", reflection_policy="none");state["stage"]="learn"
    run("case",state,"昨天数学考试最后一道题没做出来，考完有点烦。",lambda r:"situation" in r.state["draft_record"] and r.state["stage"]=="practice")
    state=new_course_state("lesson-1", reflection_policy="none");state["stage"]="practice"
    state["draft_record"]["situation"]={"value":"数学考试最后一题没做出来", "source_message_id":"synthetic-old"}
    run("help",state,"我不太记得当时的想法了。",lambda r:"thought" not in r.state["draft_record"] and any(c["help"] for c in r.state["teacher_flow"]["cards"]))
    run("review",ready_state(),"没有其他补充了。",lambda r:r.state["confirmed_record"] is None and r.state["stage"]=="review")
    run("confirm",ready_state(),"准确",lambda r:r.state["confirmed_record"] is not None and r.state["stage"]=="assessment" and not r.trace["model_calls"])
    state=new_course_state("lesson-1", reflection_policy="none");state["stage"]="learning_goal"
    run("goal-direction",state,"我希望考试没做好以后，不要一直反复自责，也希望更清楚自己当时在想什么。",lambda r:r.state["blueprint"]["goal_direction"] is not None and "learning_goal" not in r.state)
    state=new_course_state("lesson-1", reflection_policy="none");state["stage"]="learning_goal";state["blueprint"]["goal_step"]="concrete"
    run("goal-concrete",state,"我愿意在考试后出现反复自责时，尝试记录一次事情、想法、情绪和做法。不要求每次都记。",lambda r:bool(r.state.get("learning_goal_draft")) and "learning_goal" not in r.state)
    target=ROOT/"test-results"/f"natural-real-{time.strftime('%Y%m%d-%H%M%S')}.json"
    target.write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(dict(cases=[{k:r[k] for k in ("name","passed","elapsed_ms")} for r in records],
        calls=sum(len(r["calls"]) for r in records), tokens=sum(c.get("usage",{}).get("total_tokens",0) or 0 for r in records for c in r["calls"]),
        elapsed_ms=sum(r["elapsed_ms"] for r in records), file=target.name),ensure_ascii=False))
    return 0 if all(r["passed"] for r in records) else 1


if __name__=="__main__":raise SystemExit(main())
