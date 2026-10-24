import copy
import unittest
import uuid

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from cbt_course_llm_freeform import teacher_flow, lesson2_flow
from cbt_course_llm_freeform.runtime import FreeformCourseRuntime, new_course_state, course_payload
from cbt_course_llm_freeform.homework import DiaryCreate, save, entries
from cbt_course_llm_freeform.services import create_or_resume_course, get_owned_course
from cbt_course_llm_freeform.tests.test_blueprint import apply
from cbt_course_llm_freeform.tests.test_lesson2_blueprint import Script, turn
from webapp.database import Base
from webapp.models import Participant, CourseHomeworkEntry, TurnEvent
from webapp.security import encrypt_json, decrypt_json


class TeacherFlowTests(unittest.TestCase):
    def test_relationship_invitation_does_not_loop_or_imply_confirmation(self):
        from cbt_course_llm_freeform.tests.test_blueprint import ready_state
        state = ready_state()
        from cbt_course_llm_freeform import blueprint
        self.assertNotIn("有没有新的看法", blueprint.review_text(state))
        original = copy.deepcopy(state["draft_record"])
        for text in ("没有了", "我说没有", "先核对记录吧"):
            result = apply(state, text)
            self.assertNotIn("有没有新的看法", result.reply)
            self.assertEqual(result.reply, "谢谢您说出这些，我们按您的节奏整理。")
            self.assertIsNone(result.state["confirmed_record"])
            self.assertIsNone(result.state["blueprint"]["relationship"])
            self.assertEqual(result.state["draft_record"], original)
            state = result.state
        paused = apply(state, action="pause").state
        resumed = apply(paused, action="resume")
        self.assertNotIn("有没有新的看法", resumed.reply)
        self.assertIsNone(resumed.state["confirmed_record"])

    def test_overview_then_score_are_explicit_and_do_not_call_model(self):
        state=new_course_state("lesson-1")
        self.assertTrue(course_payload(state)["teacher_flow"]["overview_pending"])
        state=apply(state,action="start_mood_check").state
        self.assertIn("1—10",teacher_flow.MOOD_QUESTION)
        result=apply(state,"上周6分")
        self.assertEqual(result.state["stage"],"learn")
        self.assertEqual(result.state["teacher_flow"]["weekly_mood"]["value"],6)
        self.assertFalse(result.trace["model_called"])
        self.assertEqual(result.state["blueprint"]["ratings"],{})

    def test_all_score_bands_and_boundary_values_in_both_lessons(self):
        for lesson in ("lesson-1","lesson-2"):
            for number,band in [(1,"low"),(3,"low"),(4,"middle"),(6,"middle"),(7,"high"),(10,"high")]:
                with self.subTest(lesson=lesson,number=number):
                    result=apply(new_course_state(lesson),f"{number}分")
                    note=result.state["teacher_flow"]["weekly_mood"]
                    self.assertEqual(note["band"],band)
                    self.assertEqual(note["quote"],f"{number}分")
                    self.assertNotIn("没有发生",result.reply)

    def test_no_guess_clamp_conflicting_or_wrong_target_scores(self):
        for text in ("还好", "0分", "11分", "不是6分", "3分还是6分", "今天6分", "情绪强度6分"):
            result=apply(new_course_state("lesson-2"),text)
            self.assertEqual(result.state["lesson2_flow"]["step"],"check_in",text)
            self.assertEqual(result.state["teacher_flow"]["weekly_mood"]["status"],"pending")

    def test_decline_does_not_create_score_and_pause_resume_preserves_question(self):
        state=apply(new_course_state("lesson-1"),action="start_mood_check").state
        paused=apply(state,action="pause").state
        restored=apply(paused,action="resume")
        self.assertIn("上周",restored.reply)
        declined=apply(restored.state,action="skip_checkin").state
        self.assertEqual(declined["teacher_flow"]["weekly_mood"]["status"],"declined")
        self.assertNotIn("value",declined["teacher_flow"]["weekly_mood"])

    def test_unknown_field_exposes_original_style_help_and_keeps_case(self):
        state=new_course_state("lesson-1");state["stage"]="practice"
        state["draft_record"]["situation"]={"value":"朋友没回消息","source_message_id":"old"}
        case=state["case_id"]
        result=apply(state,"不知道")
        help_card=result.state["teacher_flow"]["cards"][-1]
        self.assertIn("自动思维",help_card["definition"])
        self.assertIn("数学考试",help_card["example"])
        self.assertEqual(result.reply,"谢谢您说出这些，我们按您的节奏整理。")
        self.assertEqual(result.state["case_id"],case)
        self.assertEqual(result.state["draft_record"],state["draft_record"])
        self.assertTrue(result.state["teacher_flow"]["cards"][-1]["help"])

    def test_all_four_unknown_branches_teach_before_defer_and_never_invent(self):
        values={"situation":"朋友没回复","thought":"他可能在忙","emotion":"失落","behavior":"继续散步"}
        for field in values:
            with self.subTest(field=field):
                state=new_course_state("lesson-1");state["stage"]="learn" if field=="situation" else "practice"
                for previous in values:
                    if previous==field: break
                    state["draft_record"][previous]={"value":values[previous],"source_message_id":"old"}
                    if previous=="thought":state["blueprint"]["ratings"]["thought_belief"]={"value":5}
                    if previous=="emotion":state["blueprint"]["ratings"]["emotion_intensity"]={"value":4}
                result=apply(state,"不知道")
                self.assertNotIn(field,result.state["draft_record"])
                self.assertNotIn(field,result.state["practice_flow"]["deferred"])
                self.assertTrue(any(c["field"]==field and c["help"] and c["definition"]==teacher_flow.CARDS[field]["definition"] for c in result.state["teacher_flow"]["cards"]))
                self.assertEqual(result.state["case_id"],state["case_id"])

    def test_multifield_answer_keeps_teaching_without_reasking_fields(self):
        state=new_course_state("lesson-1");state["stage"]="learn"
        fields={"situation":"等车","thought":"可能迟到","emotion":"担心","behavior":"继续等"}
        result=apply(state,"等车，可能迟到，担心，继续等",fields)
        self.assertEqual({c["field"] for c in result.state["teacher_flow"]["cards"]},set(fields))
        self.assertNotIn("当时有什么情绪",result.reply)

    def test_second_lesson_unknown_uses_example_and_returns_to_same_activity(self):
        state=new_course_state("lesson-2");lesson2_flow.go(state,"rain")
        result=turn(state,"不知道",client=Script(intent="help"))
        self.assertEqual(result.state["lesson2_flow"]["step"],"rain")
        self.assertIn("小明",result.reply)
        self.assertIn("词",str(result.state["teacher_flow"]["cards"]))
        self.assertEqual(result.state["draft_record"],{})

    def test_homework_no_attempt_has_one_optional_barrier_question(self):
        state=new_course_state("lesson-2");lesson2_flow.go(state,"homework")
        result=turn(state,"没做",client=Script(values={"homework_report":"没做"},homework_status="not_attempted"))
        self.assertTrue(result.state["lesson2_flow"]["homework"]["awaiting_barrier"])
        result=turn(result.state,"不想解释",action="continue_lesson2")
        self.assertEqual(result.state["lesson2_flow"]["step"],"recall")


class DiaryPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db=sessionmaker(bind=self.engine,expire_on_commit=False)()
        self.person=Participant(label=uuid.uuid4().hex,invite_hash="unused")
        self.db.add(self.person);self.db.commit()
        self.course,_=create_or_resume_course(self.db,participant_id=self.person.id,lesson_id="lesson-1")
        state=decrypt_json(self.course.agent_state_encrypted);state["completed"]=True
        self.course.agent_state_encrypted=encrypt_json(state);self.course.status="completed";self.db.commit()

    def tearDown(self):
        self.db.close();self.engine.dispose()

    def test_diary_is_encrypted_deduplicated_audited_and_owned(self):
        data=DiaryCreate(idempotency_key="request_one",source_kind="personal",situation="放学等公交",thought="可能晚到",emotion="担心")
        row=save(self.db,self.course,data)
        self.assertNotIn("放学",row.payload_encrypted)
        self.assertEqual(save(self.db,self.course,data).id,row.id)
        self.assertEqual(len(self.db.scalars(select(CourseHomeworkEntry)).all()),1)
        self.assertEqual(len(self.db.scalars(select(TurnEvent)).all()),1)
        self.db.expire(self.course,["homework_entries"])
        self.assertEqual(entries(self.course)[0]["fields"]["thought"],"可能晚到")
        self.assertIsNone(get_owned_course(self.db,conversation_id=self.course.id,participant_id="other"))
        with self.assertRaises(ValueError):save(self.db,self.course,data.model_copy(update={"emotion":"生气"}))

    def test_old_unfinished_and_invalid_whitespace_entries_are_rejected(self):
        data=DiaryCreate(idempotency_key="request_one",source_kind="fictional",situation="活动取消")
        self.course.lesson_version="old"
        with self.assertRaises(ValueError):save(self.db,self.course,data)
        from cbt_course_llm_freeform.catalog import lesson_version
        self.course.lesson_version=lesson_version("lesson-1")
        with self.assertRaises(ValueError):save(self.db,self.course,data.model_copy(update={"situation":"  "}))
        state=decrypt_json(self.course.agent_state_encrypted);state["completed"]=False
        self.course.agent_state_encrypted=encrypt_json(state)
        with self.assertRaises(ValueError):save(self.db,self.course,data)
