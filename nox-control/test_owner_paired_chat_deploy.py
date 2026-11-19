import ast
import base64
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'nox-control'))
import owner_native_operator as operator
import owner_paired_chat_deploy as route


class PairedChatDeployContractTests(unittest.TestCase):
    def test_exact_remote_source_commit_and_raw_sha256_pins(self):
        self.assertEqual(route.SOURCE_COMMIT, 'daf5077bf8f0573ca3a991e7ade9ab733e8195f5')
        self.assertEqual(operator.PAIRED_CHAT_SOURCE_COMMIT, route.SOURCE_COMMIT)
        expected = {
            'v135_js': (
                'coordination/onepass/nox-v135-resonance-owner-bridge.js',
                route.JS_BLOB,
                route.JS_SHA256,
            ),
            'v112_py': (
                'nox_runpod/teacher_mesh/v112/native_v29_full_bridge.py',
                route.PY_BLOB,
                route.PY_SHA256,
            ),
        }
        bundle = {}
        for key, (path, blob_pin, sha_pin) in expected.items():
            raw = subprocess.check_output(
                ['git', 'show', f'{route.SOURCE_COMMIT}:{path}'], cwd=ROOT)
            blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
            self.assertEqual(blob, blob_pin)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), sha_pin)
            self.assertIn(key, operator.PAIRED_CHAT_ASSETS)
            self.assertEqual(operator.PAIRED_CHAT_ASSETS[key][1:3], (blob_pin, sha_pin))
            bundle[key] = base64.b64encode(raw).decode('ascii')
        old_bundle = route.BUNDLE
        try:
            route.BUNDLE = bundle
            decoded = route.assets()
            self.assertEqual(decoded['v135_js'], subprocess.check_output(
                ['git', 'show', f'{route.SOURCE_COMMIT}:{expected["v135_js"][0]}'], cwd=ROOT))
            self.assertEqual(decoded['v112_py'], subprocess.check_output(
                ['git', 'show', f'{route.SOURCE_COMMIT}:{expected["v112_py"][0]}'], cwd=ROOT))
        finally:
            route.BUNDLE = old_bundle

    def test_owner_command_requires_exact_phase_and_both_apply_tokens(self):
        source_sha = 'a' * 40
        js_token = 'J' * 100
        py_token = 'P' * 100

        def run_command(body, mode, js='', py=''):
            with tempfile.TemporaryDirectory() as temp:
                event_path = Path(temp) / 'event.json'
                event_path.write_text(json.dumps({
                    'comment': {'id': 77, 'body': body, 'user': {'id': operator.OWNER_ID},
                                'author_association': 'OWNER'},
                    'sender': {'id': operator.OWNER_ID},
                    'repository': {'owner': {'id': operator.OWNER_ID}},
                    'issue': {'number': 256},
                }))
                env = {
                    'GITHUB_EVENT_PATH': str(event_path),
                    'GITHUB_REPOSITORY': operator.REPO,
                    'GITHUB_EVENT_NAME': 'issue_comment',
                    'NOX_PINNED_SOURCE_SHA': source_sha,
                    'NOX_PAIRED_CHAT_MODE': mode,
                    'NOX_EXPECTED_V135_TOKEN': js,
                    'NOX_EXPECTED_V112_TOKEN': py,
                }
                with patch.dict(os.environ, env, clear=False), patch.object(
                        operator.subprocess, 'check_output', return_value=source_sha + '\n'):
                    return operator.authorize_event('paired_chat_deploy')

        inspect = f'/nox-maintain {operator.INSTANCE} {source_sha} paired_chat_deploy inspect'
        apply = f'/nox-maintain {operator.INSTANCE} {source_sha} paired_chat_deploy apply {js_token} {py_token}'
        self.assertEqual(run_command(inspect, 'inspect'), 77)
        self.assertEqual(run_command(apply, 'apply', js_token, py_token), 77)
        with self.assertRaisesRegex(RuntimeError, 'HOLD_PAIRED_CHAT_PREIMAGE_TOKENS'):
            run_command(apply, 'apply', js_token, '')
        with self.assertRaisesRegex(RuntimeError, 'HOLD_EXACT_OWNER_COMMAND'):
            run_command(inspect + ' extra', 'inspect')

    def test_workflow_parser_accepts_only_exact_paired_phases(self):
        workflow = (ROOT / '.github/workflows/nox-owner-maintenance-command.yml').read_text()
        legacy_parser = next(line.strip() for line in workflow.splitlines() if 'm=re.fullmatch(' in line)
        paired_parser = next(line.strip() for line in workflow.splitlines() if 'paired=re.fullmatch(' in line)
        legacy_pattern = ast.literal_eval(ast.parse(legacy_parser).body[0].value.args[0])
        paired_pattern = ast.literal_eval(ast.parse(paired_parser).body[0].value.args[0])
        sha = 'a' * 40
        self.assertIsNotNone(re.fullmatch(
            legacy_pattern, f'/nox-maintain 60509551 {sha} audit'))
        self.assertIsNotNone(re.fullmatch(
            paired_pattern, f'/nox-maintain 60509551 {sha} paired_chat_deploy inspect'))
        self.assertIsNotNone(re.fullmatch(
            paired_pattern, f'/nox-maintain 60509551 {sha} paired_chat_deploy apply ' + 'J' * 100 + ' ' + 'P' * 100))
        self.assertIsNone(re.fullmatch(
            paired_pattern, f'/nox-maintain 60509551 {sha} paired_chat_deploy apply ' + 'J' * 100))
        self.assertIsNone(re.fullmatch(
            paired_pattern, f'/nox-maintain 60509551 {sha} paired_chat_deploy inspect extra'))

    def test_owner_inspect_workflow_does_not_capture_paired_inspect(self):
        workflow = (ROOT / '.github/workflows/nox-owner-native-inspect.yml').read_text()
        self.assertIn("!contains(github.event.comment.body, ' paired_chat_deploy inspect')", workflow)
        maintenance = (ROOT / '.github/workflows/nox-owner-maintenance-command.yml').read_text()
        self.assertIn("paired_chat_deploy inspect", maintenance)
        self.assertIn("steps.request.outputs.mode == 'inspect'", maintenance)

    def test_synthetic_apply_failure_with_uncertain_stop_never_claims_restored(self):
        # A stop timeout can leave Supervisor transitioning even before the
        # first file exchange. Such a state is not a positive restore receipt.
        for state in ('STARTING', 'STOPPING', 'RESTARTING', 'UNKNOWN'):
            with self.subTest(state=state), \
                    patch.object(route, 'owner_stop', return_value=False), \
                    patch.object(route, 'supervisor_state', return_value=(state, 123)), \
                    patch.object(route, 'process_start') as process_start, \
                    patch.object(route, 'health') as health:
                result = route.rollback_status(True, 'python /root/nox/scripts/chat_proxy.py')
                self.assertFalse(result['rollback_verified'])
                self.assertFalse(result['service_restored'])
                self.assertIsNone(result['service_restore_readback'])
                process_start.assert_not_called()
                health.assert_not_called()

    def test_slot_snapshot_requires_unique_ids_and_explicit_consistent_booleans(self):
        good = [{'id': index, 'is_processing': False} for index in range(6)]
        self.assertEqual(route.slot_projection(good)['busy'], 0)
        busy = [{'id': index, 'is_processing': index == 2} for index in range(6)]
        self.assertEqual(route.slot_projection(busy)['busy'], 1)
        for bad in (
            [{} for _ in range(6)],
            [{'id': index} for index in range(6)],
            [{'id': index, 'is_processing': 'false'} for index in range(6)],
            [{'id': index, 'is_processing': False, 'processing': True} for index in range(6)],
            [{'id': 0, 'is_processing': False} for _ in range(6)],
        ):
            with self.subTest(rows=bad):
                self.assertIsNone(route.slot_projection(bad))

    def test_admission_drain_absence_holds_before_any_stop(self):
        with self.assertRaisesRegex(RuntimeError, 'HOLD_PAIRED_CHAT_ADMISSION_DRAIN_PROVIDER_UNAVAILABLE'):
            route.require_chat_admission_drain()

    def test_unknown_or_transitioning_state_cannot_enter_file_rollback(self):
        argv = 'python /root/nox/scripts/chat_proxy.py'
        with patch.object(route, 'process_start', return_value=('different argv', '1234')), \
                patch.object(route, 'run_supervisor') as stop:
            for state in ('STARTING', 'STOPPING', 'RESTARTING', 'UNKNOWN', 'RUNNING'):
                with self.subTest(state=state), self.assertRaisesRegex(
                        RuntimeError, 'HOLD_PAIRED_CHAT_ROLLBACK_'):
                    route.prepare_service_for_file_rollback(state, 123, False, argv)
            stop.assert_not_called()
        with patch.object(route, 'process_start', return_value=(argv, '1234')), \
                patch.object(route, 'run_supervisor') as stop:
            self.assertTrue(route.prepare_service_for_file_rollback('STOPPING', 123, True, argv))
            stop.assert_called_once_with('stop')
        with self.assertRaisesRegex(RuntimeError, 'HOLD_PAIRED_CHAT_ROLLBACK_TERMINAL_STATE_HAS_PID'):
            route.prepare_service_for_file_rollback('STOPPED', 123, True, argv)

    def test_owner_lock_path_inode_is_rechecked_after_flock(self):
        held = SimpleNamespace(st_dev=1, st_ino=10, st_uid=0, st_gid=0,
                               st_mode=0o100600, st_nlink=1)
        replaced = SimpleNamespace(st_dev=1, st_ino=11, st_uid=0, st_gid=0,
                                   st_mode=0o100600, st_nlink=1)
        with patch.object(route.os, 'fstat', return_value=held), \
                patch.object(route.os, 'stat', return_value=replaced), \
                patch.object(route.fcntl, 'flock') as flock:
            with self.assertRaisesRegex(RuntimeError, 'HOLD_PAIRED_CHAT_OWNER_LOCK_PATH_REPLACED'):
                route.verify_owner_lock(4, 5)
            flock.assert_not_called()

    def test_service_restore_requires_fresh_stable_supervisor_and_health_readback(self):
        argv = 'python /root/nox/scripts/chat_proxy.py'
        with patch.object(route, 'owner_stop', side_effect=(False, False)), \
                patch.object(route, 'supervisor_state', side_effect=(('RUNNING', 321), ('RUNNING', 321))), \
                patch.object(route, 'process_start', return_value=(argv, '987654')), \
                patch.object(route, 'port_listening', return_value=True), \
                patch.object(route, 'health', return_value=True):
            result = route.rollback_status(True, argv)
        self.assertTrue(result['rollback_verified'])
        self.assertTrue(result['service_restored'])
        self.assertEqual(result['service_restore_readback'], {
            'state': 'RUNNING', 'pid': 321, 'start_ticks': '987654',
            'ports_listening': True, 'health': True})

    def test_service_restore_readback_rejects_pid_change_during_health_probe(self):
        argv = 'python /root/nox/scripts/chat_proxy.py'
        with patch.object(route, 'owner_stop', side_effect=(False, False)), \
                patch.object(route, 'supervisor_state', side_effect=(('RUNNING', 321), ('RUNNING', 322))), \
                patch.object(route, 'process_start', return_value=(argv, '987654')), \
                patch.object(route, 'port_listening', return_value=True), \
                patch.object(route, 'health', return_value=True):
            result = route.rollback_status(True, argv)
        self.assertFalse(result['rollback_verified'])
        self.assertFalse(result['service_restored'])
        self.assertIsNone(result['service_restore_readback'])


if __name__ == '__main__':
    unittest.main()
