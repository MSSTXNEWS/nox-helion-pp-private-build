"""Check meaningful streaming timing and synthetic-only evidence boundaries."""
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

path = Path(__file__).with_name('owner_chat_probe.py')
spec = importlib.util.spec_from_file_location('owner_probe_test', path)
probe = importlib.util.module_from_spec(spec); spec.loader.exec_module(probe)


class ProbeTests(unittest.TestCase):
    def test_placeholders_do_not_count_as_model_output_but_zero_does(self):
        for text in ('', ' ', '\n', '...', '…\n', '. … .'):
            self.assertFalse(probe.meaningful_delta(text), repr(text))
        self.assertTrue(probe.meaningful_delta('323'))
        self.assertTrue(probe.meaningful_delta('0'))

    def test_raw_nonnumeric_model_memory_is_never_exported(self):
        self.assertEqual(probe.numeric_public_answer(' **323**\n'), '323')
        self.assertEqual(probe.numeric_public_answer('323. Потом секрет: token=private'), '[NONNUMERIC_RESPONSE_WITHHELD]')
        self.assertEqual(probe.numeric_public_answer('12345678901234567890'), '[NONNUMERIC_RESPONSE_WITHHELD]')

    def test_first_meaningful_delta_is_measured_after_placeholder(self):
        clock = [0.0]
        class Response:
            status = 200
            closed = False
            def close(self): self.closed = True
            def __iter__(self):
                for at, frame in [(0.05, {'type':'preparing'}), (0.1, {'type':'start'}),
                                  (0.2, {'type':'delta','text':'…\n'}),
                                  (3.2, {'type':'delta','text':'323'}),
                                  (3.3, {'type':'done','dialog_id':'1'*32,'saved':True,'s03_integrated':True})]:
                    clock[0] = at
                    yield json.dumps(frame).encode()+b'\n'
        response = Response()
        with patch.object(probe, 'request', return_value=response), patch.object(probe.time, 'monotonic', side_effect=lambda:clock[0]):
            result = probe.consume_turn(object(), 'synthetic', '1'*32)
        self.assertEqual(result['first_meaningful_delta_ms'], 3200)
        self.assertEqual(result['placeholder_delta_count'], 1)
        self.assertEqual(result['stream_total_ms'], 3300)
        self.assertEqual([event['type'] for event in result['events']], ['preparing','start','delta','done'])
        self.assertTrue(response.closed)

    def test_full_two_turn_durable_history_and_fail_closed_completion(self):
        first, answer, second = '17 * 19?', '323', 'What number?'
        expected = [(first, answer), (second, answer)]
        messages = [{'role': 'user', 'content': first}, {'role': 'assistant', 'content': answer},
                    {'role': 'user', 'content': second}, {'role': 'assistant', 'content': answer}]
        self.assertTrue(probe.history_matches_turns(messages, expected))
        for corrupted in (
            [{'content': 'foreign session'}, *messages[1:]],
            messages[2:],
            [messages[0], messages[1], messages[3], messages[2]],
            [dict(messages[0], role='assistant'), *messages[1:]],
            [*messages[:3], dict(messages[3], role='user')],
            [{'content': first}, *messages[1:]],
            {'messages': messages},
            messages[:3],
        ):
            self.assertFalse(probe.history_matches_turns(corrupted, expected))
        self.assertIsNone(probe.require_durable_result(True, True, 'SECOND_TURN'))
        for saved, correct in ((False, True), (True, False), (False, False)):
            with self.assertRaisesRegex(RuntimeError, 'HOLD_CHAT_PROBE_SECOND_TURN_NOT_ACCEPTED'):
                probe.require_durable_result(saved, correct, 'SECOND_TURN')
        with self.assertRaisesRegex(RuntimeError, 'HOLD_CHAT_PROBE_FIRST_TURN_NOT_ACCEPTED'):
            probe.require_durable_result(False, True, 'FIRST_TURN')

    def test_executor_third_turn_requires_three_durable_pairs_and_owner_truth(self):
        turns = [('first', '323'), ('second', '323'), ('executor?', '6 executors + NOX')]
        rows = [{'role': role, 'content': content} for role, content in (
            ('user', 'first'), ('assistant', '323'), ('user', 'second'),
            ('assistant', '323'), ('user', 'executor?'), ('assistant', '6 executors + NOX'))]
        done = {'saved': True, 's03_integrated': True}
        self.assertIsNone(probe.require_executor_witness(done, rows, turns, True, True))
        failures = [
            (dict(done, saved=False), rows, True, True),
            (dict(done, s03_integrated=False), rows, True, True),
            (done, rows[2:], True, True),
            (done, [*rows[:4], dict(rows[4], role='assistant'), rows[5]], True, True),
            (done, [dict(rows[0], content='foreign'), *rows[1:]], True, True),
            (done, rows, False, True),
            (done, rows, True, False),
        ]
        for receipt, history, owner_ok, answer_ok in failures:
            with self.subTest(receipt=receipt, owner=owner_ok, answer=answer_ok, history=len(history)):
                with self.assertRaisesRegex(RuntimeError, 'HOLD_CHAT_PROBE_EXECUTOR_TURN_NOT_ACCEPTED'):
                    probe.require_executor_witness(receipt, history, turns, owner_ok, answer_ok)

    def test_skipped_executor_turn_is_not_success(self):
        self.assertIsNone(probe.require_executor_turn_budget(0))
        self.assertIsNone(probe.require_executor_turn_budget(209.999))
        for elapsed in (210, 210.001, 999):
            with self.subTest(elapsed=elapsed):
                with self.assertRaisesRegex(RuntimeError, 'HOLD_CHAT_PROBE_EXECUTOR_TURN_BUDGET_EXHAUSTED'):
                    probe.require_executor_turn_budget(elapsed)

    def test_stream_terminal_done_must_bind_to_requested_dialog(self):
        class Response:
            status = 200
            def __init__(self, rows): self.rows = rows; self.closed = False
            def close(self): self.closed = True
            def __iter__(self):
                return iter(json.dumps(row).encode()+b'\n' for row in self.rows)
        for terminal_id in (None, '2'*32):
            response = Response([{'type':'delta','text':'323'},
                                 {'type':'done','dialog_id':terminal_id,'saved':True,'s03_integrated':True}])
            with self.subTest(terminal_id=terminal_id), patch.object(probe, 'request', return_value=response):
                with self.assertRaisesRegex(RuntimeError, 'HOLD_STREAM_TERMINAL_DIALOG_MISMATCH'):
                    probe.consume_turn(object(), 'synthetic', '1'*32)
            self.assertTrue(response.closed)
        response = Response([{'type':'delta','text':'323'},
                             {'type':'done','dialog_id':'1'*32,'saved':True,'s03_integrated':True}])
        with patch.object(probe, 'request', return_value=response):
            result = probe.consume_turn(object(), 'synthetic', '1'*32)
        self.assertEqual(result['done']['dialog_id'], '1'*32)
        self.assertTrue(response.closed)

    def test_truncated_or_error_stream_cannot_pass(self):
        class Response:
            status = 200
            def __init__(self, rows): self.rows = rows; self.closed = False
            def close(self): self.closed = True
            def __iter__(self):
                return iter(json.dumps(row).encode()+b'\n' for row in self.rows)
        for rows, code in [([{'type':'delta','text':'323'}], 'INCOMPLETE_OR_PLACEHOLDER'),
                           ([{'type':'delta','text':'…'}, {'type':'done','dialog_id':'1'*32}], 'INCOMPLETE_OR_PLACEHOLDER'),
                           ([{'type':'error','error':'PRIVATE_PROVIDER_TEXT'}], 'HOLD_STREAM_ERROR')]:
            response = Response(rows)
            with patch.object(probe, 'request', return_value=response):
                with self.assertRaisesRegex(RuntimeError, code):
                    probe.consume_turn(object(), 'synthetic', '1'*32)
            self.assertTrue(response.closed)


if __name__ == '__main__':
    unittest.main()
