"""Synthetic protocol, sequencing, and rollback signal tests; no native calls."""
import base64
import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import Mock, patch

import owner_storage_warm_batch as b

HERE = Path(__file__).parent
CONTEXT = {'request': '12345', 'source_sha': 'a' * 40}


def bundle():
    return {name: base64.b64encode((HERE / name).read_bytes()).decode() for name in b.PINS}


def builder_records():
    value = {'schema': b.BUILDER['schema'], **CONTEXT, 'state': b.BUILDER['state'],
        'acceptance': {'anonymous_http': 401, 'owner_http': 200, 'storage_counts': {'RAM': 2, 'SSD': 1}},
        'ram_duplicate_unlinked_bytes': 306787336, 'canonical_permission_after': 0o644,
        'canonical_full_sha256_verified': True, 'previous_ram_full_sha256_verified': True,
        'old_ram_receipt_unchanged': True, 'all_sidecars_preserved': True,
        'weights_merged': False, 'training_flags_modified': False, 'new_model_loaded': False,
        'unique_weight_content_removed': False, 'training_actions': 0}
    raw = b.encoded(value) + b'\n'
    return [{'kind': 'builder_cold_storage', 'data': value},
            {'kind': 'builder_cold_storage_context', 'data': {**CONTEXT, 'receipt_sha256': b.digest(raw), 'receipt_bytes': len(raw)}}], raw


def hermes_records():
    value = {'schema': b.HERMES['schema'], **CONTEXT, 'state': b.HERMES['state'],
        'full_ram_sha_verified': True, 'checkpoints_and_admission_unchanged': True,
        'own_ssd_payload_descriptors_closed': True, 'ssd_original_unlinked': True,
        'ram_is_durable_backup': False, 'training_or_service_actions': 0,
        'checkpoint_or_ledger_changes': 0, 'qwen_disk_rearm_space_observed': False}
    raw = b.encoded(value)
    return [{'kind': 'hermes_warm_move', 'data': {**value, 'final_receipt_sha256': b.digest(raw)}}], raw


def protocol(rows, marker=True):
    raw = b''.join(b'NOX_MAINT_REPAIR=' + b.encoded(row) + b'\n' for row in rows)
    return raw + b'NOX_MAINT_REPAIR_COMPLETE=' + str(marker).lower().encode() + b'\n'


class ProtocolTests(unittest.TestCase):
    def test_actual_closure_and_larger_measured_input_are_pinned(self):
        with patch.object(b, 'BUNDLE', bundle()): blobs = b.sources()
        source = b.child_bootstrap(blobs); compile(source, '<test-child>', 'exec')
        builder = b.payload(b.BUILDER, blobs); hermes = b.payload(b.HERMES, blobs)
        self.assertGreater(len(builder), 250000)
        self.assertLess(len(builder), b.INPUT_LIMIT)
        self.assertLess(len(hermes), b.INPUT_LIMIT)
        self.assertIn('owner_builder_drive_public_proof.json', json.loads(builder)['bundle'])
        self.assertIn('class Interrupted(RuntimeError)', source)
        changed = bundle(); changed['owner_builder_drive_public_proof.json'] = base64.b64encode(b'{}').decode()
        with patch.object(b, 'BUNDLE', changed), self.assertRaisesRegex(b.Hold, 'BUNDLE_PIN'): b.sources()

    def test_builder_rc_zero_without_http_storage_proof_is_not_accepted(self):
        rows, _ = builder_records()
        _, value = b.parse_output(protocol(rows), b.BUILDER, 0, CONTEXT)
        self.assertTrue(value['success'])
        rows[0]['data']['acceptance']['storage_counts'] = {'RAM': 3, 'SSD': 0}
        _, value = b.parse_output(protocol(rows), b.BUILDER, 0, CONTEXT)
        self.assertFalse(value['success'])
        rows, _ = builder_records()
        self.assertFalse(b.parse_output(protocol(rows), b.BUILDER, 2, CONTEXT)[1]['success'])
        self.assertFalse(b.parse_output(protocol(rows, False), b.BUILDER, 0, CONTEXT)[1]['success'])

    def test_private_receipt_must_match_exact_output_and_full_raw_hash(self):
        rows, raw = builder_records()
        with tempfile.TemporaryDirectory() as directory, patch.object(b, 'ROOT', Path(directory)):
            path = b.ROOT / 'state/owner_builder_cold_storage_12345.json'
            path.parent.mkdir(); path.write_bytes(raw); path.chmod(0o600)
            self.assertTrue(b.receipt_readback(rows, b.BUILDER, CONTEXT)['durable_receipt_verified'])
            path.write_bytes(raw.replace(b'12345', b'12346'))
            with self.assertRaisesRegex(b.Hold, 'DURABLE_RECEIPT_READBACK'): b.receipt_readback(rows, b.BUILDER, CONTEXT)

    def test_hermes_requires_full_proof_but_never_promotes_disk_rearm(self):
        rows, raw = hermes_records()
        self.assertTrue(b.parse_output(protocol(rows), b.HERMES, 0, CONTEXT)[1]['success'])
        with tempfile.TemporaryDirectory() as directory, patch.object(b, 'ROOT', Path(directory)):
            path = b.ROOT / 'state/owner_hermes_warm/12345/result.json'
            path.parent.mkdir(parents=True); path.write_bytes(raw); path.chmod(0o600)
            self.assertTrue(b.receipt_readback(rows, b.HERMES, CONTEXT)['durable_receipt_verified'])
        rows[0]['data']['own_ssd_payload_descriptors_closed'] = False
        self.assertFalse(b.parse_output(protocol(rows), b.HERMES, 0, CONTEXT)[1]['success'])

    def test_unknown_output_is_never_relayed_or_accepted(self):
        rows, _ = builder_records()
        parsed, result = b.parse_output(protocol(rows) + b'not-for-public-output\n', b.BUILDER, 0, CONTEXT)
        self.assertFalse(result['success']); self.assertEqual(parsed, rows)
        self.assertNotIn('not-for-public-output', json.dumps(result))
        with self.assertRaisesRegex(b.Hold, 'OUTPUT_BOUND'):
            b.parse_output(b'x' * (b.OUTPUT_LIMIT + 1), b.BUILDER, 0, CONTEXT)


class SequenceTests(unittest.TestCase):
    def setup_calls(self, *, builder=True, guard=True):
        calls = []
        def run(phase, *_):
            calls.append(phase['name'])
            ok = builder if phase['name'] == 'builder' else True
            return [], {'phase': phase['name'], 'success': ok, 'released_at': 123.0, 'captured_stdout_bytes': 0}
        def wait(after, deadline):
            calls.append('guard')
            self.assertEqual(after, 123.0)
            if not guard: raise b.Hold('WAIT_STORAGE_WARM_BATCH_NEW_GUARD_SAMPLE')
            return {'success': True}
        return calls, run, wait

    def run_fixture(self, run, wait):
        with patch.object(b, 'sources', return_value={}), patch.object(b, 'child_bootstrap', return_value='fixture'), \
             patch.object(b, 'payload', return_value=b'{}'), patch.object(b, 'stop_present', return_value=False), \
             patch.object(b, 'run_phase', side_effect=run), patch.object(b, 'fresh_guard', side_effect=wait):
            return b.execute(CONTEXT)[1]

    def test_hermes_only_after_builder_then_new_guard(self):
        calls, run, wait = self.setup_calls()
        value = self.run_fixture(run, wait)
        self.assertEqual(calls, ['builder', 'guard', 'hermes']); self.assertTrue(value['success'])
        self.assertFalse(value['trainer_started']); self.assertFalse(value['training_rearmed'])

    def test_builder_hold_skips_guard_and_hermes(self):
        calls, run, wait = self.setup_calls(builder=False)
        value = self.run_fixture(run, wait)
        self.assertEqual(calls, ['builder']); self.assertFalse(value['success'])
        self.assertEqual(value['phases'][1]['state'], 'SKIPPED_BUILDER_OR_FRESH_GUARD_NOT_VERIFIED')

    def test_no_fresh_guard_skips_hermes_even_after_storage_commit(self):
        calls, run, wait = self.setup_calls(guard=False)
        value = self.run_fixture(run, wait)
        self.assertEqual(calls, ['builder', 'guard']); self.assertFalse(value['success'])
        self.assertTrue(value['phases'][0]['success'])

    def test_stop_after_builder_never_launches_hermes(self):
        calls, run, wait = self.setup_calls()
        with patch.object(b, 'sources', return_value={}), patch.object(b, 'child_bootstrap', return_value='fixture'), \
             patch.object(b, 'payload', return_value=b'{}'), patch.object(b, 'run_phase', side_effect=run), \
             patch.object(b, 'fresh_guard', side_effect=wait), patch.object(b, 'stop_present', return_value=True):
            value = b.execute(CONTEXT)[1]
        self.assertEqual(calls, ['builder']); self.assertEqual(value['phases'][1]['state'], 'SKIPPED_OWNER_STOP')


class GuardTests(unittest.TestCase):
    def fixture(self, stamps):
        clock = {'mono': 0.0}
        timer = types.SimpleNamespace(monotonic=lambda: clock['mono'], time=lambda: 100.0,
            sleep=lambda seconds: clock.update(mono=clock['mono'] + seconds))
        checkpoint = {'pointer_sha256': b.TEN_POINTER}
        rows = [{'sampled_at': stamp, 'state': 'INHIBITED', 'checkpoint': checkpoint,
                 'policy_state': {'inhibit': True, 'reason': 'DISK_EARLY_MARGIN', 'last_successful_updates': 10}}
                for stamp in stamps]
        counter = [0]
        def previous(_):
            row = rows[min(counter[0], len(rows)-1)]; counter[0] += 1
            return row, 'b' * 64
        guard = types.SimpleNamespace(_IO_DEADLINE=types.SimpleNamespace(value=None),
            checked_config=Mock(return_value=({'policy': {'state_max_age_seconds': 30}}, b.GUARD_CONFIG_SHA)),
            context_evidence=Mock(return_value={'verified': True}), bindings=Mock(return_value={}),
            previous_state=previous, checkpoint_metadata=Mock(return_value=checkpoint), tick=Mock())
        return timer, guard

    def test_new_sample_required_and_legitimate_disk_inhibit_preserved(self):
        timer, guard = self.fixture([89, 99])
        with patch.object(b, 'time', timer), patch.object(b, 'load_guard', return_value=guard), \
             patch.object(b, 'stop_present', return_value=False):
            value = b.fresh_guard(90, 50)
        self.assertTrue(value['success']); self.assertEqual(value['observations'], 2)
        self.assertEqual(value['sampled_at'], 99); guard.tick.assert_not_called()
        self.assertIsNone(guard._IO_DEADLINE.value)

    def test_old_sample_never_becomes_new_after_wait(self):
        timer, guard = self.fixture([89])
        with patch.object(b, 'time', timer), patch.object(b, 'load_guard', return_value=guard), \
             patch.object(b, 'stop_present', return_value=False), self.assertRaisesRegex(b.Hold, 'NEW_GUARD_SAMPLE'):
            b.fresh_guard(90, 50)
        self.assertEqual(timer.monotonic(), 20); guard.tick.assert_not_called()

    def test_different_context_or_checkpoint_is_not_softened(self):
        timer, guard = self.fixture([99]); guard.checkpoint_metadata.return_value = {'pointer_sha256': '0' * 64}
        with patch.object(b, 'time', timer), patch.object(b, 'load_guard', return_value=guard), \
             patch.object(b, 'stop_present', return_value=False), self.assertRaisesRegex(b.Hold, 'GUARD_CHECKPOINT_CHANGED'):
            b.fresh_guard(90, 50)


class SignalTests(unittest.TestCase):
    def test_term_enters_exception_rollback_before_owned_child_cleanup(self):
        with patch.object(b, 'BUNDLE', bundle()): source = b.child_bootstrap(b.sources())
        program = ("import json,time\ntry:\n print('READY',flush=True)\n time.sleep(30)\n"
            "except Exception:\n time.sleep(.05)\n print('ROLLBACK_FINISHED',flush=True)\n raise SystemExit(2)\n")
        raw = b.encoded({'source': base64.b64encode(program.encode()).decode(), 'bundle': {}})
        proc = subprocess.Popen([sys.executable, '-I', '-S', '-B', '-c', source], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)
        try:
            proc.stdin.write(raw); proc.stdin.close(); proc.stdin = None
            with selectors.DefaultSelector() as selected:
                selected.register(proc.stdout, selectors.EVENT_READ)
                self.assertTrue(selected.select(3)); self.assertEqual(proc.stdout.readline(), b'READY\n')
            proc.send_signal(signal.SIGTERM)
            output, _ = proc.communicate(timeout=5)
            self.assertEqual(proc.returncode, 2)
            self.assertIn(b'ROLLBACK_FINISHED', output)
            self.assertIn(b'NOX_BATCH_CHILD_CONTROL=', output)
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL); proc.wait(timeout=2)

    def test_builder_rollback_receives_full_grace_without_early_kill(self):
        proc = Mock(pid=1234)
        proc.communicate.return_value = (b'finished', None)
        with patch.object(b, 'signal_owned') as signal_own:
            output, forced = b.finish_child(proc, (1, 2, 3, 4), b.BUILDER['grace_seconds'])
        self.assertEqual(output, b'finished'); self.assertFalse(forced)
        self.assertEqual(proc.communicate.call_args.kwargs['timeout'], 105)
        self.assertEqual(signal_own.call_count, 1)
        self.assertLessEqual(sum(p['soft_seconds'] + p['grace_seconds'] for p in (b.BUILDER, b.HERMES))
                             + b.GUARD_WAIT_SECONDS + 4, b.TOTAL_SECONDS)


if __name__ == '__main__': unittest.main()
