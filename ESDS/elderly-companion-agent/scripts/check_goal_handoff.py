"""Reproduce goal statements at the actual post-check stage using synthetic data."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
from dotenv import load_dotenv

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--before',action='store_true');args=parser.parse_args()
    load_dotenv(ROOT/'.env',encoding='utf-8-sig');os.environ['CBT_COURSE_PROVIDER']='deepseek'
    from cbt_course_llm_freeform.runtime import FreeformCourseRuntime,new_course_state
    from cbt_course_llm_freeform.agent import FreeformCourseAgent
    from cbt_course_llm_freeform import learning_check
    rows=[]
    samples=[('goal','我的练习目标就是想减少焦虑 更积极的面对生活',True),
             ('concrete','我愿意在考试后出现反复自责时，尝试记录一次事情、想法、情绪和做法。不要求每次都记。',True),
             ('unclear','完成了',False),('feedback','这几道题对我有帮助，但我还没想好目标。',False)]
    if args.before:samples=samples[:1]
    for name,text,is_goal in samples:
        state=new_course_state('lesson-1',reflection_policy='none');learning_check.begin(state)
        for i in range(4):learning_check.save_answer(state,dict(id=f'synthetic-answer-{i}',content='合成原答'),'matches','合成反馈')
        assert state['stage']=='check_feedback'
        raw=[]
        class Recorder:
            def __init__(self):self.client=FreeformCourseAgent._client_from_env()
            def complete_with_metadata(self,*a,**kw):
                result=self.client.complete_with_metadata(*a,**kw);raw.append(result.text);return result
        runtime=FreeformCourseRuntime(agent=FreeformCourseAgent(client=Recorder()))
        start=time.perf_counter()
        try:
            result=runtime.process(state,[dict(id='synthetic-'+name,role='learner',content=text)])
            passed=(result.state['stage']=='learning_goal' and bool(result.state['blueprint']['goal_direction'] or result.state.get('learning_goal_draft'))) if is_goal else result.state['stage']=='check_feedback'
            rows.append(dict(name=name,input=text,passed=passed,reply=result.reply,stage=result.state['stage'],raw=raw,calls=runtime.model_calls))
        except Exception as exc:rows.append(dict(name=name,input=text,passed=False,error_type=type(exc).__name__,detail=str(exc),raw=raw,calls=runtime.model_calls))
        rows[-1]['elapsed_ms']=round((time.perf_counter()-start)*1000)
    path=ROOT/'test-results'/f"goal-handoff-{'before' if args.before else 'after'}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(file=path.name,cases=[{k:r[k] for k in ('name','passed','elapsed_ms')} for r in rows],calls=sum(len(r['calls']) for r in rows),tokens=sum(c.get('usage',{}).get('total_tokens',0) or 0 for r in rows for c in r['calls'])),ensure_ascii=False))
    return 0 if all(r['passed'] for r in rows) else 1


if __name__=='__main__':raise SystemExit(main())
