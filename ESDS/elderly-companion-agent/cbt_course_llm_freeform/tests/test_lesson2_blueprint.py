from __future__ import annotations

import copy
import json
import unittest
import uuid
from unittest.mock import patch

from cbt_course_llm_freeform import boundaries, lesson2_flow as flow
from cbt_course_llm_freeform.agent import FreeformCourseAgent
from cbt_course_llm_freeform.preview import PreviewClient
from cbt_course_llm_freeform.runtime import FreeformCourseRuntime, new_course_state, course_payload
from cbt_course_llm_freeform.tests.lesson2_helpers import prepare
from cbt_course_llm_freeform.tests.test_personal_boundary import BoundaryClient


def turn(state, text="", action="chat", client=None, message_id=None):
    return FreeformCourseRuntime(agent=FreeformCourseAgent(client=client or PreviewClient())).process(
        state, [{"id": message_id or uuid.uuid4().hex, "role":"learner", "content":text or action}], action=action)


class Script(PreviewClient):
    def __init__(self, **output): self.output=output
    def complete_with_metadata(self, messages, **kwargs):
        if "InteractionReflection" in messages[0]["content"] and "values" not in self.output and self.output.get("interaction") and "判读" in messages[0]["content"]:
            from daily_agent.azure_chat_client import ChatCompletionResult
            return ChatCompletionResult(text=json.dumps(self.output["interaction"],ensure_ascii=False),model="script",finish_reason="stop")
        return super().complete_with_metadata(messages,**kwargs)
    def _lesson2(self, context, latest):
        observations=[dict(field=key,value=value,source_message_id=latest["id"]) for key,value in self.output.get("values",{}).items()]
        return {"reply":"先保留您的说法。", **{k:v for k,v in self.output.items() if k!="values"},"observations":observations}


class Lesson2BlueprintTests(unittest.TestCase):
    def personal(self):
        state=new_course_state("lesson-2"); flow.go(state,"personal"); return state

    def test_normal_path_keeps_actors_quiz_and_personal_rating_separate(self):
        state=new_course_state("lesson-2")
        def send(text="",action="chat"):
            nonlocal state
            result=turn(state,text,action);state=result.state;return result
        prepare(send)
        self.assertEqual(state["lesson2_flow"]["step"],"model")
        f=state["lesson2_flow"]
        self.assertEqual(f["rain"]["source_kind"],"imagined_self")
        self.assertEqual(f["contrast"]["source_kind"],"preset_character")
        self.assertEqual(state["draft_record"]["thought"]["value"],"安排泡汤了")
        self.assertEqual(f["rating"]["value"],6)
        self.assertEqual(len(f["quiz"]["answers"]),3)
        self.assertTrue(f["quiz"]["answers"][1]["prior_feedback"])
        send(action="confirm_record");send(action="decline_practice");send(action="finish")
        self.assertTrue(state["completed"])
        self.assertEqual(state["artifact"]["schema_version"],"course-artifact/2")
        self.assertEqual(state["reflection"]["status"],"pending")
        self.assertEqual(state["learning_result"]["application_status"],"not_measured")

    def test_rain_mixed_emotions_are_not_forced_into_positive_negative(self):
        state=new_course_state("lesson-2");flow.go(state,"rain")
        result=turn(state,"失望但也放松，可以在家休息",client=Script(values={"emotion":"失望但也放松","thought":"可以在家休息"},emotion_tone="mixed"))
        self.assertEqual(result.state["lesson2_flow"]["step"],"contrast")
        self.assertEqual(result.state["lesson2_flow"]["rain"]["tone"],"mixed")
        self.assertEqual(result.state["draft_record"],{})
        self.assertIsNone(result.state["lesson2_flow"]["rating"])

    def test_zero_rating_and_emotion_edit_invalidation(self):
        state=self.personal()
        state=turn(state,"情境：等车；想法：可能晚到；情绪：担心；情绪强度：0分").state
        self.assertEqual(state["lesson2_flow"]["rating"]["value"],0)
        state=turn(state,"改成平静",client=Script(values={"emotion":"平静"})).state
        self.assertIsNone(state["lesson2_flow"]["rating"])
        self.assertIsNone(state["confirmed_record"])
        self.assertEqual(state["lesson2_flow"]["step"],"personal")

    def test_natural_rating_prefix_and_thought_edit_do_not_change_emotion(self):
        state=turn(self.personal(),"情境：等车；想法：可能晚到；情绪：担心").state
        state=turn(state,"担心大概6分",client=Script(values={"emotion_intensity":"担心大概6分"},rating_target="担心")).state
        self.assertEqual(state["lesson2_flow"]["rating"]["value"],6)
        state=turn(state,"改成应该赶得上",client=Script(values={"thought":"应该赶得上"})).state
        self.assertEqual(state["lesson2_flow"]["rating"]["value"],6)
        self.assertEqual(state["draft_record"]["emotion"]["value"],"担心")

    def test_multiple_emotion_spans_preserve_both_in_original_enclosing_quote(self):
        state=new_course_state("lesson-2");flow.go(state,"rain")
        class Separate(PreviewClient):
            def _lesson2(self,context,latest):
                return {"reply":"这两种感受可以并存。","emotion_tone":"mixed","observations":[{"field":"emotion","value":value,"source_message_id":latest["id"]} for value in ("失望","放松")]}
        result=turn(state,"有点失望，但也放松",client=Separate())
        self.assertEqual(result.state["lesson2_flow"]["rain"]["fields"]["emotion"]["value"],"失望，但也放松")
        self.assertEqual(result.state["lesson2_flow"]["events"][-1]["fragments"],["失望","放松"])

    def test_split_mood_description_and_score_keep_original_span(self):
        class SplitMood(PreviewClient):
            def _lesson2(self,context,latest):
                return {"reply":"谢谢您说明。","observations":[{"field":"mood","value":value,"source_message_id":latest["id"]} for value in ("平稳","6分")]}
        result=turn(new_course_state("lesson-2"),"这周平稳，大概6分",client=SplitMood())
        self.assertEqual(result.state["mood"]["value"],"这周平稳，大概6分")
        self.assertEqual(result.state["lesson2_flow"]["step"],"homework")

    def test_out_of_range_and_mixed_rating_without_target_are_not_clamped(self):
        state=self.personal();state=turn(state,"情境：等车；想法：可能晚到；情绪：担心").state
        result=turn(state,"12分",client=Script(values={"emotion_intensity":"12分"}))
        self.assertIsNone(result.state["lesson2_flow"]["rating"])
        state["lesson2_flow"]["personal_tone"]="mixed"
        result=turn(state,"6分",client=Script(values={"emotion_intensity":"6分"}))
        self.assertIsNone(result.state["lesson2_flow"]["rating"])

    def test_explicit_refusal_once_and_fictional_case_never_gets_personal_rating(self):
        state=turn(self.personal(),"不想谈自己的事情",client=BoundaryClient(["refuse_personal"])).state
        self.assertTrue(state["privacy"]["pending"])
        state=turn(state,"只是这次不谈",client=BoundaryClient(["local_only"])).state
        self.assertIsNone(state["privacy"]["pending"])
        self.assertTrue(boundaries.fictional(state))
        state=turn(state,"情境：活动取消；想法：白跑一趟了；情绪：失望").state
        self.assertEqual(state["lesson2_flow"]["step"],"model")
        self.assertIsNone(state["lesson2_flow"]["rating"])
        self.assertTrue(all(x["source_kind"]=="fictional" for x in state["draft_record"].values()))

    def test_different_story_cannot_enter_current_case(self):
        state=self.personal();boundaries.switch(state,"fictional")
        result=turn(state,"我去上学",client=Script(values={"situation":"我去上学"},practice_origin="personal_account"))
        self.assertEqual(result.state["draft_record"],{})
        self.assertEqual(result.trace["action"],"lesson2_source_mismatch")
        state=self.personal()
        state["draft_record"]={"situation":{"value":"昨天等车","source_message_id":"old","case_id":state["case_id"]}}
        result=turn(state,"另一件事是上学",client=Script(values={"situation":"上学"},practice_origin="different_case"))
        self.assertEqual(result.state["draft_record"],state["draft_record"])
        self.assertEqual(result.state["case_id"],state["case_id"])

    def test_missing_field_gets_only_one_clarification_then_defers(self):
        state=self.personal()
        state=turn(state,"不确定",client=Script()).state
        self.assertEqual(flow.focus(state),"situation")
        state=turn(state,"还是不确定",client=Script()).state
        self.assertIn("situation",state["lesson2_flow"]["deferred"])
        self.assertEqual(flow.focus(state),"thought")

    def test_reuse_only_situation_not_previous_thought_or_emotion(self):
        state=self.personal();state["carryover"]={"status":"accepted","summary":{"artifact_id":"old-artifact","record":{k:{"value":"旧"+k} for k in flow.TRIAD}}}
        state=turn(state,action="reuse_case").state
        self.assertEqual(set(state["draft_record"]),{"situation"})
        self.assertEqual(flow.focus(state),"thought")
        self.assertEqual(state["draft_record"]["situation"]["source_artifact_id"],"old-artifact")

    def test_quiz_help_skip_feedback_and_burden_are_not_wrong_answers(self):
        state=new_course_state("lesson-2");flow.go(state,"recall")
        state=turn(state,action="request_check_hint").state
        state=turn(state,"想法").state
        self.assertTrue(state["lesson2_flow"]["quiz"]["answers"][0]["assisted"])
        note={"verdict":"feedback","source_message_id":"u","quote":"剩下的题不做了","observation":"拒绝剩余题","hypothesis":"可能题量负担","alternative_explanation":"也可能临时想休息","scope":"lesson","reply_length":"short","follow_up":"standard","reply":"好的，剩余题先不做。","task_action":"stop_check"}
        state=turn(state,"剩下的题不做了",message_id="u",client=Script(interaction=note)).state
        self.assertEqual([x["verdict"] for x in state["lesson2_flow"]["quiz"]["answers"]][1:],["not_observed"]*2)
        self.assertFalse(state["completed"])

    def test_wrong_source_is_atomic_and_reading_payload_is_pure(self):
        state=self.personal();old=copy.deepcopy(state)
        with self.assertRaises(ValueError): turn(state,"等车",client=Script(values={"situation":"并不存在"}))
        self.assertEqual(state,old)
        boundaries.switch(state,"fictional");old=copy.deepcopy(state)
        course_payload(state);course_payload(state)
        self.assertEqual(state,old)

    def test_pause_resume_and_ambiguous_continue_do_not_confirm(self):
        state=self.personal()
        state=turn(state,action="pause").state
        state=turn(state,action="resume").state
        result=turn(state,"完成了",client=Script(intent="continue"))
        self.assertFalse(result.state["completed"])
        self.assertIsNone(result.state["confirmed_record"])
        self.assertEqual(result.state["lesson2_flow"]["step"],"personal")
        for step in ("contrast","rain_insight"):
            state=new_course_state("lesson-2");flow.go(state,step)
            result=turn(state,"这个联系没看懂",client=Script(intent="help"))
            self.assertEqual(result.state["lesson2_flow"]["step"],step)

    def test_judge_failure_pauses_without_creating_memory(self):
        result=turn(self.personal(),"不想说自己的事情",client=BoundaryClient(fail=True))
        self.assertTrue(result.state["paused"])
        self.assertEqual(result.trace["interaction_event"]["status"],"failed")
        self.assertIsNone(result.state.get("disclosure_boundary"))

    def test_local_stop_cannot_escalate_to_whole_course_pause(self):
        text="为什么一直追问，我已经说过这些了"
        note={"verdict":"feedback","source_message_id":"u","quote":text,"observation":"抱怨追问","hypothesis":"可能感到重复","alternative_explanation":"也可能没看清当前项","scope":"lesson","reply_length":"short","follow_up":"stop","reply":"抱歉，不再追问这件事。","response_type":"review_current_case","task_action":"pause"}
        original=self.personal();case=original["case_id"]
        result=turn(original,text,client=Script(interaction=note),message_id="u")
        self.assertEqual(result.state["lesson2_flow"]["step"],"model")
        self.assertFalse(result.state["paused"])
        self.assertEqual(result.state["case_id"],case)
        memory=result.trace["interaction_event"]["memory"]
        self.assertEqual(memory["proposed_task_action"],"pause")
        self.assertEqual(memory["applied_action"],"continue")


class Lesson2PersistenceTests(unittest.TestCase):
    def setUp(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from webapp.database import Base
        from webapp.models import Participant
        from webapp.security import hash_secret
        from cbt_course_llm_freeform.services import create_or_resume_course
        self.engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(self.engine)
        self.Session=sessionmaker(bind=self.engine,expire_on_commit=False);self.db=self.Session()
        self.person=Participant(label=uuid.uuid4().hex,invite_hash=hash_secret("offline"));self.db.add(self.person);self.db.commit()
        self.course=create_or_resume_course(self.db,participant_id=self.person.id,lesson_id="lesson-2")[0]

    def tearDown(self):self.db.close();self.engine.dispose()

    def send(self,text="",action="chat",key=None):
        from cbt_course_llm_freeform.services import process_course_turn
        return process_course_turn(self.db,self.course,content=text,action=action,idempotency_key=key or uuid.uuid4().hex,
            runtime_factory=lambda:FreeformCourseRuntime(agent=FreeformCourseAgent(client=PreviewClient())))

    def test_new_state_survives_reopen_deduplicates_and_old_version_is_read_only(self):
        from cbt_course_llm_freeform.services import course_conversation_payload,process_course_turn
        from webapp.models import Conversation,Message
        from sqlalchemy import select
        from webapp.security import decrypt_json
        result=self.send("最近六分",key="same")
        replay=self.send("最近六分",key="same")
        self.assertTrue(replay["deduplicated"])
        self.assertEqual(result["reply"],replay["reply"])
        self.assertEqual(len(self.db.scalars(select(Message).where(Message.conversation_id==self.course.id)).all()),3)
        with self.Session() as other:
            restored=other.get(Conversation,self.course.id)
            self.assertEqual(decrypt_json(restored.agent_state_encrypted)["lesson2_flow"]["step"],"homework")
            for old_version in ("5.1-interaction-memory", "6.1-xmind-flow"):
                restored.lesson_version=old_version;other.commit()
                self.assertTrue(course_conversation_payload(restored)["read_only"])
                with self.assertRaises(ValueError):process_course_turn(other,restored,content="继续",idempotency_key="old")

    def test_completed_reflection_receives_sources_and_does_not_apply_hypotheses(self):
        from cbt_course_llm_freeform.reflection import generate_course_reflection
        from webapp.security import decrypt_json
        from daily_agent.azure_chat_client import ChatCompletionResult
        prepare(self.send);self.send(action="confirm_record");self.send(action="decline_practice");self.send(action="finish")
        class CheckContext:
            def complete_with_metadata(inner,messages,**kwargs):
                data=json.loads(messages[-1]["content"])
                self.assertEqual(data["lesson2_flow"]["rain"]["source_kind"],"imagined_self")
                self.assertEqual(data["lesson2_flow"]["contrast"]["source_kind"],"preset_character")
                self.assertEqual(data["lesson2_flow"]["homework"]["status"],"not_attempted")
                self.assertTrue(data["learning_result"]["quiz"]["answers"][1]["prior_feedback"])
                return ChatCompletionResult(text='{"observations":[],"suggestions":[],"hypotheses":[]}',finish_reason="stop")
        generate_course_reflection(self.course.id,session_factory=self.Session,client=CheckContext())
        self.db.refresh(self.course)
        note=decrypt_json(self.course.agent_state_encrypted)["reflection"]
        self.assertEqual(note["status"],"ready");self.assertFalse(note["applied"])
