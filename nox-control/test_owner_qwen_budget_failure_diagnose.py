import ast
import hashlib
import json
import os
from pathlib import Path
import tempfile
import types
import unittest

import owner_qwen_budget_failure_diagnose as diagnostic

CODE = 'HOLD_QWEN_REVISION_WAIT_OPTIMIZER_PERMISSION_TIMEOUT'
TRANSPORT = 'HOLD_MEMFD_TRANSPORT_DEADLINE'


class BudgetDiagnosticTests(unittest.TestCase):
    def summary(self, code=CODE):
        return {'state': code, 'successful_optimizer_steps': 25, 'new_successful_optimizer_steps': 0,
                'attempted_steps': 25, 'skipped_steps': 0, 'reload_verified': True,
                'independent_holdout_accepted': True}

    def core(self):
        def plain(path):
            path = Path(path)
            diagnostic.require(path.is_absolute() and not any(p.is_symlink() for p in (*path.parents, path)), 'PATH')
            return path
        return types.SimpleNamespace(plain=plain,
            ident=lambda s: tuple(getattr(s, key) for key in ('st_dev', 'st_ino', 'st_size', 'st_mode',
                'st_uid', 'st_gid', 'st_mtime_ns', 'st_ctime_ns')),
            encode=lambda value: json.dumps(value).encode())

    def fixture(self):
        summary = self.summary()
        logs = [{'stream': 'stdout', 'modified_during_current_attempt': True, 'mtime_ns': 1100 * 10**9,
                 'last_nonempty_line_terminal_code': CODE, 'last_nonempty_line_terminal_summary': summary}]
        flags = {'TRAIN_HOLD.flag': {'present': True, 'ownership': 'OWNED_CURRENT_WINDOW_FAILURE',
                 'sha256': diagnostic.HOLD_SHA, 'mtime_ns': 1101 * 10**9},
                 'TRAIN_PAUSE_REQUEST.flag': {'present': False}}
        terminal = {'current_process_and_known_checkpoint_bound': True, 'terminal_summary': summary}
        return logs, flags, terminal

    def test_exact_shared_require_code_and_both_source_pins(self):
        folder = Path(__file__).resolve().parent
        student = (folder / 'qwen_student_training_entry_transport_budget.py').read_bytes()
        shared = (folder / 'owner_qwen_execution_revision.py').read_bytes()
        allowed = diagnostic.allowed_terminal_codes(student, shared)
        self.assertIn(CODE, allowed)
        self.assertIn(TRANSPORT, allowed)
        self.assertNotIn('HOLD_QWEN_REVISION_PRIVATE_UNREVIEWED', allowed)
        with self.assertRaisesRegex(RuntimeError, 'LOG_MARKER_SOURCE_PIN'):
            diagnostic.allowed_terminal_codes(student, shared + b'\n')
        issuer = (folder / 'owner_qwen_transport_budget_install.py').read_bytes()
        self.assertEqual(hashlib.sha256(issuer).hexdigest(), diagnostic.INSTALLER_SHA)

    def test_seven_field_current_terminal_is_safe_and_must_be_last(self):
        raw = b'private/path?token=secret\n' + json.dumps(self.summary()).encode() + b'\n'
        row = diagnostic.parse_terminal(raw, {CODE})
        self.assertEqual(row['last_nonempty_line_terminal_summary'], self.summary())
        self.assertNotIn('secret', json.dumps(row))
        self.assertIsNone(diagnostic.parse_terminal(raw + b'private later text\n', {CODE})[
            'last_nonempty_line_terminal_code'])
        early = json.dumps({'state': TRANSPORT, 'native_success_claimed': False}).encode()
        self.assertEqual(diagnostic.parse_terminal(early, {TRANSPORT})['last_nonempty_line_terminal_code'], TRANSPORT)

    def test_counter_types_duplicate_keys_and_private_extra_fields_are_not_evidence(self):
        for key, value in [('attempted_steps', 26), ('skipped_steps', True),
                           ('reload_verified', 1), ('new_successful_optimizer_steps', -1),
                           ('state', 'HOLD_PRIVATE_UNREVIEWED'), ('secret', 'x')]:
            row = self.summary(); row[key] = value
            self.assertIsNone(diagnostic.parse_terminal(json.dumps(row).encode(), {CODE})[
                'last_nonempty_line_terminal_code'])
        raw = json.dumps(self.summary()).encode().replace(b'{', b'{"state":"private",', 1)
        self.assertIsNone(diagnostic.parse_terminal(raw, {CODE})['last_nonempty_line_terminal_code'])

    def test_timeout_requires_matching_terminal_receipt_and_owned_flag_time(self):
        logs, flags, terminal = self.fixture()
        out = diagnostic.primary_failure(logs, flags, 1000, terminal)
        self.assertEqual(out['code'], CODE)
        self.assertTrue(out['optimizer_permission_wait_timeout_observed'])
        self.assertFalse(out['transport_budget_exhaustion_observed'])
        terminal['current_process_and_known_checkpoint_bound'] = False
        self.assertIsNone(diagnostic.primary_failure(logs, flags, 1000, terminal)['code'])
        for key, value in [('sha256', '0' * 64), ('ownership', 'OTHER_OR_UNRECOGNIZED'),
                           ('mtime_ns', 2000 * 10**9)]:
            logs, flags, terminal = self.fixture(); flags['TRAIN_HOLD.flag'][key] = value
            self.assertIsNone(diagnostic.primary_failure(logs, flags, 1000, terminal)['code'])
        logs, flags, terminal = self.fixture(); logs[0]['modified_during_current_attempt'] = False
        self.assertIsNone(diagnostic.primary_failure(logs, flags, 1000, terminal)['code'])

    def test_terminal_receipt_requires_current_binding_pid_and_known_checkpoint(self):
        binding = {'schema': 'fixture'}
        identity = {'pid': 1025702, 'start_ticks': 162077108, 'boot_id': '9c0ecc02-85c1-452b-b8ae-521e9a11fd03'}
        output = Path('/synthetic/private/output')
        value = {**self.summary(), 'execution_binding': binding, 'process_identity': identity,
                 'checkpoint': str(output / diagnostic.FRESH_CHECKPOINT['directory']),
                 'checkpoint_manifest_sha256': diagnostic.FRESH_CHECKPOINT['manifest_sha256'],
                 'holdout_finite': True, 'holdout_evaluated_successful_total': 25,
                 'private_training_examples': ['never export']}
        core = types.SimpleNamespace(document=lambda *_: (value, b'synthetic'), digest=diagnostic.digest)
        result = diagnostic.terminal_receipt(core, {'output': output}, binding, identity, {CODE})
        self.assertTrue(result['current_process_and_known_checkpoint_bound'])
        self.assertNotIn('never export', json.dumps(result))
        self.assertNotIn('/synthetic', json.dumps(result))
        for key, replacement in [('execution_binding', {}), ('process_identity', {**identity, 'pid': 1}),
                                 ('checkpoint_manifest_sha256', '0' * 64)]:
            old = value[key]; value[key] = replacement
            self.assertFalse(diagnostic.terminal_receipt(core, {'output': output}, binding, identity, {CODE})[
                'current_process_and_known_checkpoint_bound'])
            value[key] = old

    def test_absence_is_verified_and_any_finalizer_or_activation_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path / 'operation_result.json').write_text('{}')
            before = diagnostic.absence_of_finalizer_and_activation(self.core(), path)
            self.assertTrue(before['finalizer_receipts_absent'])
            self.assertEqual(before['entries_observed'], 1)
            for name in ['finalize-anything.json', 'activation.json']:
                leaf = path / name; leaf.symlink_to(path / 'missing')
                with self.assertRaises(RuntimeError):
                    diagnostic.absence_of_finalizer_and_activation(self.core(), path)
                leaf.unlink()

    def test_absence_scan_bounded_and_symlink_directory_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            for number in range(65):
                (path / str(number)).touch()
            with self.assertRaisesRegex(RuntimeError, 'DIRECTORY_BOUND'):
                diagnostic.absence_of_finalizer_and_activation(self.core(), path)
            link = path / 'alias'; link.symlink_to(path, target_is_directory=True)
            with self.assertRaisesRegex(RuntimeError, 'PATH'):
                diagnostic.absence_of_finalizer_and_activation(self.core(), link)

    def test_no_controls_payload_reads_or_old_finalizer_dependency(self):
        raw = Path(diagnostic.__file__).read_text(); tree = ast.parse(raw)
        called = {node.func.attr for node in ast.walk(tree)
                  if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
        self.assertFalse(called & {'write_bytes', 'write_text', 'unlink', 'replace', 'rename', 'mkdir',
            'chmod', 'full_checkpoint', 'start', 'stop', 'request_pause', 'tick', 'owned_pause', 'main'})
        alarms = [node.args[0].value for node in ast.walk(tree) if isinstance(node, ast.Call)
                  and isinstance(node.func, ast.Attribute) and node.func.attr == 'alarm'
                  and node.args and isinstance(node.args[0], ast.Constant)]
        self.assertEqual(alarms, [20, 0])
        self.assertNotIn('FINALIZE_SHA', raw)
        self.assertEqual(diagnostic.REFERENCE['request'], '6914959637')
        self.assertEqual(diagnostic.DIRECTORY_LIMIT, 64)
        self.assertEqual(diagnostic.LOG_LIMIT, 65536)


if __name__ == '__main__':
    unittest.main()
