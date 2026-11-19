"""Exact A1 continuation contract; no browser, network, GPU or S03 writes."""
import unittest

from owner_chat_browser_qa import admitted_qa_prompt, multiturn_history_valid, progressive_stream_valid


FIRST = 'Числа 1-10'
FIRST_ANSWER = '1,2,3,4,5,6,7,8,9,10'
SECOND = 'Числа в обратном порядке по предыдущему ответу'
SECOND_ANSWER = '10,9,8,7,6,5,4,3,2,1'


def rows():
    return [{'role':'user','content':FIRST},
            {'role':'assistant','content':FIRST_ANSWER},
            {'role':'user','content':SECOND},
            {'role':'assistant','content':SECOND_ANSWER}]


class SameDialogFourMessageContract(unittest.TestCase):
    def check(self, value):
        return multiturn_history_valid(value, FIRST, FIRST_ANSWER, SECOND, SECOND_ANSWER)

    def test_four_exact_ordered_messages_pass(self):
        self.assertTrue(self.check(rows()))

    def test_missing_or_extra_or_duplicate_message_holds(self):
        self.assertFalse(self.check(rows()[:2]))
        self.assertFalse(self.check(rows() + [rows()[3]]))
        self.assertFalse(self.check([rows()[0],rows()[1],rows()[2],rows()[2]]))

    def test_changed_first_answer_or_swapped_turns_holds(self):
        values=rows();values[1]['content']='unverified first';self.assertFalse(self.check(values))
        values=rows();values[2],values[3]=values[3],values[2];self.assertFalse(self.check(values))

    def test_unexpected_roles_and_non_objects_hold(self):
        values=rows();values[3]['role']='tool';self.assertFalse(self.check(values))
        values=rows();values[3]=None;self.assertFalse(self.check(values))
        self.assertFalse(self.check(None))

    def test_one_shot_native_post_admission_blocks_replay_and_third_turn(self):
        self.assertEqual(admitted_qa_prompt(0, False, FIRST, SECOND), FIRST)
        self.assertIsNone(admitted_qa_prompt(1, False, FIRST, SECOND))
        self.assertEqual(admitted_qa_prompt(1, True, FIRST, SECOND), SECOND)
        self.assertIsNone(admitted_qa_prompt(2, True, FIRST, SECOND))

    def test_second_turn_progress_requires_two_real_visible_prefixes(self):
        proof={'ui_measurement_kind':'CUMULATIVE_VISIBLE_ASSISTANT_BODY',
               'native_delta_count':3,'ui_before_native_done':True,
               'ui_prefix_lengths_before_done':[4,7],
               'ui_first_ms':12,'native_done_ms':120}
        self.assertTrue(progressive_stream_valid(proof))
        proof['ui_prefix_lengths_before_done']=[7]
        self.assertFalse(progressive_stream_valid(proof))


if __name__=='__main__':
    unittest.main()
