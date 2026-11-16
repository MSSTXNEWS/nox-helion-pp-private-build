import ast
import json
from pathlib import Path
import unittest

import owner_qwen_transport_failure_diagnose as diagnostic

CODE = 'HOLD_MEMFD_TRANSPORT_DEADLINE'


class DiagnosticTests(unittest.TestCase):
    def terminal(self, code=CODE):
        return json.dumps({'state': code, 'native_success_claimed': False}).encode()

    def fixture(self):
        logs = [{'stream': 'stdout', 'modified_during_current_attempt': True,
                 'mtime_ns': 1100 * 10**9, 'last_nonempty_line_terminal_code': CODE}]
        flags = {'TRAIN_HOLD.flag': {'present': True, 'ownership': 'OWNED_CURRENT_WINDOW_FAILURE',
                 'sha256': diagnostic.HOLD_SHA, 'mtime_ns': 1101 * 10**9},
                 'TRAIN_PAUSE_REQUEST.flag': {'present': False}}
        return logs, flags

    def test_only_exact_final_terminal_can_identify_budget(self):
        raw = b'private/path?token=secret\n' + self.terminal() + b'\n'
        value = diagnostic.parse_terminal(raw, {CODE})
        self.assertEqual(value['last_nonempty_line_terminal_code'], CODE)
        self.assertNotIn('secret', json.dumps(value))
        value = diagnostic.parse_terminal(raw + b'{"state":"PINNED_PUBLIC_BASE_STAGING"}\n', {CODE})
        self.assertIsNone(value['last_nonempty_line_terminal_code'])

    def test_duplicate_unknown_or_claimed_success_is_not_terminal_evidence(self):
        rows = (b'{"state":"HOLD_MEMFD_TRANSPORT_DEADLINE","state":"private","native_success_claimed":false}',
                self.terminal('HOLD_PRIVATE_UNREVIEWED_VALUE'),
                b'{"state":"HOLD_MEMFD_TRANSPORT_DEADLINE","native_success_claimed":true}',
                b'{"state":"HOLD_MEMFD_TRANSPORT_DEADLINE","native_success_claimed":false,"secret":"x"}')
        for row in rows:
            self.assertIsNone(diagnostic.parse_terminal(row, {CODE})['last_nonempty_line_terminal_code'])

    def test_exact_owned_flag_and_time_are_required_not_elapsed_progress(self):
        logs, flags = self.fixture()
        self.assertTrue(diagnostic.primary_failure(logs, flags, 1000)['transport_budget_exhaustion_observed'])
        for key, value in (('ownership', 'OTHER_OR_UNRECOGNIZED'), ('sha256', '0' * 64),
                           ('mtime_ns', 2000 * 10**9)):
            logs, flags = self.fixture(); flags['TRAIN_HOLD.flag'][key] = value
            self.assertFalse(diagnostic.primary_failure(logs, flags, 1000)['transport_budget_exhaustion_observed'])
        logs, flags = self.fixture(); logs[0]['modified_during_current_attempt'] = False
        self.assertFalse(diagnostic.primary_failure(logs, flags, 1000)['transport_budget_exhaustion_observed'])
        logs, flags = self.fixture(); logs[0]['last_nonempty_line_terminal_code'] = None
        self.assertFalse(diagnostic.primary_failure(logs, flags, 1000)['transport_budget_exhaustion_observed'])

    def test_later_verified_guard_pause_does_not_relabel_the_original_exit(self):
        logs, flags = self.fixture()
        flags['TRAIN_PAUSE_REQUEST.flag'] = {'present': True, 'ownership': 'OWNED_CURRENT_GUARD_PAUSE',
                                           'mtime_ns': 1600 * 10**9}
        self.assertTrue(diagnostic.primary_failure(logs, flags, 1000)['transport_budget_exhaustion_observed'])
        flags['TRAIN_PAUSE_REQUEST.flag']['mtime_ns'] = 1090 * 10**9
        self.assertFalse(diagnostic.primary_failure(logs, flags, 1000)['transport_budget_exhaustion_observed'])
        flags['TRAIN_PAUSE_REQUEST.flag']['ownership'] = 'OTHER_OR_UNRECOGNIZED'
        self.assertFalse(diagnostic.primary_failure(logs, flags, 1000)['transport_budget_exhaustion_observed'])

    def test_actual_runtime_defines_deadline_and_frozen_sources_have_exact_pins(self):
        import hashlib
        directory = Path(__file__).resolve().parent
        runtime = (directory / 'qwen_student_training_entry_transport_candidate.py').read_bytes()
        self.assertEqual(hashlib.sha256(runtime).hexdigest(), diagnostic.STUDENT_SHA)
        self.assertIn(CODE, {n.value for n in ast.walk(ast.parse(runtime))
            if isinstance(n, ast.Constant) and isinstance(n.value, str)})
        issuer = (directory / 'owner_qwen_transport_revision_install.py').read_bytes()
        self.assertEqual(hashlib.sha256(issuer).hexdigest(), diagnostic.INSTALLER_SHA)

    def test_diagnostic_source_has_no_control_or_payload_read(self):
        tree = ast.parse(Path(diagnostic.__file__).read_text())
        called = {n.func.attr for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        self.assertFalse(called & {'write_bytes', 'write_text', 'unlink', 'replace', 'rename',
            'full_checkpoint', 'start', 'stop', 'request_pause', 'tick', 'owned_pause', 'main'})
        self.assertEqual(diagnostic.LOG_LIMIT, 65536)
        self.assertEqual(diagnostic.REFERENCE['request'], '6913811534')


if __name__ == '__main__':
    unittest.main()
