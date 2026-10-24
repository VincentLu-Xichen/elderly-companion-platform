"""Small synthetic check for previously missed multi-field utterances."""
import json
import os
from pathlib import Path
import sys
import time

def main():
    project=Path(__file__).resolve().parents[1];sys.path.insert(0,str(project))
    from dotenv import load_dotenv
    load_dotenv(project/".env",encoding="utf-8-sig");os.environ["CBT_COURSE_PROVIDER"]="deepseek"
    from cbt_course_llm_freeform.agent import FreeformCourseAgent
    from cbt_course_llm_freeform import lesson2_flow as flow
    from cbt_course_llm_freeform.runtime import FreeformCourseRuntime,new_course_state
    cases=[("rain","会有点失望，但也放松，想到可以在家休息。"),("rain","我很生气，脑中冒出的是老天又在跟我作对。"),("personal","昨天朋友没回消息，我想到他可能很忙，但还是有些担心"),("complaint","为什么一直追问，我已经说过这些了")]
    rows=[];calls=[];started=time.perf_counter()
    for index,(step,text) in enumerate(cases):
        state=new_course_state("lesson-2",reflection_policy="none");flow.go(state,"personal" if step=="complaint" else step)
        runtime=FreeformCourseRuntime(agent=FreeformCourseAgent())
        try:
            result=runtime.process(state,[{"id":f"synthetic-{index}","role":"learner","content":text}])
            record=result.state["lesson2_flow"]["rain"]["fields"] if step=="rain" else result.state["draft_record"]
            passed=result.state["lesson2_flow"]["step"]=="model" and not result.state["paused"] and result.state["case_id"]==state["case_id"] if step=="complaint" else set(record)==({"emotion","thought"} if step=="rain" else set(flow.TRIAD))
            rows.append({"step":step,"passed":passed,"reply":result.reply,"record":record})
        except Exception as exc:rows.append({"step":step,"passed":False,"error_type":type(exc).__name__})
        calls.extend(runtime.model_calls)
    output={"synthetic":True,"rows":rows,"calls":calls,"usage":{"calls":len(calls),"tokens":sum(c.get("usage",{}).get("total_tokens",0) for c in calls),"wall_ms":round((time.perf_counter()-started)*1000)}}
    (project/"test-results/lesson2-extraction.json").write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"cases":[r["passed"] for r in rows],"usage":output["usage"]}),flush=True)
    return int(not all(r["passed"] for r in rows))

if __name__=="__main__":raise SystemExit(main())
