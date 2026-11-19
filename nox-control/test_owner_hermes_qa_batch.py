"""Small synthetic children only; no native model, browser, service or chmod."""
import base64
from contextlib import ExitStack, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import owner_hermes_qa_batch as batch


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.context = {'request': '12345', 'source_sha': 'a' * 40}
        self.phases = [dict(row) for row in batch.PHASES]
        self.sources = {}
        self.stack.enter_context(patch.object(batch, 'STOP_PATHS', ()))
        self.install_sources()

    def rows(self, index, *, success=True):
        phase = self.phases[index]
        final = {'schema': phase['schema'], **self.context,
                 'state': phase['success_state'] if success else 'HOLD',
                 'reason': None if success else 'HOLD_SYNTHETIC',
                 'full_current_ssd_sha_verified': success, 'permissions_verified': True,
                 'qa_acceptance_verified': success, 'post_qa_runtime_identity_verified': True,
                 'qa_returncode': 0 if success else 2}
        if index == 0:
            return [{'kind': phase['final_kind'], 'data': final}]
        return [{'kind': 'browser_runtime_permissions', 'data': {'state': 'PERMISSIONS_ONLY'}},
                {'kind': 'browser_stream_only_receipt', 'data': {**self.context,
                 'state': 'STREAM_ONLY_ACCEPTED' if success else 'HOLD',
                 'stream_only_acceptance_verified': success}},
                {'kind': phase['final_kind'], 'data': final}]

    def source(self, index, *, success=True, extra='', markers=None, rows=None, code=None):
        rows = self.rows(index, success=success) if rows is None else rows
        markers = ([True] * (index + 1) if success else [False]) if markers is None else markers
        code = (0 if success else 2) if code is None else code
        return ("import json,os,sys,signal,time,subprocess\n"
                "assert 'site' not in sys.modules\n"
                "assert signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0)\n"
                "assert os.environ['NOX_OWNER_REQUEST_ID']=='12345'\n"
                "assert os.environ.get('SYNTHETIC_PRIVATE_ENV') is None\n"
                "assert isinstance(__NOX_BUNDLE_JSON__,dict)\n"
                "print('PRIVATE_STDERR',file=sys.stderr)\n" + extra +
                ''.join('print(' + repr('NOX_MAINT_REPAIR=' + json.dumps(row)) + ',flush=True)\n' for row in rows) +
                ''.join('print(' + repr('NOX_MAINT_REPAIR_COMPLETE=' + str(value).lower()) + ',flush=True)\n' for value in markers) +
                'raise SystemExit(' + str(code) + ')\n').encode()

    def install_sources(self, updates=None):
        if not self.sources:
            for index, phase in enumerate(self.phases):
                self.sources[phase['entry']] = self.source(index)
                for name in phase['dependencies']:
                    self.sources[name] = b'# synthetic pinned dependency\n'
        self.sources.update(updates or {})
        pins = {name: hashlib.sha256(raw).hexdigest() for name, raw in self.sources.items()}
        bundle = {name: base64.b64encode(raw).decode() for name, raw in self.sources.items()}
        for name, value in {'PHASES': tuple(self.phases), 'PINS': pins, 'BUNDLE': bundle}.items():
            self.stack.enter_context(patch.object(batch, name, value))
        return bundle

    def test_real_isolated_children_no_private_env_or_stderr_and_one_global_marker(self):
        output = io.StringIO()
        with patch.dict(os.environ, {'NOX_OWNER_REQUEST_ID': '12345', 'NOX_OWNER_SOURCE_SHA': 'a' * 40,
                                     'SYNTHETIC_PRIVATE_ENV': 'PRIVATE_SECRET'}), redirect_stdout(output):
            self.assertEqual(batch.main(), 0)
        text = output.getvalue()
        self.assertEqual(text.count('NOX_MAINT_REPAIR_COMPLETE='), 1)
        self.assertTrue(text.endswith('NOX_MAINT_REPAIR_COMPLETE=true\n'))
        self.assertNotIn('PRIVATE_SECRET', text); self.assertNotIn('PRIVATE_STDERR', text)

    def test_hermes_hold_does_not_block_actual_second_phase(self):
        self.install_sources({self.phases[0]['entry']: self.source(0, success=False)})
        rows, result = batch.execute(self.context)
        self.assertFalse(result['success']); self.assertTrue(result['phases'][1]['success'])
        self.assertEqual(len(rows), 4); self.assertEqual(result['verified_phase_count'], 1)

    def test_source_pin_failure_remains_local_to_phase(self):
        bundle = self.install_sources()
        bundle[self.phases[0]['dependencies'][0]] = base64.b64encode(b'raise AssertionError()').decode()
        rows, result = batch.execute(self.context)
        self.assertIn('SOURCE_PIN', result['phases'][0]['reason'])
        self.assertTrue(result['phases'][1]['success']); self.assertEqual(len(rows), 3)

    def test_permissions_and_nested_true_marker_cannot_pass_failed_final_qa(self):
        rows = self.rows(1, success=False)
        self.install_sources({self.phases[1]['entry']: self.source(1, rows=rows, code=0, markers=[True, True])})
        _, result = batch.execute(self.context)
        self.assertFalse(result['success']); self.assertFalse(result['phases'][1]['success'])

    def test_accepted_final_without_actual_stream_receipt_is_not_success(self):
        self.install_sources({self.phases[1]['entry']: self.source(1, rows=self.rows(1)[::2])})
        _, result = batch.execute(self.context)
        self.assertFalse(result['phases'][1]['success'])

    def test_wrong_context_or_false_completion_never_passes(self):
        for kind in ('context', 'marker'):
            with self.subTest(kind=kind):
                rows = self.rows(0)
                if kind == 'context': rows[0]['data']['request'] = '999'
                raw = b'\n'.join([b'NOX_MAINT_REPAIR=' + json.dumps(rows[0]).encode(),
                    b'NOX_MAINT_REPAIR_COMPLETE=' + (b'false' if kind == 'marker' else b'true')])
                _, result = batch.parse_output(raw, self.phases[0], 0, self.context)
                self.assertFalse(result['success'])

    def test_owner_stop_is_latched_even_if_later_flag_disappears(self):
        rows = self.rows(0, success=False); rows[0]['data']['reason'] = 'HOLD_HERMES_PREFLIGHT_OWNER_STOP'
        self.install_sources({self.phases[0]['entry']: self.source(0, rows=rows, success=False)})
        _, result = batch.execute(self.context)
        self.assertTrue(result['owner_stop_latched'])
        self.assertEqual(result['phases'][1]['state'], 'SKIPPED_OWNER_STOP')

    def test_unknown_stdout_suppressed_safe_rows_preserved(self):
        self.install_sources({self.phases[0]['entry']: self.source(0, extra="print('PRIVATE_UNKNOWN_STDOUT')\n")})
        rows, result = batch.execute(self.context)
        self.assertFalse(result['success']); self.assertEqual(len(rows), 4)
        self.assertNotIn('PRIVATE_UNKNOWN_STDOUT', json.dumps((rows, result)))

    def test_timeout_first_phase_still_runs_second(self):
        self.phases[0]['timeout'] = .15
        self.install_sources({self.phases[0]['entry']: self.source(0, extra='time.sleep(30)\n')})
        _, result = batch.execute(self.context)
        self.assertFalse(result['phases'][0]['success']); self.assertTrue(result['phases'][1]['success'])
        self.assertIn('CHILD_TIMEOUT', result['phases'][0]['reason'])

    def test_stop_cleans_owned_session_when_leader_exits_and_grandchild_ignores_term(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'pids.json'
            grandchild = 'import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(60)'
            leader = ('import subprocess,sys,os,json,time\n'
                      'p=subprocess.Popen([sys.executable,"-c",' + repr(grandchild) + '])\n'
                      'open(' + repr(str(marker)) + ',"w").write(json.dumps([os.getpid(),p.pid]))\n'
                      'time.sleep(60)\n')
            extra = 'p=subprocess.Popen([sys.executable,"-c",' + repr(leader) + '],start_new_session=True)\ntime.sleep(60)\n'
            self.install_sources({self.phases[0]['entry']: self.source(0, extra=extra)})
            # The synthetic marker is only a local STOP trigger for this test.
            with patch.object(batch, 'stop_present', side_effect=lambda: marker.exists()):
                _, result = batch.execute(self.context)
            pids = json.loads(marker.read_text())
            for pid in pids:
                path = Path('/proc') / str(pid) / 'stat'
                self.assertTrue(not path.exists() or path.read_bytes().split(b') ', 1)[1].startswith(b'Z '))
            detail = result['phases'][0]['child_cleanup']
            self.assertEqual(detail['cleanup_targets'], 1); self.assertEqual(detail['cleanup_unverified'], 0)
            self.assertEqual(result['phases'][1]['state'], 'SKIPPED_OWNER_STOP')


class FrozenClosureTests(unittest.TestCase):
    def test_all_nine_actual_source_pins_and_phase_closure_without_running_them(self):
        here = Path(__file__).parent
        bundle = {name: base64.b64encode((here / name).read_bytes()).decode() for name in batch.PINS}
        with patch.object(batch, 'BUNDLE', bundle):
            for phase in batch.PHASES:
                value = json.loads(batch.payload(phase))
                self.assertEqual(set(value['bundle']), set(phase['dependencies']))
        self.assertEqual(len(bundle), 9)

    def test_global_operator_bundle_macro_has_one_occurrence_and_child_still_compiles(self):
        source = Path(batch.__file__).read_text()
        self.assertEqual(source.count('__NOX_BUNDLE_JSON__'), 1)
        scope = {'__name__': 'fixture_only'}
        exec(compile(source.replace('__NOX_BUNDLE_JSON__', json.dumps({'synthetic': 'value'})), '<fixture>', 'exec'), scope)
        compile(scope['CHILD'], '<child>', 'exec')
        self.assertEqual(scope['BUNDLE'], {'synthetic': 'value'})


if __name__ == '__main__': unittest.main()
