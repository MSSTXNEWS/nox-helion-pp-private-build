"""Exact A1 continuation contract; no browser, network, GPU or S03 writes."""
import unittest

from owner_chat_browser_qa import (admitted_qa_prompt, allowed_qa_request,
                                   canonical_s03_proof_valid, multiturn_history_valid, progressive_stream_valid)


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

    def test_no_null_or_missing_message_can_bypass_exhausted_admission(self):
        good_first={'message': FIRST, 'dialog_id': 'synthetic-dialog'}
        good_second={'message': SECOND, 'dialog_id': 'synthetic-dialog'}
        self.assertTrue(allowed_qa_request(0, False, FIRST, SECOND, good_first, 'synthetic-dialog'))
        self.assertFalse(allowed_qa_request(1, False, FIRST, SECOND, good_second, 'synthetic-dialog'))
        self.assertTrue(allowed_qa_request(1, True, FIRST, SECOND, good_second, 'synthetic-dialog'))
        for bad in ({'message':None,'dialog_id':'synthetic-dialog'},
                    {'dialog_id':'synthetic-dialog'}, {}, None):
            self.assertFalse(allowed_qa_request(1, False, FIRST, SECOND, bad, 'synthetic-dialog'))
            self.assertFalse(allowed_qa_request(2, True, FIRST, SECOND, bad, 'synthetic-dialog'))
        self.assertFalse(allowed_qa_request(2, True, FIRST, SECOND, good_second, 'synthetic-dialog'))
        self.assertFalse(allowed_qa_request(0, False, FIRST, SECOND, good_first, 'other-dialog'))

    def test_dialog_history_alone_is_not_canonical_s03_proof(self):
        self.assertFalse(canonical_s03_proof_valid(None, None, 'synthetic-dialog', rows()))

    def test_canonical_s03_requires_matching_writer_receipt_and_independent_readback(self):
        expected = rows()
        receipt = {'source':'canonical_s03', 'verified':True, 'durable':True,
                   'event_id':'evt-1', 'turn_id':'turn-2', 'sequence':2,
                   'dialog_id':'synthetic-dialog'}
        readback = {'source':'canonical_s03', 'independent':True,
                    'event_id':'evt-1', 'turn_id':'turn-2', 'sequence':2,
                    'dialog_id':'synthetic-dialog', 'messages':expected,
                    'full_answer_sha256':__import__('hashlib').sha256(
                        SECOND_ANSWER.encode('utf-8')).hexdigest()}
        self.assertTrue(canonical_s03_proof_valid(
            receipt, readback, 'synthetic-dialog', expected))
        bad = dict(readback, event_id='other-event')
        self.assertFalse(canonical_s03_proof_valid(
            receipt, bad, 'synthetic-dialog', expected))
        bad = dict(readback, independent=False)
        self.assertFalse(canonical_s03_proof_valid(
            receipt, bad, 'synthetic-dialog', expected))
        bad = dict(readback, full_answer_sha256='0' * 64)
        self.assertFalse(canonical_s03_proof_valid(
            receipt, bad, 'synthetic-dialog', expected))

    def test_second_turn_progress_requires_two_real_visible_prefixes(self):
        proof={'ui_measurement_kind':'CUMULATIVE_VISIBLE_ASSISTANT_BODY',
               'native_delta_count':3,'ui_before_native_done':True,
               'ui_prefix_lengths_before_done':[4,7],
               'ui_first_ms':12,'native_done_ms':120}
        self.assertTrue(progressive_stream_valid(proof))
        proof['ui_prefix_lengths_before_done']=[7]
        self.assertFalse(progressive_stream_valid(proof))


    def test_long_context_is_compared_without_silent_truncation(self):
        long_first = 'P' * (256 * 1024)
        long_first_answer = 'A' * (256 * 1024)
        long_second = 'Q' * (256 * 1024)
        long_second_answer = 'B' * (256 * 1024)
        expected = [
            {'role':'user','content':long_first},
            {'role':'assistant','content':long_first_answer},
            {'role':'user','content':long_second},
            {'role':'assistant','content':long_second_answer},
        ]
        self.assertTrue(multiturn_history_valid(
            expected, long_first, long_first_answer, long_second, long_second_answer))
        expected[1]['content'] = expected[1]['content'][:-1]
        self.assertFalse(multiturn_history_valid(
            expected, long_first, long_first_answer, long_second, long_second_answer))

    def test_tool_result_role_cannot_be_counted_as_chat_context(self):
        values = rows()
        values[1] = {'role':'tool','content':'large tool output'}
        self.assertFalse(self.check(values))


if __name__=='__main__':
    unittest.main()
