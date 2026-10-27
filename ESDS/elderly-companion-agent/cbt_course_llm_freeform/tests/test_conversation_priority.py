"""033: ongoing conversation preserves records without executing optional writes."""
import copy
import unittest
from cbt_course_llm_freeform import dialogue
from cbt_course_llm_freeform.tests.test_dialogue_ownership import starting, turn, DialogueClient


class ConversationPriorityTests(unittest.TestCase):
    def setUp(self):
        self.state, self.history = starting()
        detour, self.history = turn(self.state, '现在很难受，想先说一会儿。',
                                    DialogueClient('conversation', '先听您说。'), self.history)
        self.state = detour.state

    def test_conversation_rejects_optional_writes_but_preserves_reply_and_audit(self):
        text = '我只是想念她，并不是认为她一定不在乎我。'
        client = DialogueClient('conversation', '听见了，您是在表达想念。', fields={'thought': text})
        before = copy.deepcopy(self.state)
        result, _ = turn(self.state, text, client, self.history)
        self.assertEqual(result.reply, client.reply)
        for key in ['stage', 'draft_record', 'blueprint', 'practice_flow', 'case_id', 'confirmed_record']:
            self.assertEqual(result.state[key], before[key])
        self.assertEqual(result.state['classroom_dialogue'], before['classroom_dialogue'])
        self.assertEqual(result.trace['observations'], [])
        self.assertEqual(result.trace['conversation_record_guard']['rejected_observations'][0]['value'], text)
        self.assertEqual(len(client.calls), 1)
        self.assertFalse(result.trace['trigger']['triggered'])

    def test_unsourced_candidates_still_fail_atomically(self):
        before = copy.deepcopy(self.state)
        for client in [DialogueClient('conversation', fields={'thought':'不存在的原话'}),
                       DialogueClient('conversation', source='old', fields={'thought':'想念她'})]:
            with self.subTest(client=client):
                with self.assertRaisesRegex(ValueError, 'faithful current'):
                    turn(self.state, '想念她', client, self.history)
                self.assertEqual(self.state, before)

    def test_advancement_attempt_or_answer_claim_still_fails(self):
        for extra, attempted in [({'advance':True}, None), ({'case_options':['想念她']}, None), ({}, 'thought')]:
            with self.subTest(extra=extra, attempted=attempted):
                with self.assertRaisesRegex(ValueError, 'non-answer'):
                    turn(self.state, '想念她', DialogueClient('conversation', fields={'thought':'想念她'},
                         extra=extra, attempted_field=attempted), self.history)

    def test_does_not_claim_rejected_write_was_completed(self):
        for reply in ['已经修改记录了。', '我会把记录改为想念她。', '帮您记下这条想法。']:
            with self.subTest(reply=reply):
                with self.assertRaisesRegex(ValueError, 'rejected record write'):
                    turn(self.state, '想念她', DialogueClient('conversation', reply, fields={'thought':'想念她'}), self.history)

    def test_record_writes_in_concept_question_remain_invalid(self):
        with self.assertRaisesRegex(ValueError, 'non-answer'):
            turn(self.state, '想法是什么', DialogueClient('concept_question', fields={'thought':'想法是什么'}), self.history)

    def test_explicit_record_edit_uses_sourced_resume_path(self):
        text = '请把刚才记录里的想法改为她可能在忙。'
        client = DialogueClient('resume_course', '按您这次明确的纠正来整理。', fields={'thought':'她可能在忙'})
        result, _ = turn(self.state, text, client, self.history)
        self.assertEqual(result.state['classroom_dialogue']['mode'], 'course')
        self.assertEqual(result.state['draft_record']['thought']['value'], '她可能在忙')
        self.assertFalse(result.state['completed'])
        self.assertIsNone(result.state['confirmed_record'])
        self.assertIsNone(result.trace['conversation_record_guard'])

    def test_turn_guard_does_not_discard_answer_and_new_rating(self):
        client = DialogueClient('resume_course', '好的。', fields={'thought_belief':'相信程度0分'})
        result, _ = turn(self.state, '我愿意继续练习，相信程度0分。', client, self.history)
        self.assertEqual(result.state['blueprint']['ratings']['thought_belief']['value'], 0)
        self.assertIsNone(result.trace['conversation_record_guard'])
