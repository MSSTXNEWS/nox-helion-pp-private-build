"""Synthetic child processes only; never call either native probe."""
import base64
from contextlib import ExitStack, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import time
import unittest
from unittest.mock import patch

import owner_log_browser_readonly_batch as batch


class ReadonlyBatchTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.context = {'request': '12345', 'source_sha': 'a' * 40}
        self.phases = [dict(row) for row in batch.PHASES]
        self.sources = {}
        self.install_sources()

    def source(self, index, *, code=0, gate=True, extra='', delayed=False, marker=None):
        phase = self.phases[index]
        row = {'kind': phase['kinds'][0], 'data': {'schema': phase['schema'],
            'state': phase['success_state'] if code == 0 else 'READ_ONLY_OBSERVATION_HELD',
            'reason': None if code == 0 else 'HOLD_SYNTHETIC',
            'original_runtime_gate_passes': gate, 'selected_count': 3, 'full_stable_estimate_count': 3}}
        return ("import json,os,sys,signal,time\n"
                "assert 'site' not in sys.modules\n"
                "assert signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0)\n"
                "assert os.environ['NOX_OWNER_REQUEST_ID']=='12345'\n"
                "assert os.environ.get('SYNTHETIC_PRIVATE_ENV') is None\n"
                "assert isinstance(__NOX_BUNDLE_JSON__,dict)\n"
                "print('PRIVATE_STDERR',file=sys.stderr)\n" + extra +
                ("time.sleep(2)\n" if delayed else '') +
                'print(' + repr('NOX_MAINT_REPAIR=' + json.dumps(row)) + ',flush=True)\n' +
                'print(' + repr('NOX_MAINT_REPAIR_COMPLETE=' + (str(code == 0).lower() if marker is None else marker)) + ',flush=True)\n' +
                'raise SystemExit(' + str(code) + ')\n').encode()

    def install_sources(self, updates=None):
        if not self.sources:
            for i, phase in enumerate(self.phases):
                self.sources[phase['entry']] = self.source(i)
                for name in phase['dependencies']:
                    self.sources[name] = b'# synthetic pinned dependency\n'
        self.sources.update(updates or {})
        pins = {name: hashlib.sha256(raw).hexdigest() for name, raw in self.sources.items()}
        bundle = {name: base64.b64encode(raw).decode() for name, raw in self.sources.items()}
        for key, value in {'PHASES': tuple(self.phases), 'PINS': pins, 'BUNDLE': bundle}.items():
            self.stack.enter_context(patch.object(batch, key, value))
        return bundle

    def test_isolated_children_valid_context_no_private_environment_or_stderr(self):
        with patch.dict(os.environ, {'SYNTHETIC_PRIVATE_ENV': 'SECRET'}, clear=False):
            rows, result = batch.execute(self.context)
        self.assertTrue(result['success'])
        self.assertEqual(result['successful_probe_count'], 2)
        self.assertEqual(len(rows), 2)
        self.assertNotIn('SECRET', json.dumps(result))
        self.assertNotIn('PRIVATE_STDERR', json.dumps(rows))
        self.assertEqual(result['source_or_state_files_written'], 0)

    def test_first_hold_does_not_suppress_second_and_one_aggregate_marker(self):
        self.install_sources({self.phases[0]['entry']: self.source(0, code=2)})
        text = io.StringIO()
        with patch.dict(os.environ, {'NOX_OWNER_REQUEST_ID': '12345', 'NOX_OWNER_SOURCE_SHA': 'a' * 40}), redirect_stdout(text):
            code = batch.main()
        output = text.getvalue()
        self.assertEqual(code, 2)
        self.assertIn('HOLD_SYNTHETIC', output)
        self.assertIn('RUNTIME_METADATA_OBSERVED', output)
        self.assertEqual(output.count('NOX_MAINT_REPAIR_COMPLETE='), 1)
        self.assertTrue(output.endswith('NOX_MAINT_REPAIR_COMPLETE=false\n'))

    def test_browser_failed_gate_is_explicit_successful_observation_not_readiness(self):
        self.install_sources({self.phases[1]['entry']: self.source(1, gate=False)})
        rows, result = batch.execute(self.context)
        self.assertTrue(result['success'])
        self.assertFalse(result['original_browser_runtime_gate_passes'])
        self.assertEqual(result['state'], 'READ_ONLY_PROBES_COMPLETED_WITH_OBSERVED_HOLDS')
        self.assertIn('ORIGINAL_BROWSER_RUNTIME_GATE_HELD', result['observed_holds'])

    def test_timeout_first_child_still_allows_second_without_partial_claim(self):
        self.phases[0]['timeout'] = .04
        self.install_sources({self.phases[0]['entry']: self.source(0, delayed=True)})
        started = time.monotonic()
        rows, result = batch.execute(self.context)
        self.assertFalse(result['success'])
        self.assertEqual(result['phases'][0]['state'], 'PROBE_TIMED_OUT')
        self.assertTrue(result['phases'][1]['success'])
        self.assertEqual([row['kind'] for row in rows], ['browser_runtime_inspect'])
        self.assertLess(time.monotonic() - started, 2)

    def test_dependency_pin_failure_does_not_execute_first_or_block_second(self):
        bundle = self.install_sources()
        bundle[self.phases[0]['dependencies'][0]] = base64.b64encode(b'raise RuntimeError("BAD")').decode()
        rows, result = batch.execute(self.context)
        self.assertIn('SOURCE_PIN', result['phases'][0]['reason'])
        self.assertTrue(result['phases'][1]['success'])
        self.assertEqual(len(rows), 1)

    def test_unexpected_private_stdout_is_never_relayed_as_safe_record(self):
        self.install_sources({self.phases[0]['entry']: self.source(0, extra="print('PRIVATE_RAW_SECRET')\n")})
        rows, result = batch.execute(self.context)
        self.assertFalse(result['success'])
        self.assertFalse(result['phases'][0]['protocol_valid'])
        self.assertNotIn('PRIVATE_RAW_SECRET', json.dumps((rows, result)))

    def test_zero_exit_with_false_completion_cannot_inflate_aggregate(self):
        self.install_sources({self.phases[0]['entry']: self.source(0, marker='false')})
        _, result = batch.execute(self.context)
        self.assertFalse(result['success'])
        self.assertEqual(result['successful_probe_count'], 1)


class FrozenClosureTests(unittest.TestCase):
    def test_all_four_frozen_sources_match_without_running_probes(self):
        here = Path(__file__).parent
        bundle = {name: base64.b64encode((here / name).read_bytes()).decode() for name in batch.PINS}
        with patch.object(batch, 'BUNDLE', bundle):
            for phase in batch.PHASES:
                value = json.loads(batch.payload(phase))
                self.assertEqual(set(value['bundle']), set(phase['dependencies']))

    def test_operator_bundle_token_substitution_preserves_child_script(self):
        source = Path(batch.__file__).read_text()
        self.assertEqual(source.count('__NOX_BUNDLE_JSON__'), 1)
        patched = source.replace('__NOX_BUNDLE_JSON__', json.dumps({'synthetic': 'data'}))
        scope = {'__name__': 'not_main'}
        exec(compile(patched, '<fixture>', 'exec'), scope)
        self.assertEqual(scope['BUNDLE'], {'synthetic': 'data'})
        compile(scope['CHILD'], '<child-fixture>', 'exec')


if __name__ == '__main__':
    unittest.main()
