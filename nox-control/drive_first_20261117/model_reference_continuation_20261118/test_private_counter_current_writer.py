"""One independent TempFS regression; no native IO or HTTP."""
import contextlib
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'final_inputs'))
import model_reference_changed_path_qa as qa
from p0_witness_protocol import Hold


class CurrentWriterPrivateCounterTest(unittest.TestCase):
    def test_private_legacy_extra_then_late_current_lifetime_drift_prevents_send_and_replay(self):
        prior = (HERE / 'final_inputs/inputs/ACTUAL_PRIOR_OUTCOME_CANONICAL.json').read_bytes()
        self.assertEqual(qa.digest(prior), 'f0224c15acf37aaad4b45380ce174a27ae2acbafbdf361f036f07eca846e4fd9')
        arbiter_bytes = (HERE / 'final_inputs/inputs/actual_arbiter_source.py').read_bytes()
        self.assertEqual(qa.digest(arbiter_bytes), '4c9df9bbdaa2d788766090b466e3aff226d3c214ce936ac1559e7856a9190be0')
        with tempfile.TemporaryDirectory() as directory, contextlib.ExitStack() as stack:
            root = Path(directory)
            state, scripts, status, logs = [root / n for n in ('state', 'scripts', 'status', 'logs')]
            for p in (state, scripts, status, logs): p.mkdir(mode=0o700)
            priority = state / 'priority'; priority.mkdir(mode=0o700)
            arbiter = scripts / 'nox_priority_arbiter.py'; arbiter.write_bytes(arbiter_bytes); arbiter.chmod(0o775)
            log = logs / 'proxy.log'; log.write_bytes(b''); log.chmod(0o664)
            lease = state / 'owner_maintenance.lock'; lease.write_bytes(b''); lease.chmod(0o600)
            lock = {'dev': lease.stat().st_dev, 'ino': lease.stat().st_ino}
            counter = status / 'chat_state.json'
            raw = b'{"inflight":9,"last_ts":1,"writer":null,"activity_schema":null,"legacy_private":{"opaque":"INDEPENDENT_SYNTHETIC_PRIVATE_735"}}\n'
            counter.write_bytes(raw); counter.chmod(0o600)
            old = state / qa.JOURNAL; old.mkdir(mode=0o700)
            reservation = {'request': qa.PRIOR_REQUEST, 'source_sha': qa.PRIOR_SOURCE,
                'nonce': 'a' * 32, 'install_request': qa.RELEASE['install_request'],
                'dialog_id': qa.DIALOG, 'automatic_retry_allowed': False}
            for name, content in [('outcome.json', prior), ('reservation.json', qa.canonical(reservation))]:
                p = old / name; p.write_bytes(content); p.chmod(0o600)
            originals = {n: ((old/n).read_bytes(), qa.ZeroSendContinuation.file_identity((old/n).stat()))
                         for n in ('outcome.json', 'reservation.json')}
            for name, value in [('ROOT', root), ('STATE', state), ('SCRIPTS', scripts)]:
                stack.enter_context(patch.object(qa.native, name, value))
            stack.enter_context(patch.object(qa, 'COUNTER', counter))
            stack.enter_context(patch.object(qa.native, 'global_stop_guard', return_value=None))
            current = {'pid': 3648425, 'start_ticks': 175058217, 'state': 'S'}
            self.assertEqual(current['pid'], qa.RELEASE['runtime_identity']['pid'])
            self.assertEqual(current['start_ticks'], qa.RELEASE['runtime_identity']['start_ticks'])
            seen = []
            def process(pid, *, details):
                self.assertEqual(pid, 3648425); self.assertFalse(details)
                seen.append(pid); return dict(current)
            stack.enter_context(patch.object(qa.native, 'process', side_effect=process))
            clock = {'now': time.time(), 'elapsed': 0.0, 'login': None}
            def update_priority():
                active = clock['login'] is not None and clock['now'] - clock['login'] < 180
                stamp = None if clock['login'] is None else datetime.fromtimestamp(
                    clock['login'], timezone(timedelta(hours=1))).strftime('%Y-%m-%d %H:%M:%S %Z')
                values = {'CHAT_ACTIVE': b'1' if active else b'0', 'MODE': b'ACTIVE' if active else b'IDLE',
                    'status.json': qa.canonical({'mode': 'ACTIVE' if active else 'IDLE', 'train_pause': active,
                                               'idle_threshold_min': 3, 'last_owner_chat': stamp})}
                for n, value in values.items():
                    p = priority/n; p.write_bytes(value); p.chmod(0o600); os.utime(p, (clock['now'], clock['now']))
            update_priority()
            def sleep(seconds):
                clock['now'] += seconds; clock['elapsed'] += seconds; update_priority()
            idle = []
            def owner_idle():
                self.assertEqual((priority/'CHAT_ACTIVE').read_bytes(), b'0')
                self.assertEqual((priority/'MODE').read_bytes(), b'IDLE')
                idle.append(clock['elapsed']); return {'fixture_idle': True}
            stack.enter_context(patch.object(qa.native, 'owner_idle', side_effect=owner_idle))
            journal = qa.ZeroSendContinuation('9001', 'c'*40)
            stack.callback(journal.close_prior)
            journal.preflight()
            baseline, projection = qa.counter_snapshot()
            self.assertEqual(baseline, raw)
            self.assertEqual(projection['extra_key_count'], 3)
            self.assertTrue(projection['writer_key_present'])
            self.assertTrue(projection['activity_schema_key_present'])
            self.assertNotIn('legacy_private', json.dumps(projection))
            self.assertNotIn('INDEPENDENT_SYNTHETIC_PRIVATE_735', json.dumps(projection))
            report = {}
            waiter = qa.LoginIdleWait(qa.native, qa.document, qa.counter_snapshot, baseline,
                {'process': dict(current)}, lock, report, clock=lambda: clock['now'],
                monotonic=lambda: clock['elapsed'], sleep=sleep)
            stack.callback(waiter.close)
            client = Mock()
            with journal:
                waiter.capture()
                clock['login'] = int(clock['now'])
                stamp = datetime.fromtimestamp(clock['login'], timezone.utc).strftime('%Y-%m-%d %H:%M:%S %z')
                with log.open('ab') as output: output.write((stamp+' chat_login_ok ip=127.0.0.1\n').encode())
                update_priority()
                waiter.wait()
                self.assertEqual(idle, [182.0])
                evidence = qa.write_counter_evidence(journal, 'counter_before.json', baseline, projection)
                private_file = journal.path / 'counter_before.json'
                self.assertEqual(json.loads(private_file.read_bytes())['raw_utf8'].encode(), raw)
                self.assertEqual(private_file.stat().st_mode & 0o777, 0o600)
                self.assertEqual(private_file.stat().st_nlink, 1)
                self.assertTrue(evidence['readback_exact'])
                self.assertNotIn('INDEPENDENT_SYNTHETIC_PRIVATE_735', json.dumps(evidence))
                current['start_ticks'] += 1
                with self.assertRaisesRegex(Hold, 'HOLD_PROXY_LIFETIME_DURING_IDLE_WAIT'):
                    waiter.final_check()
                    journal.send(client)
                client.request.assert_not_called()
                self.assertFalse((journal.path/'model_post_intent.json').exists())
                self.assertEqual(idle, [182.0])
            self.assertGreater(len(seen), 180)
            again = qa.ZeroSendContinuation('9002', 'd'*40)
            stack.callback(again.close_prior)
            with self.assertRaisesRegex(Hold, 'HOLD_CONTINUATION_ALREADY_RESERVED_NO_RETRY'):
                again.preflight()
            for n, expected in originals.items():
                self.assertEqual(((old/n).read_bytes(), qa.ZeroSendContinuation.file_identity((old/n).stat())), expected)
            self.assertEqual(counter.read_bytes(), raw)


if __name__ == '__main__':
    unittest.main()
