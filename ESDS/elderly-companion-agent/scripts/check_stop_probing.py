"""Bounded real-DeepSeek checks with synthetic histories only."""
import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv


def main():
    project=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(project))
    load_dotenv(project/'.env',encoding='utf-8-sig')
    os.environ['CBT_COURSE_PROVIDER']='deepseek'
    from cbt_course_llm_freeform.runtime import FreeformCourseRuntime,new_course_state
    from cbt_course_llm_freeform import boundaries
    cases=[('why_probing','你为什么要一直追问我，我三个要素都说了'),
           ('angry','你烦不烦，别一直追问了'),
           ('length_only','你的解释太长了，简短一点'),
           ('negation','我不是嫌你一直追问，我还愿意继续'),
           ('privacy','我不想谈自己的事情'),
           ('other_story','我昨天在图书馆看书时听到窗外有人唱歌')]
    rows=[]
    for name,text in cases:
        state=new_course_state('lesson-1',reflection_policy='none');state['stage']='practice'
        if name=='other_story':boundaries.switch(state,'fictional')
        else:
            for key,value in [('situation','散步时邻居匆匆走过'),('thought','可能打扰了他'),('emotion','失落')]:
                state['draft_record'][key]={'value':value,'source_message_id':'prior','source_kind':'personal'}
        original=state['case_id']
        result=FreeformCourseRuntime().process(state,[{'id':'prior','role':'learner','content':'散步时邻居匆匆走过，我想可能打扰了他，心里失落。'},
            {'id':'guide','role':'agent','content':'您当时做了什么？' if name!='other_story' else '请辨认小陈案例中发生了什么。'},
            {'id':name,'role':'learner','content':text}])
        event=result.trace.get('interaction_event') or {};action=result.trace.get('action')
        if name in {'why_probing','angry'}:
            passed=(action=='interaction_feedback' and result.state['stage']=='review' and result.state['case_id']==original
                and not boundaries.fictional(result.state) and '？' not in result.reply and '抱歉' in result.reply)
        elif name in {'length_only','negation'}:
            passed=result.state['stage']=='practice' and result.state['case_id']==original and not boundaries.blocked(result.state)
        elif name=='privacy':passed=bool(result.state['privacy']['pending']) and boundaries.fictional(result.state)
        else:passed=action=='case_source_mismatch' and result.state['draft_record']=={}
        row={'case':name,'passed':passed,'reply':result.reply,'action':action,'stage':result.state['stage'],
             'model_calls':result.trace['model_calls'],'interaction_event':event,'practice_source':boundaries.source(result.state)}
        rows.append(row);print(json.dumps({k:row[k] for k in ('case','passed','action','stage','reply')},ensure_ascii=True),flush=True)
    (project/'test-results/stop-probing-deepseek.json').write_text(json.dumps({'synthetic':True,'cases':rows},ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if all(r['passed'] for r in rows) else 1


if __name__=='__main__':raise SystemExit(main())
