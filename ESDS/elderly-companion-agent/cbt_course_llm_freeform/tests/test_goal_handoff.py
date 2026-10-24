import copy
import unittest
from datetime import timedelta

from cbt_course_llm_freeform import learning_check, navigation
from cbt_course_llm_freeform.runtime import new_course_state
from cbt_course_llm_freeform.tests.test_navigation import NavigationClient, navigate


def post_check():
    state=new_course_state('lesson-1',reflection_policy='none');learning_check.begin(state)
    for i in range(4):learning_check.save_answer(state,dict(id=f'answer-{i}',content='原答'),'matches','合成反馈')
    return state


class GoalHandoffTests(unittest.TestCase):
    def test_goal_at_feedback_enters_goal_without_rewriting_answers_or_confirming(self):
        state=post_check();before=copy.deepcopy(state['learning_check'])
        result=navigate(state,'我的练习目标就是想减少焦虑 更积极的面对生活',NavigationClient(intent='goal'))
        self.assertEqual(result.state['stage'],'learning_goal')
        self.assertIn('learning_goal_draft',result.state)
        self.assertNotIn('learning_goal',result.state)
        self.assertEqual(result.state['learning_check'],before)
        self.assertEqual(state['stage'],'check_feedback')
        self.assertEqual([c['phase'] for c in result.trace['model_calls']],['course_navigation'])

    def test_unclear_negative_and_ordinary_feedback_do_not_become_goals(self):
        for text in ['完成了','不是我的目标，是朋友想减少焦虑','还没想好目标']:
            result=navigate(post_check(),text,NavigationClient(intent='clarify'))
            self.assertEqual(result.state['stage'],'check_feedback')
            self.assertNotIn('learning_goal_draft',result.state)

    def test_continue_and_retry_remain_separate_explicit_choices(self):
        result=navigate(post_check(),'继续设置目标',NavigationClient(actions=['continue_after_check']))
        self.assertEqual(result.state['stage'],'learning_goal')
        result=navigate(post_check(),'再练一次',NavigationClient(actions=['start_check_retry']))
        self.assertTrue(learning_check.retrying(result.state))

    def test_wrong_source_and_illegal_jump_cannot_commit(self):
        for client in [NavigationClient(intent='goal',bad_source=True),NavigationClient(actions=['finish']),NavigationClient(actions=['confirm_learning_goal'])]:
            # A goal client uses exact quotes; exercise a forged source via actions separately.
            if client.intent=='goal':client=NavigationClient(actions=['continue_after_check'],bad_source=True)
            state=post_check();result=navigate(state,'继续',client)
            self.assertEqual(result.state['stage'],'check_feedback')
            self.assertFalse(result.state['completed'])
            self.assertNotIn('learning_goal',result.state)

    def test_active_retry_cannot_be_goal_navigation(self):
        state=post_check();state['learning_check']['retry']['status']='active'
        d=navigation.NavigationDecision(intent='goal',goal_items=['减少焦虑'])
        with self.assertRaises(ValueError):navigation.validate(d,state,dict(id='u',content='减少焦虑'))

    def test_failed_request_can_retry_same_input_key_and_deduplicate(self):
        from cbt_course_llm_freeform.tests.test_guided import GuidedPersistenceTests
        from cbt_course_llm_freeform.services import create_or_resume_course,process_course_turn
        from cbt_course_llm_freeform.runtime import FreeformCourseRuntime
        from cbt_course_llm_freeform.agent import FreeformCourseAgent
        from cbt_course_llm_freeform.preview import PreviewClient
        from webapp.security import encrypt_json,decrypt_json
        fixture=GuidedPersistenceTests();fixture.setUp()
        try:
            course=create_or_resume_course(fixture.db,participant_id=fixture.person.id,lesson_id='lesson-1')[0]
            course.agent_state_encrypted=encrypt_json(post_check());fixture.db.commit()
            class Fail:
                def process(self,*a,**kw):raise RuntimeError('synthetic failed attempt')
            args=dict(content='我的练习目标就是想减少焦虑',idempotency_key='handoff-retry-same-input')
            with self.assertRaises(RuntimeError):process_course_turn(fixture.db,course,**args,runtime_factory=Fail)
            self.assertEqual(decrypt_json(course.agent_state_encrypted)['stage'],'check_feedback')
            factory=lambda:FreeformCourseRuntime(agent=FreeformCourseAgent(client=PreviewClient()))
            result=process_course_turn(fixture.db,course,**args,runtime_factory=factory)
            again=process_course_turn(fixture.db,course,**args,runtime_factory=factory)
            self.assertEqual(decrypt_json(course.agent_state_encrypted)['stage'],'learning_goal')
            self.assertTrue(again['deduplicated'])
        finally:fixture.tearDown()

    def test_reflection_stale_naive_lock_reclaims_but_recent_lock_stays(self):
        from cbt_course_llm_freeform.tests.test_guided import GuidedPersistenceTests
        from cbt_course_llm_freeform.reflection import generate_course_reflection
        from cbt_course_llm_freeform.preview import PreviewClient
        from webapp.models import utcnow
        from webapp.security import decrypt_json
        fixture=GuidedPersistenceTests();fixture.setUp()
        try:
            course=fixture.finish_lesson()
            course.active_request_id='recent';course.processing_started_at=utcnow();fixture.db.commit()
            generate_course_reflection(course.id,session_factory=fixture.Session,client=PreviewClient())
            fixture.db.refresh(course);self.assertEqual(course.active_request_id,'recent')
            course.processing_started_at=utcnow()-timedelta(minutes=3);fixture.db.commit()
            generate_course_reflection(course.id,session_factory=fixture.Session,client=PreviewClient())
            fixture.db.refresh(course)
            self.assertIsNone(course.active_request_id)
            self.assertEqual(decrypt_json(course.agent_state_encrypted)['reflection']['status'],'ready')
        finally:fixture.tearDown()
