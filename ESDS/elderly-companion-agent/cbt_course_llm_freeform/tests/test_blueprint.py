import copy
import unittest
import uuid
from types import SimpleNamespace

from cbt_course_llm_freeform import blueprint, boundaries, learning_check, practice_flow
from cbt_course_llm_freeform.agent import FreeformCourseAgent
from cbt_course_llm_freeform.preview import PreviewClient
from cbt_course_llm_freeform.runtime import FreeformCourseRuntime, new_course_state, course_payload
from cbt_course_llm_freeform.schemas import TeachingDecision, AgentResult
from cbt_course_llm_freeform.navigation import NavigationDecision


class Teacher:
    def __init__(self, fields): self.fields = fields
    def reply(self, history, *, context):
        latest = history[-1]
        return AgentResult(reply="谢谢您说出这些，我们按您的节奏整理。", decision=TeachingDecision(
            reply="谢谢您说出这些，我们按您的节奏整理。",
            observations=[dict(field=k, value=v, source_message_id=latest["id"]) for k,v in self.fields.items()]))


class Navigator:
    def __init__(self, decision): self.decision = NavigationDecision(**decision)
    def navigate(self, history, *, context): return SimpleNamespace(decision=self.decision, completion=None)


def apply(state, text="", fields=None, action="chat", agent=None, mid="u"):
    return FreeformCourseRuntime(agent=agent or Teacher(fields or {})).process(state,
        [{"id": mid, "role": "learner", "content": text or action}], action=action)


def ready_state():
    state = new_course_state("lesson-1", reflection_policy="none")
    state["stage"] = "practice"
    text = "事情：朋友没回消息；想法：可能在忙；相信程度0分；心情：失落；情绪强度0分；做法：继续散步"
    fields = dict(situation="朋友没回消息", thought="可能在忙", thought_belief="相信程度0分", emotion="失落", emotion_intensity="情绪强度0分", behavior="继续散步")
    return apply(state, text, fields).state


class BlueprintTests(unittest.TestCase):
    def test_normal_course_ends_with_sourced_ratings_relation_and_two_goals(self):
        runtime = FreeformCourseRuntime(agent=FreeformCourseAgent(client=PreviewClient()))
        state = new_course_state("lesson-1", reflection_policy="none")
        history=[]
        def turn(text="", action="chat"):
            nonlocal state
            history.append({"id": uuid.uuid4().hex, "role": "learner", "content": text or action})
            result=runtime.process(state, history, action=action);state=result.state
            history.append({"id":uuid.uuid4().hex,"role":"agent","content":result.reply})
            return result
        turn(action="skip_checkin")
        turn("事情：朋友没回消息；想法：他可能在忙；心情：失落；做法：继续散步")
        self.assertEqual(practice_flow.current_field(state),"thought_belief")
        turn("0分")
        self.assertEqual(practice_flow.current_field(state),"emotion_intensity")
        turn("6分")
        self.assertEqual(state["stage"],"review")
        turn("我现在还不能确定朋友没回复的原因")
        turn(action="confirm_record")
        for text in ("有人打招呼时没想到回应", "担心对方觉得没礼貌影响关系", "紧张", "不断找话题和对方说话"):
            turn(text)
        turn(action="continue_after_check")
        turn("每周记录一次情绪；每周用四要素分析一件事")
        self.assertEqual(len(state["learning_goal_draft"]["items"]),2)
        turn(action="confirm_learning_goal")
        turn(action="accept_practice")
        turn(action="finish")
        self.assertTrue(state["completed"])
        self.assertEqual(state["confirmed_record"]["blueprint"]["ratings"]["thought_belief"]["value"],0)
        self.assertIsNotNone(state["blueprint"]["relationship"])
        self.assertTrue(state["learning_check"]["answers"][1]["prior_feedback"])

    def test_zero_is_present_and_both_ratings_are_separate(self):
        state=ready_state()
        self.assertEqual(state["stage"],"review")
        self.assertEqual(state["blueprint"]["ratings"]["thought_belief"]["value"],0)
        self.assertEqual(state["blueprint"]["ratings"]["emotion_intensity"]["value"],0)

    def test_initial_narrative_with_both_labelled_ratings_is_not_asked_again(self):
        state=new_course_state("lesson-1",reflection_policy="none");state["stage"]="learn"
        result=apply(state,"朋友没回消息，可能在忙，对这个想法的相信程度0分，失落，情绪强度6分，继续散步",
            dict(situation="朋友没回消息",thought="可能在忙",thought_belief="对这个想法的相信程度0分",emotion="失落",emotion_intensity="情绪强度6分",behavior="继续散步"))
        self.assertEqual(result.state["stage"],"review")
        self.assertEqual(result.state["blueprint"]["ratings"]["thought_belief"]["value"],0)
        self.assertIsNone(practice_flow.current_field(result.state))

    def test_case_selection_does_not_stream_an_unvalidated_next_question(self):
        class NoDraftStream(PreviewClient):
            def stream_with_metadata(self,*args,**kwargs):
                raise AssertionError("Case selection draft must not be displayed")
        state=new_course_state("lesson-1",reflection_policy="none");state["stage"]="learn"
        fragments=[]
        runtime=FreeformCourseRuntime(agent=FreeformCourseAgent(client=NoDraftStream()),on_reply=fragments.append)
        result=runtime.process(state,[dict(id="u",role="learner",content="朋友没回消息")])
        self.assertEqual(fragments,[])
        self.assertEqual(result.state["draft_record"]["situation"]["value"],"朋友没回消息")

    def test_invalid_score_does_not_clamp_or_advance(self):
        state=ready_state();state["stage"]="practice";state["blueprint"]["ratings"].pop("thought_belief")
        result=apply(state,"11分",{"thought_belief":"11分"})
        self.assertNotIn("thought_belief",result.state["blueprint"]["ratings"])
        self.assertEqual(practice_flow.current_field(result.state),"thought_belief")

    def test_unlabelled_score_cannot_fill_another_question(self):
        state=ready_state();state["stage"]="practice";state["blueprint"]["ratings"]={}
        result=apply(state,"8分",{"emotion_intensity":"8分"})
        self.assertEqual(result.state["blueprint"]["ratings"],{})

    def test_edit_thought_withdraws_its_rating_and_relation_but_not_emotion(self):
        state=ready_state()
        result=apply(state,"改成：他可能没看到",{"thought":"他可能没看到"})
        self.assertEqual(result.state["stage"],"practice")
        self.assertNotIn("thought_belief",result.state["blueprint"]["ratings"])
        self.assertIn("emotion_intensity",result.state["blueprint"]["ratings"])
        self.assertIsNone(result.state["blueprint"]["relationship"])

    def test_case_switch_clears_and_archives_ratings(self):
        state=ready_state();before=state["case_id"]
        boundaries.switch(state,"fictional")
        self.assertNotEqual(state["case_id"],before)
        self.assertEqual(state["blueprint"]["ratings"],{})
        self.assertIn("thought_belief",state["privacy"]["archived"][-1]["blueprint"]["ratings"])

    def test_fictional_material_without_scores_never_asks_for_them(self):
        state=ready_state();boundaries.switch(state,"fictional")
        result=apply(state,"活动取消，白跑一趟，失望，回家",dict(situation="活动取消",thought="白跑一趟",emotion="失望",behavior="回家"))
        self.assertEqual(result.state["stage"],"review")
        self.assertEqual(result.state["blueprint"]["ratings"],{})
        self.assertTrue(practice_flow.confirmed_ready(result.state,dict(fields=result.state["draft_record"],deferred_fields=result.state["practice_flow"]["deferred"])))

    def test_refused_score_and_one_clarification_then_leave_blank(self):
        state=ready_state();state["stage"]="practice";state["blueprint"]["ratings"]={}
        state=apply(state,"暂不评分").state
        self.assertEqual(practice_flow.current_field(state),"emotion_intensity")
        state=apply(state,"不知道").state
        self.assertEqual(state["stage"],"practice")
        state=apply(state,"还是想不起").state
        self.assertEqual(state["stage"],"review")
        self.assertEqual(state["blueprint"]["ratings"],{})

    def test_stop_probing_leaves_scores_blank_and_keeps_case(self):
        from cbt_course_llm_freeform.tests.test_stop_probing import StopClient
        state=ready_state();state["stage"]="practice";state["blueprint"]["ratings"]={}
        result=apply(state,"你为什么一直追问",agent=FreeformCourseAgent(client=StopClient()))
        self.assertEqual(result.state["case_id"],state["case_id"])
        self.assertEqual(result.state["stage"],"review")
        self.assertNotIn("？",result.reply)
        self.assertEqual(result.state["blueprint"]["ratings"],{})

    def test_goal_direction_then_concrete_and_excess_not_truncated(self):
        state=ready_state();state["stage"]="learning_goal"
        blueprint.goal_answer(state,{"id":"g1","content":"希望少焦虑"},["希望少焦虑"],"direction")
        self.assertNotIn("learning_goal_draft",state)
        blueprint.goal_answer(state,{"id":"g2","content":"每周记录一次情绪；每周散步一次"},["每周记录一次情绪","每周散步一次"])
        self.assertEqual(len(state["learning_goal_draft"]["items"]),2)
        old=copy.deepcopy(state["learning_goal_draft"])
        text="；".join(f"目标{i}" for i in range(6))
        reply=blueprint.goal_answer(state,{"id":"g3","content":text},text.split("；"))
        self.assertIn("合并",reply)
        self.assertNotIn("learning_goal_draft",state)

    def test_goal_edit_after_confirmation_requires_confirmation_and_plan_again(self):
        state=ready_state();state["stage"]="learning_goal"
        blueprint.goal_answer(state,{"id":"g","content":"每周记录一次情绪"},["每周记录一次情绪"])
        state=apply(state,action="confirm_learning_goal").state
        state=apply(state,action="accept_practice").state
        decision=dict(intent="goal",goal_items=["每周记录两次情绪"],goal_level="concrete",actions=[])
        result=apply(state,"修改目标，每周记录两次情绪",agent=Navigator(decision))
        self.assertEqual(result.state["stage"],"learning_goal")
        self.assertNotIn("learning_goal",result.state)
        self.assertEqual(result.state["practice_plan"]["status"],"undecided")

    def test_indexed_goal_edit_retains_other_item_and_original_evidence(self):
        state=ready_state();state["stage"]="learning_goal"
        blueprint.goal_answer(state,{"id":"original","content":"每周记录一次情绪；每周分析一件事"},["每周记录一次情绪","每周分析一件事"])
        state=apply(state,action="confirm_learning_goal").state
        decision=dict(intent="goal",actions=[],goal_updates=[dict(index=2,value="每周分析两件事")])
        result=apply(state,"第二项改成每周分析两件事，第一项不变",agent=Navigator(decision),mid="edit")
        items=result.state["learning_goal_draft"]["items"]
        self.assertEqual(items,[dict(value="每周记录一次情绪",source_message_id="original"),dict(value="每周分析两件事",source_message_id="edit")])
        self.assertNotIn("learning_goal",result.state)
        self.assertEqual(result.state["stage"],"learning_goal")

    def test_goal_edit_button_retains_base_and_invalid_index_is_atomic(self):
        state=ready_state();state["stage"]="learning_goal"
        blueprint.goal_answer(state,{"id":"original","content":"每周分析一件事"},["每周分析一件事"])
        state=apply(state,action="confirm_learning_goal").state
        bad=apply(state,"第五项改为每天记录",agent=Navigator(dict(intent="goal",actions=[],goal_updates=[dict(index=5,value="每天记录")])))
        self.assertEqual(bad.trace["navigation_event"]["status"],"failed")
        self.assertEqual(bad.state["stage"],"plan")
        state=apply(state,action="edit_learning_goal").state
        result=apply(state,"第一项改为每天记录",agent=Navigator(dict(intent="goal",actions=[],goal_updates=[dict(index=1,value="每天记录")])))
        self.assertEqual(result.state["learning_goal_draft"]["items"][0]["value"],"每天记录")

    def test_clarification_cannot_claim_goal_was_changed_without_structured_update(self):
        state=ready_state();state["stage"]="learning_goal"
        blueprint.goal_answer(state,{"id":"g","content":"每周分析一件事"},["每周分析一件事"])
        state=apply(state,action="confirm_learning_goal").state
        result=apply(state,"第一项改为每天记录",agent=Navigator(dict(intent="clarify",actions=[],reply="已修改目标，请确认")))
        self.assertEqual(result.trace["navigation_event"]["status"],"failed")
        self.assertEqual(result.state["stage"],"plan")
        self.assertNotIn("已修改",result.reply)

    def test_unfaithful_goal_rejected_without_state_change(self):
        state=ready_state();state["stage"]="learning_goal"
        result=apply(state,"少担心",agent=Navigator(dict(intent="goal",actions=[],goal_items=["每天散步"])))
        self.assertEqual(result.trace["navigation_event"]["status"],"failed")
        self.assertNotIn("learning_goal_draft",result.state)

    def test_other_lessons_do_not_enable_blueprint_or_accept_scores(self):
        for number in range(2,9):
            state=new_course_state(f"lesson-{number}",reflection_policy="none")
            self.assertIsNone(course_payload(state)["blueprint"])
        state=new_course_state("lesson-2",reflection_policy="none");state["stage"]="practice"
        with self.assertRaises(RuntimeError):apply(state,"8分",{"thought_belief":"8分"})

    def test_rating_source_cannot_be_fabricated(self):
        state=ready_state();state["stage"]="practice"
        with self.assertRaises(RuntimeError):apply(state,"没有评分",{"thought_belief":"8分"})

    def test_multiple_cases_require_selection_and_keep_both_source_messages(self):
        class Cases(Teacher):
            def reply(self, history, *, context):
                return AgentResult(reply="先选一件",decision=TeachingDecision(reply="先选一件",case_options=["朋友没回消息","活动取消"]))
        state=new_course_state("lesson-1",reflection_policy="none");state["stage"]="learn"
        state=apply(state,"朋友没回消息；活动取消",agent=Cases({}),mid="options").state
        self.assertEqual(state["draft_record"],{})
        state=apply(state,"第二件",mid="selected").state
        self.assertEqual(state["draft_record"]["situation"]["value"],"活动取消")
        self.assertEqual(state["draft_record"]["situation"]["source_message_id"],"options")
        self.assertEqual(state["draft_record"]["situation"]["selection_message_id"],"selected")

    def test_model_reported_refusal_precedes_case_options_when_rule_misses_it(self):
        class Refusal(Teacher):
            def reply(self, history, *, context):
                latest=history[-1]
                note=dict(verdict="feedback",source_message_id=latest["id"],quote=latest["content"],
                    observation="本轮不愿展开",hypothesis="可能不愿谈本次个人事情",alternative_explanation="也可能只是希望换一种材料",
                    scope="lesson",reply_length="short",follow_up="reduce",personal_intent="refuse_personal",
                    reply="可以，这件事先不谈。以后课程也用虚构例子、不主动问个人经历，可以吗？")
                return AgentResult(reply=note["reply"],decision=TeachingDecision(reply=note["reply"],interaction=note,case_options=[latest["content"]]))
        state=new_course_state("lesson-1",reflection_policy="none");state["stage"]="learn"
        result=apply(state,"今天不展开这一段",agent=Refusal({}))
        self.assertTrue(boundaries.fictional(result.state))
        self.assertTrue(result.state["privacy"]["pending"])
        self.assertEqual(result.state["blueprint"]["case_options"],[])

    def test_review_correction_invalidates_only_related_rating_even_if_new_score_first(self):
        state=ready_state()
        result=apply(state,"情绪强度7分，心情是紧张",dict(emotion_intensity="情绪强度7分",emotion="紧张"))
        self.assertEqual(result.state["blueprint"]["ratings"]["emotion_intensity"]["value"],7)
        self.assertEqual(result.state["stage"],"review")

    def test_two_questions_give_immediate_feedback_and_log_previous_exposure(self):
        state=ready_state();state=apply(state,action="confirm_record").state
        result=apply(state,"只是情绪",agent=FreeformCourseAgent(client=PreviewClient()))
        self.assertIn("参考含义",result.reply)
        self.assertFalse(result.state["learning_check"]["answers"][0]["prior_feedback"])
        result=apply(result.state,"担心影响关系",agent=FreeformCourseAgent(client=PreviewClient()))
        self.assertTrue(result.state["learning_check"]["answers"][1]["prior_feedback"])


class BlueprintPersistenceTests(unittest.TestCase):
    def test_restart_goals_and_scores_persist_but_only_live_confirmed_goals_cross(self):
        import tempfile
        from pathlib import Path
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from webapp.database import Base
        from webapp.models import Participant, Conversation, Message
        from webapp.security import hash_secret, decrypt_json
        from cbt_course_llm_freeform.services import create_or_resume_course, process_course_turn, AGENT_VERSION
        from cbt_course_llm_freeform.memory import offer_previous_summary
        with tempfile.TemporaryDirectory() as folder:
            url="sqlite:///"+(Path(folder)/"blueprint.db").as_posix()
            engine=create_engine(url);Base.metadata.create_all(engine)
            with sessionmaker(bind=engine,expire_on_commit=False)() as db:
                person=Participant(label=uuid.uuid4().hex,invite_hash=hash_secret("synthetic-blueprint"));db.add(person);db.commit()
                conversation,_=create_or_resume_course(db,participant_id=person.id,lesson_id="lesson-1")
                def send(text="",action="chat",key=None):
                    return process_course_turn(db,conversation,content=text,action=action,idempotency_key=key or uuid.uuid4().hex,
                        runtime_factory=lambda:FreeformCourseRuntime(agent=FreeformCourseAgent(client=PreviewClient())))
                send(action="skip_checkin");send("朋友没回消息")
                send("想法：他可能在忙；心情：失落；做法：继续散步")
                first=send("0分",key="score-zero")
                self.assertTrue(send("0分",key="score-zero")["deduplicated"])
                send("6分");send("我还不能确定原因")
                send(action="confirm_record")
                for _ in range(4):send(action="skip_check_question")
                send(action="continue_after_check")
                send("每周记录一次情绪；每周分析一件事")
                send(action="confirm_learning_goal");send(action="decline_practice");send(action="finish")
                state=decrypt_json(conversation.agent_state_encrypted)
                self.assertEqual(state["blueprint"]["ratings"]["thought_belief"]["value"],0)
                confirmation=state["learning_goal"]["confirmation_message_id"]
                participant_id,conversation_id=person.id,conversation.id
            engine.dispose()
            engine=create_engine(url)
            with sessionmaker(bind=engine,expire_on_commit=False)() as db:
                state=decrypt_json(db.get(Conversation,conversation_id).agent_state_encrypted)
                self.assertEqual(state["blueprint"]["ratings"]["emotion_intensity"]["value"],6)
                summary=offer_previous_summary(db,participant_id,AGENT_VERSION,"lesson-2")["summary"]
                self.assertEqual(len(summary["course_goals"]),2)
                self.assertNotIn("ratings",summary)
                self.assertNotIn("blueprint",summary)
                db.delete(db.get(Message,confirmation));db.commit()
                self.assertEqual(offer_previous_summary(db,participant_id,AGENT_VERSION,"lesson-2")["summary"]["course_goals"],[])
                self.assertEqual(offer_previous_summary(db,"foreign",AGENT_VERSION,"lesson-2")["status"],"unavailable")
            engine.dispose()
