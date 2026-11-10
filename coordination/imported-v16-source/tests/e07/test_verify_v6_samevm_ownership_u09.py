"""Synthetic negative regressions; no physical E07 or release claim."""
import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[2] / 'coordination/e07/verify_v6_samevm_ownership_u09.py'
spec = importlib.util.spec_from_file_location('u09_v6_chain', PATH)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def fixtures():
    sha = 'a' * 64
    p = dict(schema='NOX-E06-ONEHOST-DIAGNOSTIC-NSIS-v1',
             source_commit_sha1=gate.SOURCE, installer_sha256=gate.SETUP,
             installer_bytes=169612753, python_backend_sha256=sha, release_accepted=False)
    u = dict(schema='NOX-E07-FULL-D02-UIA-v1', source_sha=gate.SOURCE,
             setup_sha256=gate.SETUP, build_id=gate.BUILD, five_uia='PASS',
             five_primary={'status': 'PASS', 'actions_invoked': 5},
             physical_setup_verified=True, release_accepted=False)
    q = dict(schema='nox.installed.qwen.e07-diagnostic.v1',
             installed_backend_sha256=sha, installed_native='LIVE_NONEMPTY_RESPONSE_VERIFIED',
             installed_native_generated_bytes=9, native_history_restart='PASS',
             sqlite_history_rows_after_restart=2, release_accepted=False)
    s = dict(schema='nox.native.active-stop.physical.v1', backend_sha256=sha,
             native_active_stop='PASS', native_stop_ack='PASS',
             interrupted_chat_terminal='NATIVE_CHAT_STOP',
             nonempty_deltas_before_stop=1, release_accepted=False)
    x = dict(schema='NOX-V6-U08-ORDERED-QWEN-THEN-E07-v1', source_sha=gate.SOURCE,
             setup_sha256=gate.SETUP, build_id=gate.BUILD,
             official_conservative_uninstall='PASS', install_root_absent=True,
             prior_rollback_slots_absent=True, original_native_data_sha256_unchanged=True,
             release_accepted=False)
    return p, u, q, s, x

class TestChain(unittest.TestCase):
    def test_accept_receipts_without_release_claim(self):
        r = gate.verify(*fixtures())
        self.assertEqual(r['receipt_identity_chain'], 'PASS')
        self.assertIs(r['same_windows_vm_proven_from_json'], False)
        self.assertEqual(r['independent_e07_10_10'], 'HOLD')
        self.assertIs(r['release_accepted'], False)

    def test_stop_from_different_backend_rejected(self):
        p, u, q, s, x = fixtures(); s['backend_sha256'] = 'b' * 64
        with self.assertRaisesRegex(gate.Hold, 'STOP_OWNER_BACKEND'):
            gate.verify(p, u, q, s, x)

    def test_different_qwen_backend_rejected(self):
        p, u, q, s, x = fixtures(); q['installed_backend_sha256'] = 'b' * 64
        with self.assertRaisesRegex(gate.Hold, 'QWEN_SQLITE_BACKEND'):
            gate.verify(p, u, q, s, x)

    def test_cross_setup_receipt_rejected(self):
        p, u, q, s, x = fixtures(); u['setup_sha256'] = 'b' * 64
        with self.assertRaisesRegex(gate.Hold, 'UIA_SETUP_IDENTITY'):
            gate.verify(p, u, q, s, x)

    def test_inflight_stream_required(self):
        p, u, q, s, x = fixtures(); s['nonempty_deltas_before_stop'] = 0
        with self.assertRaisesRegex(gate.Hold, 'STOP_OWNER_BACKEND'):
            gate.verify(p, u, q, s, x)

    def test_sqlite_true_not_count(self):
        p, u, q, s, x = fixtures(); q['sqlite_history_rows_after_restart'] = True
        with self.assertRaisesRegex(gate.Hold, 'QWEN_SQLITE_BACKEND'):
            gate.verify(p, u, q, s, x)

    def test_user_data_loss_rejected(self):
        p, u, q, s, x = fixtures(); x['original_native_data_sha256_unchanged'] = False
        with self.assertRaisesRegex(gate.Hold, 'NOLOSS_IDENTITY'):
            gate.verify(p, u, q, s, x)

    def test_fabricated_release_rejected(self):
        p, u, q, s, x = fixtures(); s['release_accepted'] = True
        with self.assertRaisesRegex(gate.Hold, 'STOP_OWNER_BACKEND'):
            gate.verify(p, u, q, s, x)

if __name__ == '__main__':
    unittest.main()
