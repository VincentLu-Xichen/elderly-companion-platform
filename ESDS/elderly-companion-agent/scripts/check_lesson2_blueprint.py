"""Bounded synthetic real-model walkthrough, with persisted audit and reflection.

Uses a temporary SQLite file; never reads or edits real participant records.
"""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import uuid


def main():
    project=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(project))
    from dotenv import load_dotenv
    load_dotenv(project/".env",encoding="utf-8-sig")
    os.environ["CBT_COURSE_PROVIDER"]="deepseek"
    os.environ["CBT_REFLECTION_POLICY"]="none"
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker
    from webapp.database import Base
    from webapp.models import Participant, TurnEvent
    from webapp.security import decrypt_json, encrypt_json, hash_secret
    from cbt_course_llm_freeform.agent import FreeformCourseAgent
    from cbt_course_llm_freeform import lesson2_flow as flow
    from cbt_course_llm_freeform.runtime import FreeformCourseRuntime
    from cbt_course_llm_freeform.services import create_or_resume_course, process_course_turn
    from cbt_course_llm_freeform.reflection import generate_course_reflection
    rows=[]; raw=[]; calls=[]
    class RecordingClient:
        def __init__(self):self.client=FreeformCourseAgent._client_from_env()
        def complete_with_metadata(self,messages,**kwargs):
            response=self.client.complete_with_metadata(messages,**kwargs)
            raw.append({"marker":messages[0]["content"][:40],"text":response.text})
            return response
    def factory():return FreeformCourseRuntime(agent=FreeformCourseAgent(client=RecordingClient()))
    started=time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="lesson2-real-check-") as tmp:
        engine=create_engine("sqlite:///"+(Path(tmp)/"test.db").as_posix());Base.metadata.create_all(engine)
        Session=sessionmaker(bind=engine,expire_on_commit=False)
        with Session() as db:
            person=Participant(label="synthetic-lesson2",invite_hash=hash_secret(uuid.uuid4().hex));db.add(person);db.commit()
            course=create_or_resume_course(db,participant_id=person.id,lesson_id="lesson-2")[0]
            def send(text="",action="chat"):
                result=process_course_turn(db,course,content=text,action=action,idempotency_key=uuid.uuid4().hex,runtime_factory=factory)
                state=decrypt_json(course.agent_state_encrypted)
                rows.append({"input":text or action,"step":state["lesson2_flow"]["step"],"reply":result["reply"],"paused":state["paused"]})
                print(json.dumps({"case":"normal","step":rows[-1]["step"],"paused":rows[-1]["paused"]}),flush=True)
                return state
            try:
                send("最近一周整体还算平稳，我给6分")
                send("课后试着记录过一次，但情绪和想法有时写混了")
                for text in ("认知，是对自己和同学的判断","情绪","行为"):
                    send(text)
                send(action="continue_lesson2")
                send("我会有点失望，但也觉得放松")
                send("郊游泡汤了，不过可以在家休息")
                send(action="continue_lesson2")
                send("同一件事可以有不同解释，感受也可能不同")
                send("昨天朋友没回消息，我想到他可能很忙，但还是有些担心")
                state=send("担心大概6分")
                if state["lesson2_flow"]["step"]!="model":raise AssertionError("Normal path did not reach model review")
                send("我觉得这几项可能有关，但还不能确定是谁影响谁")
                send(action="confirm_record");send(action="decline_practice");state=send(action="finish")
                if not state["completed"]:raise AssertionError("Not completed")
                db.expunge_all()
                generate_course_reflection(course.id,session_factory=Session,client=RecordingClient())
                from webapp.models import Conversation
                state=decrypt_json(db.get(Conversation,course.id).agent_state_encrypted)
                rows.append({"case":"post_lesson","passed":state["reflection"]["status"]=="ready","reflection":state["reflection"]})
            except Exception as exc:
                rows.append({"case":"normal","passed":False,"error_type":type(exc).__name__,"error":str(exc)[:180]})
            # New conversations are separately owned synthetic participants.
            for case,text,expect in (("privacy","我不想谈自己的事情","pending"),("complaint","为什么一直追问，我已经说过这些了","model"),("burden","我不想做这么多题目","quiz_stopped"),("rain_combined","会有点失望，但也放松，想到可以在家休息。","contrast")):
                p=Participant(label="synthetic-"+case,invite_hash=hash_secret(uuid.uuid4().hex));db.add(p);db.commit()
                c=create_or_resume_course(db,participant_id=p.id,lesson_id="lesson-2")[0]
                state=decrypt_json(c.agent_state_encrypted);flow.go(state,"recall" if case=="burden" else "rain" if case=="rain_combined" else "personal")
                if case=="complaint":state["draft_record"]={"situation":{"value":"等车迟到了","source_message_id":"synthetic-seed","source_kind":"personal","case_id":state["case_id"]}}
                original_case=state["case_id"];c.agent_state_encrypted=encrypt_json(state);db.commit()
                try:
                    response=process_course_turn(db,c,content=text,idempotency_key=uuid.uuid4().hex,runtime_factory=factory)
                    state=decrypt_json(c.agent_state_encrypted)
                    if expect=="pending":passed=bool(state["privacy"]["pending"])
                    elif expect=="model":passed=state["lesson2_flow"]["step"]=="model" and state["case_id"]==original_case
                    elif expect=="contrast":passed=state["lesson2_flow"]["step"]=="contrast" and set(state["lesson2_flow"]["rain"]["fields"])=={"emotion","thought"} and not state["draft_record"]
                    else:passed=state["lesson2_flow"]["quiz"]["index"]==3
                    rows.append({"case":case,"passed":passed,"reply":response["reply"],"flow":state["lesson2_flow"]})
                    if case=="privacy" and passed:
                        response=process_course_turn(db,c,content="只是这次不说，以后再看",idempotency_key=uuid.uuid4().hex,runtime_factory=factory)
                        state=decrypt_json(c.agent_state_encrypted)
                        rows.append({"case":"local_confirmation","passed":not state["privacy"]["pending"] and not state.get("disclosure_boundary"),"reply":response["reply"]})
                except Exception as exc:rows.append({"case":case,"passed":False,"error_type":type(exc).__name__,"error":str(exc)[:180]})
            for event in db.scalars(select(TurnEvent)):
                if event.trace_encrypted:calls.extend(decrypt_json(event.trace_encrypted).get("model_calls",[]))
                if event.idempotency_key.startswith("reflection:"):
                    calls.append({"phase":"post_lesson_reflection","status":event.status,"usage":{"total_tokens":event.total_tokens or 0},"latency_ms":event.latency_ms})
        engine.dispose()
    output={"synthetic":True,"rows":rows,"calls":calls,"raw_outputs":raw,"usage":{"calls":len(calls),"tokens":sum(c.get("usage",{}).get("total_tokens",0) for c in calls),"wall_ms":round((time.perf_counter()-started)*1000)}}
    path=project/"test-results/lesson2-real-blueprint.json";path.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding="utf-8")
    checks=[r for r in rows if "passed" in r]
    print(json.dumps({"checks":[{"case":r["case"],"passed":r["passed"]} for r in checks],"usage":output["usage"]}),flush=True)
    return int(not checks or not all(r["passed"] for r in checks))


if __name__=="__main__":raise SystemExit(main())
