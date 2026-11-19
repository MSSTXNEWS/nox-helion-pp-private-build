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

    def test_probe_accepts_only_explicit_owner_dialog_scope(self):
        did='d'*32
        done={'saved':True,'owner_dialog_saved':True,'s03_integrated':False,
              'canonical_s03_write_verified':False,'writer':'V112_OWNER_DIALOG_WRITER',
              'dialog_id':did,'turn_id':'1'*32,'receipt_id':'2'*32,'lease_epoch':'3'*32,
              'exchange_id':'4'*32,'receipt_sha256':'a'*64}
        history={'status':'READY','dialog_id':did,'store_scope':'OWNER_DIALOG_TABLES_ONLY',
                 'canonical_s03_readback_verified':False,'messages':[]}
        self.assertTrue(probe.owner_dialog_completion(done,did))
        self.assertEqual(probe.owner_dialog_history(history,did),[])
        self.assertFalse(probe.owner_dialog_completion({**done,'s03_integrated':True},did))
        self.assertFalse(probe.owner_dialog_completion({**done,'canonical_s03_write_verified':True},did))
        self.assertIsNone(probe.owner_dialog_history({**history,'store_scope':'S03'},did))
        self.assertIsNone(probe.owner_dialog_history({**history,'canonical_s03_readback_verified':True},did))

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
                                  (3.3, {'type':'done','saved':True,'s03_integrated':False,
                                      'owner_dialog_saved':True,'canonical_s03_write_verified':False})]:
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

    def test_truncated_or_error_stream_cannot_pass(self):
        class Response:
            status = 200
            def __init__(self, rows): self.rows = rows; self.closed = False
            def close(self): self.closed = True
            def __iter__(self):
                return iter(json.dumps(row).encode()+b'\n' for row in self.rows)
        for rows, code in [([{'type':'delta','text':'323'}], 'INCOMPLETE_OR_PLACEHOLDER'),
                           ([{'type':'delta','text':'…'}, {'type':'done'}], 'INCOMPLETE_OR_PLACEHOLDER'),
                           ([{'type':'error','error':'PRIVATE_PROVIDER_TEXT'}], 'HOLD_STREAM_ERROR')]:
            response = Response(rows)
            with patch.object(probe, 'request', return_value=response):
                with self.assertRaisesRegex(RuntimeError, code):
                    probe.consume_turn(object(), 'synthetic', '1'*32)
            self.assertTrue(response.closed)


if __name__ == '__main__':
    unittest.main()
