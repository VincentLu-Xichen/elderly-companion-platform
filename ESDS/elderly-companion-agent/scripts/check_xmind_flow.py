"""Small synthetic real-provider checks; raw evidence stays in ignored test-results."""
import json
import os
from pathlib import Path
import sys
import time

from dotenv import load_dotenv

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    load_dotenv(ROOT/".env",encoding="utf-8-sig")
    os.environ["CBT_COURSE_PROVIDER"]="deepseek"
    from cbt_course_llm_freeform.runtime import FreeformCourseRuntime,new_course_state
    from cbt_course_llm_freeform import lesson2_flow
    records=[]
    def run(name,state,text,check):
        start=time.perf_counter();runtime=FreeformCourseRuntime()
        try:
            result=runtime.process(state,[dict(id="synthetic-"+name,role="learner",content=text)])
            records.append(dict(name=name,passed=bool(check(result)),reply=result.reply,state=result.state,calls=runtime.model_calls,elapsed_ms=round((time.perf_counter()-start)*1000)))
        except Exception as exc:
            records.append(dict(name=name,passed=False,error_type=type(exc).__name__,calls=runtime.model_calls,elapsed_ms=round((time.perf_counter()-start)*1000)))
    state=new_course_state("lesson-1",reflection_policy="none");state["stage"]="practice"
    state["draft_record"]["situation"]={"value":"朋友没回复消息","source_message_id":"synthetic-old"}
    run("thought-help",state,"我不知道当时脑子里想了什么",lambda r:any(c["help"] and c["field"]=="thought" for c in r.state["teacher_flow"]["cards"]) and "thought" not in r.state["draft_record"])
    state=new_course_state("lesson-2",reflection_policy="none");lesson2_flow.go(state,"rain")
    run("rain-help",state,"不知道用什么词说这个感受",lambda r:r.state["lesson2_flow"]["step"]=="rain" and "小明" in r.reply)
    state=new_course_state("lesson-2",reflection_policy="none");lesson2_flow.go(state,"homework")
    run("homework-barrier",state,"这周没有做课后记录",lambda r:r.state["lesson2_flow"]["homework"].get("awaiting_barrier") is True)
    state=new_course_state("lesson-2",reflection_policy="none");lesson2_flow.go(state,"personal")
    run("personal-triad",state,"情境：散步时突然下雨；想法：今天的安排泡汤了；情绪：失望；情绪强度：4分",lambda r:r.state["lesson2_flow"]["step"]=="model" and r.state["lesson2_flow"]["rating"]["value"]==4)
    target=ROOT/"test-results"/"xmind-flow-real.json";target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(dict(cases=[dict(name=r["name"],passed=r["passed"],elapsed_ms=r["elapsed_ms"]) for r in records],
        calls=sum(len(r["calls"]) for r in records),tokens=sum(c.get("usage",{}).get("total_tokens",0) or 0 for r in records for c in r["calls"])),ensure_ascii=False))
    return 0 if all(r["passed"] for r in records) else 1


if __name__=="__main__":
    raise SystemExit(main())
