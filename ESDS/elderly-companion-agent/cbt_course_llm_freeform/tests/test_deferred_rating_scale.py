"""034: resume does not reopen scoring; both case scales include zero."""
import copy
import unittest
from cbt_course_llm_freeform import blueprint, learning_request
from cbt_course_llm_freeform.runtime import FreeformCourseRuntime
from cbt_course_llm_freeform.teacher_flow import MOOD_QUESTION
from cbt_course_llm_freeform.tests.test_dialogue_ownership import starting, turn, DialogueClient


class DeferredRatingScaleTests(unittest.TestCase):
    def setUp(self):
        self.state, self.history = starting()
        latest = dict(id='034-defer', role='learner', content='先听我说，今天先不评分。')
        self.history.append(latest)
        learning_request.apply(self.state, dict(mode='listen', deferred_rating_fields=list(blueprint.RATINGS),
                               source_message_id=latest['id'], quote=latest['content']), latest, '先听您说。')

    def test_resume_keeps_deferrals_and_context_has_no_pending_ratings(self):
        deferred = copy.deepcopy(self.state['practice_flow']['deferred'])
        client = DialogueClient('resume_course', '我们继续核对已有的四部分。')
        result, _ = turn(self.state, '现在愿意继续刚才的练习。', client, self.history)
        self.assertEqual(result.state['practice_flow']['deferred'], deferred)
        self.assertEqual(result.state['blueprint']['ratings'], {})
        self.assertEqual(result.state['stage'], 'review')
        self.assertIsNone(result.state['confirmed_record'])
        context = FreeformCourseRuntime()._context(result.state)
        self.assertEqual(context['pending_task']['pending_fields'], [])
        self.assertEqual(set(context['pending_task']['deferred_fields']), set(blueprint.RATINGS))
        self.assertEqual(context['blueprint']['rating_scale'], dict(minimum=0, maximum=10, zero_is_valid=True))

    def test_explicit_zero_rating_reopens_only_its_own_deferred_field(self):
        result, history = turn(self.state, '我愿意继续练习。', DialogueClient('resume_course'), self.history)
        result, _ = turn(result.state, '我现在愿意评相信程度，相信程度0分。',
                         DialogueClient('answer', '这项按您给的数值整理，另一项仍暂留。',
                                        fields={'thought_belief':'相信程度0分'}), history)
        self.assertEqual(result.state['blueprint']['ratings']['thought_belief']['value'], 0)
        self.assertNotIn('thought_belief', result.state['practice_flow']['deferred'])
        self.assertEqual(result.state['practice_flow']['deferred']['emotion_intensity']['source_message_ids'], ['034-defer'])

    def test_case_scale_visible_outside_active_rating_focus_and_is_a_copy(self):
        for stage in ['learn', 'practice', 'review']:
            state = copy.deepcopy(self.state); state['stage'] = stage
            context = FreeformCourseRuntime()._context(state)
            self.assertEqual(context['blueprint']['rating_scale']['minimum'], 0)
            self.assertIsNone(context['pending_task']['scale'])
            context['blueprint']['rating_scale']['minimum'] = 99
            self.assertEqual(blueprint.RATING_SCALE['minimum'], 0)

    def test_both_case_rating_endpoints_remain_valid_weekly_scale_stays_separate(self):
        for quote, expected in [('相信程度0分', 0), ('情绪强度0分', 0), ('相信程度10分', 10), ('情绪强度10分', 10)]:
            self.assertEqual(blueprint.parse_rating(quote), expected)
        self.assertIsNone(blueprint.parse_rating('相信程度11分'))
        self.assertIn('上周', MOOD_QUESTION)
        self.assertIn('1—10', MOOD_QUESTION)
