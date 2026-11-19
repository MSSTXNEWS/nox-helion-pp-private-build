"""Focused passive phase evidence tests; no browser, network or native actions."""
import asyncio
import base64
import hashlib
import json
from pathlib import Path
import re
import textwrap
import time
import types
import unittest
import urllib.parse
from unittest.mock import patch

import owner_workspace_browser_acceptance as frozen
import owner_workspace_browser_acceptance_v2 as candidate

HERE = Path(__file__).resolve().parent
FILES = {name: HERE / name for name in candidate.PINS}
FILES['owner_browser_stream_only_entry.py'] = HERE / 'pinned/browser_normal_v1/owner_browser_stream_only_entry.py'
BUNDLE = {name: base64.b64encode(path.read_bytes()).decode() for name, path in FILES.items()}
ASSET = (HERE.parent / 'coordination/onepass/workspace-owner-capabilities.js').read_bytes()
PROJECTION = {'native_flag': True, 'workspace_native': True, 'ready_resolved': True,
    'ready_rejected': False, 'capability_schema': 'NOX_NATIVE_UI_WORKSPACE_V1',
    'settings': False, 'storage_scope': 'BROWSER_VISUAL_PREFS'}


class PhaseEvidenceTests(unittest.TestCase):
    def capture(self, *, fail=None, hang=None, payload=ASSET, projection=None):
        calls = []; deadlines = []; report = {}; frame = object()

        async def operation(label, value):
            calls.append(label)
            if fail == label:
                raise RuntimeError('private URL and body must not be exported')
            if hang == label:
                await asyncio.Event().wait()
            return value

        async def headers(): return await operation('headers', {'content-length': str(len(payload))})
        async def finished(): return await operation('finished', None)
        async def sizes(): return await operation('sizes', {'responseBodySize': len(payload)})
        async def body(): return await operation('body', payload)
        async def evaluate(value):
            self.assertEqual(value, frozen.WORKSPACE_JS)
            return await operation('ready', PROJECTION if projection is None else projection)

        async def wait_for(task, timeout):
            deadlines.append(timeout)
            # Preserve and assert requested bounds, but make deliberate hangs finite in this fixture.
            return await asyncio.wait_for(task, timeout={3: .01, 5: .03}[timeout])

        request = types.SimpleNamespace(method='GET', resource_type='script', frame=frame,
            redirected_from=None, sizes=sizes)
        asset = types.SimpleNamespace(request=request, url='http://192.0.2.1:8080' + frozen.ASSET_PATH,
            status=200, from_service_worker=False, all_headers=headers, finished=finished, body=body)
        namespace = {'asyncio': types.SimpleNamespace(wait_for=wait_for, CancelledError=asyncio.CancelledError),
            'urllib': urllib, 're': re, 'time': time, 'digest': lambda raw: hashlib.sha256(raw).hexdigest(),
            'origin': '192.0.2.1:8080', 'workspace_responses': [asset], 'report': report,
            'page': types.SimpleNamespace(main_frame=frame, evaluate=evaluate)}
        source = candidate.PHASE_HELPER + candidate.instrument_capture(frozen.WORKSPACE_CAPTURE, frozen.WORKSPACE_JS)
        exec(compile('async def run():\n' + textwrap.indent(textwrap.dedent(source), '    '),
            '<passive-workspace-fixture>', 'exec'), namespace)
        return namespace['run'], report, calls, deadlines

    def test_real_pinned_closure_compiles_without_changing_auth_request_or_cleanup_functions(self):
        with patch.object(candidate, 'BUNDLE', BUNDLE):
            actual = candidate.prepared()
        with patch.object(frozen, 'BUNDLE', BUNDLE):
            old = frozen.prepared()
        for name in ('request_gate', 'main', 'stop_owned_child', 'browser_source', 'child_program'):
            self.assertEqual(getattr(actual, name).__code__.co_code, getattr(old, name).__code__.co_code)
        self.assertEqual(actual.POLL_SECONDS, 32)
        for old_limit in ('timeout=20000', 'timeout=12000', 'timeout=3', 'timeout=5'):
            self.assertIn(old_limit, actual.PAGE_TAIL)
        self.assertEqual(actual.PAGE_TAIL.count("report['workspace_acceptance_verified']=True"), 1)
        self.assertIn('HOLD_WORKSPACE_BROWSER_LATE_DUPLICATE_ASSET', actual.PAGE_TAIL)
        self.assertEqual(actual.request_gate('POST', 'http://x/api/settings', 'x'), 'APPLICATION_MUTATION')
        program = actual.child_program(actual.sources())
        compile(program, '<passive-workspace-v2-child>', 'exec')
        self.assertIn('timeout=75', program.decode())
        self.assertEqual(hashlib.sha256(FILES[candidate.BASE].read_bytes()).hexdigest(), candidate.BASE_SHA)

    def test_success_records_real_await_sequence_without_new_calls_or_early_acceptance(self):
        run, report, calls, deadlines = self.capture(); asyncio.run(run())
        self.assertEqual(calls, ['headers', 'finished', 'sizes', 'body', 'ready'])
        self.assertEqual(deadlines, [5, 3])
        rows = report['workspace_diagnostics']['steps']
        self.assertEqual([r['phase'] for r in rows], ['ASSET_HEADERS', 'ASSET_FINISHED', 'ASSET_SIZES',
                                                     'ASSET_BODY', 'WORKSPACE_READY'])
        self.assertTrue(all(r['state'] == 'COMPLETE' and 0 <= r['elapsed_seconds'] < 1 for r in rows))
        self.assertEqual(report['workspace_asset']['sha256'], frozen.ASSET_SHA)
        self.assertEqual(report['workspace_asset']['additional_gets'], 0)
        self.assertIsNone(report['workspace_diagnostics']['timeout_scope'])
        self.assertNotIn('workspace_acceptance_verified', report)

    def test_each_failed_await_retains_only_stage_category_and_duration(self):
        labels = {'headers': 'ASSET_HEADERS', 'finished': 'ASSET_FINISHED', 'sizes': 'ASSET_SIZES',
                  'body': 'ASSET_BODY', 'ready': 'WORKSPACE_READY'}
        for name, expected in labels.items():
            with self.subTest(name=name):
                run, report, _, _ = self.capture(fail=name)
                with self.assertRaises(RuntimeError):
                    asyncio.run(run())
                diag = report['workspace_diagnostics']
                self.assertEqual(report['browser_stage'], expected)
                self.assertEqual(diag['phase'], expected)
                self.assertEqual(diag['steps'][-1]['state'], 'FAILED')
                self.assertEqual(diag['steps'][-1]['exception_type'], 'RUNTIME_ERROR')
                self.assertNotIn('private', json.dumps(report))
                self.assertNotIn('workspace_acceptance_verified', report)

    def test_asset_budget_cancellation_identifies_finished_sizes_or_body_without_widening_budget(self):
        for name in ('finished', 'sizes', 'body'):
            with self.subTest(name=name):
                run, report, calls, deadlines = self.capture(hang=name)
                with self.assertRaisesRegex(RuntimeError, 'HOLD_WORKSPACE_BROWSER_ASSET_' + name.upper() + '_TIMEOUT'):
                    asyncio.run(run())
                self.assertEqual(report['workspace_diagnostics']['timeout_scope'], 'ASSET_BODY_3S')
                self.assertEqual(report['workspace_diagnostics']['steps'][-1]['state'], 'CANCELLED')
                self.assertEqual(deadlines, [5, 3])
                self.assertNotIn('ready', calls)
                self.assertNotIn('workspace_asset', report)

    def test_ready_timeout_preserves_separate_asset_proof_and_does_not_claim_branch_acceptance(self):
        run, report, _, deadlines = self.capture(hang='ready')
        with self.assertRaisesRegex(RuntimeError, 'HOLD_WORKSPACE_BROWSER_WORKSPACE_READY_TIMEOUT'):
            asyncio.run(run())
        self.assertEqual(report['workspace_diagnostics']['timeout_scope'], 'WORKSPACE_CAPTURE_5S')
        self.assertEqual(report['workspace_asset']['sha256'], frozen.ASSET_SHA)
        self.assertNotIn('workspace', report)
        self.assertNotIn('workspace_acceptance_verified', report)
        self.assertEqual(deadlines, [5, 3])

    def test_original_hash_and_literal_false_capability_gates_still_fail_closed(self):
        for options, code in (({'payload': b'x' * len(ASSET)}, 'ASSET_SHA'),
                              ({'projection': {**PROJECTION, 'settings': True}}, 'CAPABILITY_BRANCH')):
            with self.subTest(code=code):
                run, report, _, _ = self.capture(**options)
                with self.assertRaisesRegex(RuntimeError, code):
                    asyncio.run(run())
                self.assertNotIn('workspace_acceptance_verified', report)


if __name__ == '__main__':
    unittest.main()
