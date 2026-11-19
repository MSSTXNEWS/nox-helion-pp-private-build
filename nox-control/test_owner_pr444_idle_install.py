import base64
import hashlib
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / 'owner_native_deploy.py'
SPEC = importlib.util.spec_from_file_location('owner_native_deploy', ENTRY)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class PayloadTests(unittest.TestCase):
    def bundle(self):
        names = {
            'owner_subagent_dispatcher.py': ROOT / 'systemic_relay_20261118/runtime/owner_subagent_dispatcher.py',
            'owner_subagent_processes.py': ROOT / 'systemic_relay_20261118/runtime/owner_subagent_processes.py',
            'owner_subagent_instruction_truth.py': ROOT / 'systemic_relay_20261118/runtime/owner_subagent_instruction_truth.py',
        }
        result = {}
        for name, path in names.items():
            raw = path.read_bytes()
            pin = hashlib.sha256(raw).hexdigest()
            result[name] = {'content': base64.b64encode(raw).decode('ascii'), 'sha256': pin}
        return result

    def test_exact_reviewed_payload_is_accepted(self):
        decoded = MOD.decode_bundle(self.bundle())
        self.assertEqual(set(decoded), set(MOD.ASSET_SHA256))
        self.assertEqual({name: hashlib.sha256(raw).hexdigest() for name, raw in decoded.items()},
                         MOD.ASSET_SHA256)

    def test_extra_payload_file_is_rejected(self):
        bundle = self.bundle()
        bundle['unreviewed.py'] = {'content': '', 'sha256': '0' * 64}
        with self.assertRaisesRegex(MOD.Hold, 'BUNDLE_FILE_SET'):
            MOD.decode_bundle(bundle)

    def test_changed_runtime_bytes_are_rejected(self):
        bundle = self.bundle()
        key = 'owner_subagent_processes.py'
        raw = b'# changed'
        bundle[key] = {'content': base64.b64encode(raw).decode('ascii'),
                       'sha256': MOD.ASSET_SHA256[key]}
        with self.assertRaisesRegex(MOD.Hold, 'BUNDLE_CONTENT_PIN'):
            MOD.decode_bundle(bundle)


class GateTests(unittest.TestCase):
    def gate(self):
        return {
            'owner_authenticated': True, 'request_id': '12345', 'source_sha': 'a' * 40,
            'observed_at': 100.0, 'owner_lock_held': True, 'stop_flags_clear': True,
            'queue_claims_clear': True, 'pool_idle': True, 'service': MOD.SERVICE,
            'pid': 123, 'start_ticks': 456, 'pgrp': 123,
            'service_config_sha256': 'b' * 64, 'pgid_members_exact': True,
            'signal_mode': 'SINGLE_PID_SIGTERM_NO_FALLBACK',
        }

    def test_fresh_owner_gate_is_accepted(self):
        self.assertEqual(MOD.validate_gate(self.gate(), now=110), self.gate())

    def test_missing_owner_lock_holds(self):
        gate = self.gate()
        gate['owner_lock_held'] = False
        with self.assertRaisesRegex(MOD.Hold, 'OWNER_LOCK_OR_STOP'):
            MOD.validate_gate(gate, now=110)

    def test_stale_gate_holds(self):
        with self.assertRaisesRegex(MOD.Hold, 'GATE_STALE'):
            MOD.validate_gate(self.gate(), now=131)

    def test_unproven_process_group_holds(self):
        gate = self.gate()
        gate['pgid_members_exact'] = False
        with self.assertRaisesRegex(MOD.Hold, 'SERVICE_SCOPE'):
            MOD.validate_gate(gate, now=110)

    def test_source_contains_no_kill_or_group_signal_fallback(self):
        source = ENTRY.read_text()
        self.assertNotIn('SIGKILL', source)
        self.assertNotIn('killpg', source)
        self.assertIn('os.kill(old_identity[\'pid\'], signal.SIGTERM)', source)


if __name__ == '__main__':
    unittest.main()
