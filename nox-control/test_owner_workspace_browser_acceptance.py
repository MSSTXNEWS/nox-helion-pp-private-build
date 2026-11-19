"""Passive browser composition checks; fake response objects, no browser/network."""
import asyncio
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import textwrap
import types
import unittest
from unittest.mock import patch

import owner_workspace_browser_acceptance as w

HERE = Path(__file__).resolve().parent
FILES = {w.BASE: HERE / w.BASE,
    'owner_browser_stream_only_entry.py': HERE / 'pinned/browser_normal_v1/owner_browser_stream_only_entry.py',
    'owner_chat_browser_qa.py': HERE / 'owner_chat_browser_qa.py'}
BUNDLE = {name: base64.b64encode(path.read_bytes()).decode() for name, path in FILES.items()}
ASSET = (HERE.parent / 'coordination/onepass/workspace-owner-capabilities.js').read_bytes()


class WorkspaceAcceptanceTests(unittest.TestCase):
    def base(self):
        with patch.object(w, 'BUNDLE', BUNDLE):
            return w.prepared()

    def capture(self, *, payload=ASSET, projection=None, duplicate=False, response_options=None):
        calls = []; frame = object(); options = response_options or {}
        async def sizes():
            calls.append('sizes'); return {'responseBodySize': options.get('wire', len(payload))}
        request = types.SimpleNamespace(method='GET', resource_type='script', frame=frame,
            redirected_from=options.get('redirected_from'), sizes=sizes)
        async def headers():
            return {'content-encoding': options.get('encoding', 'identity')}
        async def finished(): return None
        async def body(): calls.append('body'); return payload
        response = types.SimpleNamespace(request=request, url='http://192.0.2.1:8080' + w.ASSET_PATH,
            status=200, from_service_worker=options.get('from_service_worker', False),
            all_headers=headers, finished=finished, body=body)
        async def evaluate(script):
            calls.append('evaluate'); self.assertEqual(script, w.WORKSPACE_JS)
            return projection or {'native_flag': True, 'workspace_native': True, 'ready_resolved': True,
                'ready_rejected': False, 'capability_schema': 'NOX_NATIVE_UI_WORKSPACE_V1',
                'settings': False, 'storage_scope': 'BROWSER_VISUAL_PREFS'}
        report = {}; namespace = {'asyncio': asyncio, 'urllib': __import__('urllib.parse'), 're': __import__('re'),
            'time': __import__('time'), 'digest': lambda b: hashlib.sha256(b).hexdigest(),
            'origin': '192.0.2.1:8080', 'page': types.SimpleNamespace(main_frame=frame, evaluate=evaluate),
            'workspace_responses': [response] * (2 if duplicate else 1), 'report': report}
        code = 'async def run():\n' + textwrap.indent(textwrap.dedent(
            w.WORKSPACE_CAPTURE.replace('__WORKSPACE_JS_LITERAL__', repr(w.WORKSPACE_JS))), '    ')
        exec(compile(code, '<fake-capture>', 'exec'), namespace)
        return namespace['run'], report, calls

    def test_real_bundle_child_compiles_and_auth_guard_cleanup_remain_exact(self):
        b = self.base(); original = types.ModuleType('frozen')
        exec(compile(FILES[w.BASE].read_bytes(), '<frozen>', 'exec'), original.__dict__)
        for name in ('request_gate', 'main', 'stop_owned_child', 'browser_source', 'child_program'):
            self.assertEqual(getattr(b, name).__code__.co_code, getattr(original, name).__code__.co_code)
        program = b.child_program(b.sources()); compile(program, '<child>', 'exec')
        self.assertEqual(b.POLL_SECONDS, 32)
        self.assertIn('timeout=5', b.PAGE_TAIL)
        self.assertIn("report['workspace_acceptance_verified']=False", b.PAGE_TAIL)
        self.assertEqual(b.PAGE_TAIL.count("report['workspace_acceptance_verified']=True"), 1)
        self.assertIn('HOLD_WORKSPACE_BROWSER_LATE_DUPLICATE_ASSET', b.PAGE_TAIL)
        self.assertEqual(b.request_gate('POST', 'http://x/api/settings', 'x'), 'APPLICATION_MUTATION')
        self.assertEqual(b.request_gate('GET', 'http://x/api/nox/history', 'x'), 'PRIVATE_HISTORY')
        self.assertEqual(b.category('http://x/api/ui/capabilities', 'x'), '/api/ui/capabilities')

    def test_same_page_body_and_false_settings_branch_verified_without_get(self):
        run, report, calls = self.capture(); asyncio.run(run())
        self.assertEqual(calls, ['sizes', 'body', 'evaluate'])
        self.assertEqual(report['workspace_asset']['sha256'], w.ASSET_SHA)
        self.assertEqual(report['workspace_asset']['additional_gets'], 0)
        self.assertFalse(report['all_legacy_unauthorized_polling_fixed'])
        self.assertNotIn('workspace_acceptance_verified', report)

    def test_wrong_body_or_wire_bound_is_not_accepted(self):
        for options in ({'payload': b'x' * len(ASSET)}, {'response_options': {'wire': 16385}}):
            with self.subTest(options=tuple(options)):
                run, report, calls = self.capture(**options)
                with self.assertRaisesRegex(RuntimeError, 'ASSET_(SHA|WIRE_BOUND)'):
                    asyncio.run(run())
                self.assertNotIn('evaluate', calls)

    def test_duplicate_redirect_and_service_worker_fail_before_body(self):
        for options in ({'duplicate': True}, {'response_options': {'redirected_from': object()}},
                        {'response_options': {'from_service_worker': True}}):
            with self.subTest(options=tuple(options)):
                run, _, calls = self.capture(**options)
                with self.assertRaisesRegex(RuntimeError, 'ASSET_RESPONSE_'):
                    asyncio.run(run())
                self.assertEqual(calls, [])

    def test_ready_or_capability_mismatch_never_promotes_branch(self):
        correct = {'native_flag': True, 'workspace_native': True, 'ready_resolved': True,
            'ready_rejected': False, 'capability_schema': 'NOX_NATIVE_UI_WORKSPACE_V1',
            'settings': False, 'storage_scope': 'BROWSER_VISUAL_PREFS'}
        for key, value in (('ready_resolved', False), ('settings', True), ('settings', None),
                           ('storage_scope', 'SERVER_SETTINGS'), ('capability_schema', None)):
            run, report, _ = self.capture(projection={**correct, key: value})
            with self.subTest(key=key, value=value), self.assertRaisesRegex(RuntimeError, 'CAPABILITY_BRANCH'):
                asyncio.run(run())
            self.assertNotIn('workspace_acceptance_verified', report)

    def test_javascript_reads_only_public_projection_and_clears_timer(self):
        script = r"""
const vm=require('node:vm'), assert=require('node:assert/strict');
const source=JSON.parse(process.argv[1]);
async function check(ready) {
 let clears=0;const delays=[];
 const workspace={native:true,ready,capabilities:{schema:'NOX_NATIVE_UI_WORKSPACE_V1',settings:false},storageScope:'BROWSER_VISUAL_PREFS'};
 Object.defineProperty(workspace,'settings',{get(){throw Error('private settings read');}});
 const context=vm.createContext({window:{NOX_NATIVE_OWNER:true,NoxWorkspace:workspace},
  setTimeout(fn,delay){delays.push(delay);return setTimeout(fn,0);},clearTimeout(id){clears++;clearTimeout(id);}});
 const row=await vm.runInContext('('+source+')()',context,{timeout:1000});
 assert.deepEqual(delays,[4500]);assert.equal(clears,1);
 return JSON.parse(JSON.stringify(row));
}
(async()=>{const ok=await check(Promise.resolve());assert.equal(ok.ready_resolved,true);assert.equal(ok.settings,false);
 const failed=await check(Promise.reject(Error('must not export this secret')));assert.equal(failed.ready_rejected,true);
 const pending=await check(new Promise(()=>{}));assert.equal(pending.ready_resolved,false);
 assert.equal(JSON.stringify([ok,failed,pending]).includes('secret'),false);console.log('PASS');})().catch(()=>process.exit(2));
"""
        value = subprocess.run(['node', '-e', script, json.dumps(w.WORKSPACE_JS)], capture_output=True, timeout=5)
        self.assertEqual(value.returncode, 0, value.stderr.decode()); self.assertEqual(value.stdout.strip(), b'PASS')


if __name__ == '__main__':
    unittest.main()
