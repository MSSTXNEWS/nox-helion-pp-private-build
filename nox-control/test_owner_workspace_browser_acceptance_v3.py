"""Same-page CDP correlation and bounded body proof; no browser/network actions."""
import asyncio
import base64
import hashlib
import json
from pathlib import Path
import re
import types
import unittest
import urllib.parse
from unittest.mock import patch

import owner_workspace_browser_acceptance_v2 as old
import owner_workspace_browser_acceptance_v3 as candidate

HERE = Path(__file__).resolve().parent
FILES = {name: HERE / name for name in candidate.PINS}
FILES['owner_browser_stream_only_entry.py'] = HERE / 'pinned/browser_normal_v1/owner_browser_stream_only_entry.py'
BUNDLE = {name: base64.b64encode(path.read_bytes()).decode() for name, path in FILES.items()}
ASSET = (HERE.parent / 'coordination/onepass/workspace-owner-capabilities.js').read_bytes()
ORIGIN = '192.0.2.1:8080'
URL = 'http://' + ORIGIN + '/nox-web-v29/pc/workspace.js'
PAGE = 'http://' + ORIGIN + '/nox-web-v29/pc/resonance.html'


class Session:
    def __init__(self, *, payload=ASSET, encoded=False, hang=False, frame_changed=False):
        self.calls = []; self.listeners = {}; self.payload = payload; self.encoded = encoded
        self.hang = hang; self.frame_changed = frame_changed; self.frames = 0; self.detached = False

    async def send(self, method, params=None):
        self.calls.append((method, params))
        if method == 'Page.getFrameTree':
            self.frames += 1
            return {'frameTree': {'frame': {'id': 'frame-main', 'loaderId': 'foreign-loader' if self.frame_changed else 'loader-main',
                'url': 'about:blank' if self.frames == 1 else PAGE}}}
        if method == 'Network.enable': return {}
        if method == 'Network.getResponseBody':
            if self.hang: await asyncio.Event().wait()
            return {'body': base64.b64encode(self.payload).decode() if self.encoded else self.payload.decode(),
                    'base64Encoded': self.encoded}
        raise AssertionError('Unexpected method')

    def on(self, name, callback): self.listeners[name] = callback
    def remove_listener(self, name, callback):
        if self.listeners.get(name) is callback: del self.listeners[name]
    async def detach(self): self.detached = True


def collector(session):
    namespace = {'asyncio': asyncio, 'urllib': urllib, 're': re,
                 'digest': lambda raw: hashlib.sha256(raw).hexdigest()}
    exec(compile(candidate.CDP_SOURCE, '<same-page-cdp>', 'exec'), namespace)
    report = {}; proof = namespace['WorkspaceCDPProof'](ORIGIN, report)
    async def new_session(page): return session
    asyncio.run(proof.attach(types.SimpleNamespace(new_cdp_session=new_session), object()))
    return proof, report


def events(proof, *, finish=True, frame='frame-main', loader='loader-main', response_extra=None, encoding='identity'):
    proof.event('request', {'requestId': 'req-public', 'loaderId': loader, 'frameId': frame, 'type': 'Script',
                           'request': {'url': URL, 'method': 'GET', 'headers': {'Authorization': 'must-not-export'}}})
    response = {'url': URL, 'status': 200, 'fromServiceWorker': False,
                'headers': {'Content-Length': str(len(ASSET)), 'Content-Encoding': encoding,
                            'Set-Cookie': 'must-not-export'}}
    response.update(response_extra or {})
    proof.event('response', {'requestId': 'req-public', 'loaderId': loader, 'frameId': frame, 'type': 'Script',
                            'response': response})
    proof.event('data', {'requestId': 'req-public', 'dataLength': len(ASSET), 'encodedDataLength': len(ASSET)})
    if finish: proof.event('finished', {'requestId': 'req-public', 'encodedDataLength': len(ASSET) + 350})


class CDPWorkspaceTests(unittest.TestCase):
    def test_exact_bundle_compiles_preserving_auth_routes_deadlines_and_owned_cleanup(self):
        with patch.object(candidate, 'BUNDLE', BUNDLE): fresh = candidate.prepared()
        with patch.object(old, 'BUNDLE', BUNDLE): prior = old.prepared()
        for name in ('main', 'request_gate', 'stop_owned_child', 'browser_source', 'child_program'):
            self.assertEqual(getattr(fresh, name).__code__.co_code, getattr(prior, name).__code__.co_code)
        compile(fresh.child_program(fresh.sources()), '<passive-cdp-child>', 'exec')
        self.assertEqual(fresh.POLL_SECONDS, 32)
        for bound in ('timeout=3', 'timeout=5', 'timeout=20000', 'timeout=12000'):
            self.assertIn(bound, fresh.PAGE_TAIL)
        self.assertNotIn('.body()', fresh.PAGE_TAIL)
        self.assertNotIn('asset.body', fresh.PAGE_TAIL)
        self.assertEqual(fresh.PAGE_TAIL.count("'Network.getResponseBody'"), 1)
        for forbidden in ('Network.loadNetworkResource', 'Network.replayXHR', 'Fetch.enable', 'Fetch.getResponseBody'):
            self.assertNotIn(forbidden, fresh.PAGE_TAIL)
        self.assertIn('NOT_READ_WORKSPACE_ONLY_SCOPE', fresh.PAGE_TAIL)
        self.assertLess(fresh.PAGE_TAIL.index('workspace_cdp.final_check()'),
                        fresh.PAGE_TAIL.index("report['workspace_acceptance_verified']=True"))
        self.assertEqual(fresh.request_gate('POST', 'http://x/api/settings', 'x'), 'APPLICATION_MUTATION')
        self.assertEqual(hashlib.sha256(FILES[candidate.BASE].read_bytes()).hexdigest(), candidate.BASE_SHA)

    def test_one_same_page_cdp_body_reads_plain_or_base64_without_private_fields(self):
        for encoded in (False, True):
            with self.subTest(encoded=encoded):
                session = Session(encoded=encoded); proof, report = collector(session); events(proof)
                self.assertEqual(asyncio.run(proof.read_body()), ASSET); proof.final_check()
                self.assertEqual([x[0] for x in session.calls],
                                 ['Page.getFrameTree', 'Network.enable', 'Page.getFrameTree', 'Network.getResponseBody'])
                self.assertEqual(session.calls[-1], ('Network.getResponseBody', {'requestId': 'req-public'}))
                self.assertEqual(session.calls[1][1], {'maxTotalBufferSize': 1048576,
                    'maxResourceBufferSize': 16384, 'maxPostDataSize': 0})
                self.assertTrue(report['workspace_cdp']['body_sha_verified'])
                self.assertFalse(report['workspace_cdp']['prior_body_timeout_cause_proven'])
                raw = json.dumps(report)
                for secret in ('must-not-export', 'req-public', 'loader-main', 'frame-main', URL):
                    self.assertNotIn(secret, raw)
                asyncio.run(proof.close()); self.assertTrue(session.detached); self.assertEqual(session.listeners, {})

    def test_missing_finished_and_foreign_frame_or_loader_prevent_body_request(self):
        for options in ({'finish': False}, {'frame': 'other-frame'}, {'loader': 'other-loader'}):
            with self.subTest(options=options):
                session = Session(); proof, _ = collector(session); events(proof, **options)
                with self.assertRaises(RuntimeError): asyncio.run(proof.read_body())
                self.assertNotIn('Network.getResponseBody', [x[0] for x in session.calls])

    def test_duplicate_redirect_service_worker_and_response_identifier_fail_closed(self):
        for kind in ('duplicate', 'redirect', 'worker', 'unbound'):
            with self.subTest(kind=kind):
                session = Session(); proof, _ = collector(session)
                if kind == 'worker': events(proof, response_extra={'fromServiceWorker': True})
                else: events(proof)
                if kind in ('duplicate', 'redirect'):
                    proof.event('request', {'requestId': 'req-public' if kind == 'redirect' else 'new-request',
                        'loaderId': 'loader-main', 'frameId': 'frame-main', 'type': 'Script',
                        'redirectResponse': {'status': 302}, 'request': {'url': URL, 'method': 'GET'}})
                if kind == 'unbound':
                    proof.event('response', {'requestId': 'unknown', 'response': {'url': URL}})
                with self.assertRaises(RuntimeError): asyncio.run(proof.read_body())
                self.assertNotIn('Network.getResponseBody', [x[0] for x in session.calls])

    def test_empty_wrong_and_oversized_body_never_trigger_fallback_or_second_body_call(self):
        for payload in (b'', b'x' * len(ASSET), b'x' * 16385):
            with self.subTest(length=len(payload)):
                session = Session(payload=payload); proof, report = collector(session); events(proof)
                with self.assertRaises(RuntimeError): asyncio.run(proof.read_body())
                with self.assertRaises(RuntimeError): asyncio.run(proof.read_body())
                self.assertEqual([x[0] for x in session.calls].count('Network.getResponseBody'), 1)
                self.assertFalse(report['workspace_cdp']['body_sha_verified'])

    def test_decoded_data_bound_blocks_body_before_materialization(self):
        session = Session(); proof, _ = collector(session); events(proof, finish=False)
        proof.event('data', {'requestId': 'req-public', 'dataLength': 16385, 'encodedDataLength': 1})
        proof.event('finished', {'requestId': 'req-public', 'encodedDataLength': 8000})
        with self.assertRaisesRegex(RuntimeError, 'DATA_BOUND'): asyncio.run(proof.read_body())
        self.assertNotIn('Network.getResponseBody', [x[0] for x in session.calls])

    def test_cancelled_body_keeps_one_attempt_and_owned_session_can_close(self):
        session = Session(hang=True); proof, report = collector(session); events(proof)
        async def exercise():
            with self.assertRaises(TimeoutError): await asyncio.wait_for(proof.read_body(), .01)
            await proof.close()
        asyncio.run(exercise())
        self.assertEqual([x[0] for x in session.calls].count('Network.getResponseBody'), 1)
        self.assertEqual(report['workspace_cdp']['phase'], 'GET_RESPONSE_BODY')
        self.assertFalse(report['workspace_cdp']['body_sha_verified'])
        self.assertTrue(session.detached)

    def test_late_duplicate_cannot_be_promoted_after_successful_body_hash(self):
        session = Session(); proof, _ = collector(session); events(proof)
        asyncio.run(proof.read_body())
        proof.event('request', {'requestId': 'late-public', 'loaderId': 'loader-main', 'frameId': 'frame-main',
            'type': 'Script', 'request': {'url': URL, 'method': 'GET'}})
        with self.assertRaises(RuntimeError): proof.final_check()


if __name__ == '__main__':
    unittest.main()
