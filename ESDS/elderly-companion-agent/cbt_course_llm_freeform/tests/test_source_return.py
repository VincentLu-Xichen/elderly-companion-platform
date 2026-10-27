"""032: sourced requests and proactive refusal without a pending invitation."""
import copy
import unittest
from cbt_course_llm_freeform import learning_request
from cbt_course_llm_freeform.tests.test_dialogue_ownership import starting, turn, DialogueClient

class SourceReturnTests(unittest.TestCase):
    def test_proactive_repeated_refusal_preserves_case_without_inventing_invitation(self):
        state, history = starting()
        before = copy.deepcopy(state)
        for text in ['我现在还不想回练习，想再缓一会儿。', '我还是想先缓一会儿。']:
            result, history = turn(state, text, DialogueClient('decline_return', '好，先缓一会儿。'), history)
            state = result.state
            flow = state['classroom_dialogue']
            self.assertIsNone(flow['invitation'])
            self.assertEqual(flow['mode'], 'conversation')
            self.assertEqual(flow['return_preference']['quote'], text)
            for key in ['stage', 'case_id', 'draft_record', 'practice_flow', 'blueprint']:
                self.assertEqual(state[key], before[key])
            self.assertFalse(state['paused'])
        resumed, _ = turn(state, '现在愿意继续刚才的练习。', DialogueClient('resume_course', '好的。'), history)
        self.assertEqual(resumed.state['classroom_dialogue']['mode'], 'course')
        self.assertNotIn('return_preference', resumed.state['classroom_dialogue'])

    def test_request_sources_reject_old_id_paraphrase_and_empty_quote_without_mutation(self):
        state, _ = starting()
        latest = dict(id='current', content='不是要停课，只想说说。')
        for changes, error in [({'source_message_id':'old'}, 'message id mismatch'),
                               ({'quote':'我需要倾诉'}, 'quote is not current verbatim text'),
                               ({'quote':''}, 'quote is not current verbatim text'),
                               ({'quote':'要停课'}, 'omitted a negation')]:
            with self.subTest(changes=changes):
                candidate = copy.deepcopy(state)
                request = dict(mode='listen', deferred_rating_fields=[], source_message_id='current', quote=latest['content'])
                request.update(changes)
                with self.assertRaisesRegex(ValueError, error):
                    learning_request.apply(candidate, request, latest, '先听您说。')
                self.assertEqual(candidate, state)

    def test_current_verbatim_request_is_saved_as_current_evidence(self):
        state, _ = starting()
        latest = dict(id='current', content='我先不分析，只想说说。')
        request = dict(mode='listen', deferred_rating_fields=[], source_message_id='current', quote='只想说说')
        learning_request.apply(state, request, latest, '先听您说。')
        self.assertEqual(state['classroom_dialogue']['mode'], 'conversation')
        memory=state['latest_interaction_event']['memory']
        self.assertEqual(memory['quote'], '只想说说')
        self.assertEqual(memory['source_message_id'], 'current')
