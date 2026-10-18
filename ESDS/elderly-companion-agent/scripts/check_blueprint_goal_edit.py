"""Focused synthetic goal edits, including the exact browser failure wording."""
import copy
import json
import os
import sys
from pathlib import Path


def main():
    project=Path(__file__).resolve().parents[1];sys.path.insert(0,str(project))
    from dotenv import load_dotenv
    load_dotenv(project/".env",encoding="utf-8-sig");os.environ["CBT_COURSE_PROVIDER"]="deepseek"
    from cbt_course_llm_freeform.runtime import FreeformCourseRuntime,new_course_state
    base=[dict(value="每周用四要素记录一件事",source_message_id="original"),dict(value="每周留意一次当时的情绪",source_message_id="original")]
    rows=[]
    for name,text,index,expected in [
        ("exact_browser_phrase","第二项目标改为每周记录两次情绪，第一项不变",1,"每周记录两次情绪"),
        ("first_only","第一项目标改为每周观察两次心情，第二项保持不变",0,"每周观察两次心情"),
        ("negation","我不是要修改第二项目标，只是问问第二项写了什么",None,None)]:
        state=new_course_state("lesson-1",reflection_policy="none");state["stage"]="plan"
        state["learning_goal"]={"status":"confirmed","value":"；".join(item["value"] for item in base),"items":copy.deepcopy(base),"confirmation_message_id":"confirmed"}
        state["learning_goal_draft"]=copy.deepcopy(state["learning_goal"])
        result=FreeformCourseRuntime().process(state,[
            dict(id="original",role="learner",content="；".join(item["value"] for item in base)),
            dict(id="confirmed",role="learner",content="确认这些目标"),
            dict(id="guide",role="agent",content="接下来选择是否安排课后观察，也可以修改课程目标。"),
            dict(id=name,role="learner",content=text)])
        if index is None:
            passed=result.state["stage"]=="plan" and result.state["learning_goal"]==state["learning_goal"]
        else:
            items=result.state.get("learning_goal_draft",{}).get("items",[])
            passed=(result.state["stage"]=="learning_goal" and not result.state.get("learning_goal") and len(items)==2
                and items[index]["value"]==expected and items[1-index]==base[1-index])
        rows.append(dict(case=name,passed=passed,reply=result.reply,trace=result.trace))
        print(json.dumps(dict(case=name,passed=passed,event=result.trace.get("navigation_event")),ensure_ascii=True),flush=True)
    calls=[call for row in rows for call in row["trace"]["model_calls"]]
    usage=dict(calls=len(calls),total_tokens=sum(call.get("usage",{}).get("total_tokens",0) for call in calls),model_elapsed_ms=sum(call.get("latency_ms",0) for call in calls))
    (project/"test-results/blueprint-goal-edit-final.json").write_text(json.dumps(dict(synthetic=True,usage=usage,cases=rows),ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(usage),flush=True)
    return 0 if all(row["passed"] for row in rows) else 1


if __name__=="__main__":raise SystemExit(main())
