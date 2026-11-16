"""Synthetic checks for optional log projection; no native observation."""
import ast
import hashlib
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock


HERE = Path(__file__).parent
RAW = (HERE / 'owner_qwen_transport_observe.py').read_bytes()
M = types.ModuleType('_test_transport_observer')
exec(compile(RAW, str(HERE / 'owner_qwen_transport_observe.py'), 'exec'), M.__dict__)


def event(**changes):
    row = {'state': 'PINNED_PUBLIC_BASE_STAGING', 'transport_version': 'NOX_QWEN_PUBLIC_TRANSPORT_V1',
           'stage': 'READ', 'attempt': 2, 'committed_offset': 1048576, 'bytes': 1048576, 'total': 5276436216,
           'http_status': 206, 'exception_type': 'TimeoutError', 'errno': 110,
           'staging_elapsed_seconds': 60.5, 'io_elapsed_seconds': 30.0}
    row.update(changes)
    return row


def line(row):
    return json.dumps(row, separators=(',', ':')).encode() + b'\n'


def require(ok, code):
    if not ok:
        raise RuntimeError('HOLD_TEST_' + code)


class ProjectionTests(unittest.TestCase):
    def test_only_public_numeric_and_categorical_fields_leave_parser(self):
        raw = line(event(url='https://private.invalid/token=secret', error='private body',
                         file='/private/path', prompt='private user text', process_identity={'pid': 123}))
        rows = M.transport_events(raw)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['committed_offset'], 1048576)
        self.assertEqual(rows[0]['http_status'], 206)
        self.assertEqual(rows[0]['exception_type'], 'TimeoutError')
        exported = json.dumps(rows)
        for text in ('private', 'secret', 'prompt', 'process_identity', 'url'):
            self.assertNotIn(text, exported)

    def test_malformed_counters_stage_version_or_duplicate_keys_are_ignored(self):
        bad = [event(bytes=True, committed_offset=True), event(committed_offset=True),
               event(committed_offset=2), event(total=1), event(stage=['READ']),
               event(attempt=True), event(attempt=7), event(transport_version='OTHER'),
               event(state='PRIVATE_OTHER_STATE')]
        raw = b''.join(line(row) for row in bad)
        raw += line(event()).replace(b'"attempt":2', b'"attempt":2,"attempt":1')
        self.assertEqual(M.transport_events(raw), [])

    def test_nonfinite_and_unrecognized_exception_text_is_not_exported(self):
        raw = line(event(exception_type={'secret': 'value'}, errno=True, http_status=True,
                         io_elapsed_seconds=1e300))
        rows = M.transport_events(raw)
        self.assertEqual(rows[0]['exception_type'], 'OTHER_EXCEPTION')
        self.assertIsNone(rows[0]['errno']); self.assertIsNone(rows[0]['http_status'])
        self.assertIsNone(rows[0]['io_elapsed_seconds'])
        self.assertEqual(M.transport_events(line(event(io_elapsed_seconds=float('nan')))), [])

    def test_gib_progress_without_stage_or_attempt_remains_telemetry(self):
        row = event()
        for key in ('stage', 'attempt', 'committed_offset', 'http_status', 'exception_type', 'errno',
                    'staging_elapsed_seconds', 'io_elapsed_seconds'):
            row.pop(key)
        projected = M.transport_events(line(row))[0]
        self.assertEqual(projected['stage'], 'PROGRESS')
        self.assertIsNone(projected['attempt'])
        self.assertEqual(projected['committed_offset'], row['bytes'])

    def test_tail_and_output_event_counts_are_bounded(self):
        raw = line(event(bytes=17, committed_offset=17)) + b'x' * 65536 + b'\n'
        raw += b''.join(line(event(bytes=i, committed_offset=i)) for i in range(40))
        rows = M.transport_events(raw)
        self.assertEqual(len(rows), 24)
        self.assertEqual([row['committed_offset'] for row in rows], list(range(16, 40)))

    def test_known_supervisor_stdout_read_is_bounded_and_does_not_claim_pid_binding(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / 'logs').mkdir(); log = root / 'logs/student.stdout'
            log.write_bytes(b'x' * 100000 + b'\n' + line(event()))
            config = ('[program:trainer]\nstdout_logfile=' + str(log) + '\n').encode()
            helper = types.SimpleNamespace(ROOT=root, SUPERVISOR=root / 'supervisor.conf', SERVICE='trainer',
                SUPERVISOR_SHA=hashlib.sha256(config).hexdigest(), read=lambda _: config,
                digest=lambda raw: hashlib.sha256(raw).hexdigest(), plain=lambda path: path)
            result = M.transport_telemetry(types.SimpleNamespace(require=require), {'helper': helper})
            self.assertEqual(result['status'], 'BOUNDED_LOG_TELEMETRY')
            self.assertEqual(result['tail_bytes_read'], 65536)
            self.assertEqual(len(result['events']), 1)
            self.assertTrue(result['may_include_prior_runs'])
            self.assertFalse(result['current_process_bound']); self.assertFalse(result['full_weights_integrity_proven'])
            self.assertNotIn(str(root), json.dumps(result))

    def test_bad_supervisor_pin_prevents_any_log_open(self):
        helper = types.SimpleNamespace(SUPERVISOR=Path('/unknown'), SUPERVISOR_SHA='0' * 64,
                                      read=lambda _: b'foreign', digest=lambda _: '1' * 64)
        with mock.patch.object(M.os, 'open', side_effect=AssertionError('log must not open')):
            result = M.transport_telemetry(types.SimpleNamespace(require=require), {'helper': helper})
        self.assertEqual(result['status'], 'UNAVAILABLE')
        self.assertEqual(result['reason'], 'HOLD_TEST_TRANSPORT_SUPERVISOR_PIN')

    def test_installer_pin_and_optional_telemetry_are_the_only_proof_delta(self):
        old = (HERE / 'owner_qwen_revision_observe.py').read_bytes()
        self.assertEqual(hashlib.sha256(old).hexdigest(), '5e2946fe9282e1a6c8a89123674b26cf0d2a90cc7995d551c3b09d058d14f026')
        tree = ast.parse(RAW)
        class RemoveOptional(ast.NodeTransformer):
            def visit_Import(self, node):
                return None if len(node.names) == 1 and node.names[0].name in {'configparser', 'math', 'stat'} else node
            def visit_FunctionDef(self, node):
                return None if node.name in {'transport_events', 'transport_telemetry'} else self.generic_visit(node)
            def visit_Assign(self, node):
                if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id == 'INSTALLER_SHA':
                    node.value = ast.Constant('2dd28da0d4e90614dbc168e0d921022c2b95061d08e21b2f76394f2f6280c468')
                if len(node.targets) == 1 and isinstance(node.targets[0], ast.Subscript):
                    target = node.targets[0]
                    if isinstance(target.value, ast.Name) and target.value.id == 'value' and isinstance(target.slice, ast.Constant) and target.slice.value == 'transport_telemetry':
                        return None
                return node
        self.assertEqual(ast.dump(RemoveOptional().visit(tree), include_attributes=False),
                         ast.dump(ast.parse(old), include_attributes=False))
        self.assertEqual(M.INSTALLER_SHA, '4be67c1d30d9513c96a3164c02e70056c47004922bbd3398cbc5e463f820f25d')


if __name__ == '__main__':
    unittest.main()
