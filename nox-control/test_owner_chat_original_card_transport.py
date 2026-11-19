import base64
import copy
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock, call, patch

import owner_chat_original_card_transport as transport
import owner_native_operator as operator


class OriginalCardTransportTests(unittest.TestCase):
    def setUp(self):
        self.request = '1234'
        self.source = 'a' * 40
        self.receipt = {
            'schema': 'NOX_1A01_ORIGINAL_CARD_BROWSER_QA_V1',
            'request': self.request,
            'source_sha': self.source,
            'state': 'ORIGINAL_CARD_UI_QA_PASSED_S03_UNEVALUATED',
            'onehost_1a01_original_card_acceptance_state': 'ORIGINAL_CARD_UI_ACCEPTED',
            'two_turn_condition': 'NOT_RUN_SEPARATE_FROM_FROZEN_1A01_CARD',
            'actual_native_backend': True,
            'actual_native_model_stream_verified': True,
            'original_card_one_turn': True,
            'progressive_stream_render_verified': True,
            'accepted_input_waiting_answer_completed_ui_verified': True,
            'synthetic_backend_used': False,
            'canonical_s03_readback_verified': False,
            'supplemental_dialog_receipt_used_for_acceptance': False,
            'stream': {'native_calls': 1, 'native_eof': True, 'dom_answer_matches_native': True},
            'unexpected_private_field': 'must not be in the transport output',
        }

    def project(self, receipt):
        return transport.receipt_projection(json.dumps(receipt).encode(), self.request, self.source)

    def test_exact_operator_bundle_and_no_unpinned_source(self):
        allowed_paths = ('nox-control/owner_chat_browser_qa.py',
                         'nox-control/owner_browser_stream_only_entry.py')
        bundle_paths = operator.repair_bundle_paths('repair', operator.FILES['repair'], allowed_paths)
        bundle = {Path(path).name: base64.b64encode(Path(path).read_bytes()).decode()
                  for path in bundle_paths}
        self.assertEqual(set(transport.sources(bundle)), set(transport.PINS))
        with self.assertRaisesRegex(RuntimeError, 'HOLD_1A01_BUNDLE_SCOPE'):
            transport.sources({**bundle, 'arbitrary.py': 'Cg=='})
        bundle[transport.QA_ENTRY] = 'Cg=='
        with self.assertRaisesRegex(RuntimeError, 'HOLD_1A01_BUNDLE_PIN'):
            transport.sources(bundle)

    def test_ui_witness_does_not_export_private_fields_or_promote_s03(self):
        row = self.project(self.receipt)
        self.assertEqual(row['task_id'], '1A01')
        self.assertEqual(row['spec_sha256'], transport.TASK_SPEC_SHA256)
        self.assertEqual(row['owner_chat_stream_posts_observed'], 1)
        self.assertFalse(row['canonical_s03_readback_verified'])
        self.assertEqual(row['original_task_acceptance_delta'], 0)
        self.assertNotIn('unexpected_private_field', row)

    def test_rejects_mismatched_request_and_unproven_stream(self):
        with self.assertRaisesRegex(RuntimeError, 'HOLD_1A01_RECEIPT_SCOPE'):
            self.project({**self.receipt, 'request': '5678'})
        for field, value in (('native_calls', True), ('native_calls', 2), ('native_eof', False)):
            row = copy.deepcopy(self.receipt)
            row['stream'][field] = value
            with self.subTest(field=field, value=value):
                with self.assertRaisesRegex(RuntimeError, 'HOLD_1A01_STREAM_SCOPE'):
                    self.project(row)

    def test_timeout_signals_entire_group_before_reaping_child(self):
        process = Mock(pid=1234)
        process.wait.side_effect = [subprocess.TimeoutExpired('browser', 165), 0]
        event_order = Mock()
        event_order.attach_mock(process.wait, 'wait')
        with patch.object(transport.subprocess, 'Popen', return_value=process), \
                patch.object(transport.time, 'sleep'), \
                patch.object(transport.os, 'killpg', event_order.kill):
            with self.assertRaisesRegex(RuntimeError, 'HOLD_1A01_BROWSER_TIMEOUT'):
                transport.run_browser('/unused', Path('/unused'), {})
        self.assertEqual(event_order.mock_calls, [
            call.wait(timeout=165),
            call.kill(1234, transport.signal.SIGTERM),
            call.kill(1234, transport.signal.SIGKILL),
            call.wait(timeout=5),
        ])
