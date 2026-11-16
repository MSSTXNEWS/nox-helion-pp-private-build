import ast
import asyncio
import base64
import gzip
import hashlib
import json
from pathlib import Path
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch

import owner_chat_asset_identity_qa as asset
import owner_browser_asset_identity_entry as entry

HERE = Path(__file__).resolve().parent
PUBLIC = (HERE.parent / 'coordination/onepass/nox-v135-resonance-owner-bridge-coalesced.js').read_bytes()


def load(name):
    raw = (HERE / (name + '.py')).read_bytes()
    module = types.ModuleType('_asset_fixture_' + name)
    exec(compile(raw, '<' + name + '>', 'exec'), module.__dict__)
    return module, raw


def installed():
    core, raw = load('owner_chat_browser_qa')
    transport, traw = load('owner_chat_browser_transport_qa')
    release, rraw = load('owner_chat_browser_release_qa')
    scope, sraw = load('owner_chat_stream_only_qa')
    normal, nraw = load('owner_chat_normal_motion_qa')
    original_gate = core.progressive_stream_valid
    captured = {}
    rewrite = asset.rewrite_browser

    def capture(source):
        captured['before'] = source
        captured['after'] = rewrite(source)
        return captured['after']

    with patch.object(asset, 'rewrite_browser', side_effect=capture):
        asset.install(core, raw, transport, traw, release, rraw, scope, sraw, normal, nraw)
    return core, scope, normal, original_gate, captured


class Page:
    def __init__(self):
        self.main_frame = object()
        self.listeners = {}

    def on(self, name, callback):
        self.listeners[name] = callback

    def remove_listener(self, name, callback):
        assert self.listeners[name] == callback
        del self.listeners[name]


def response(page, raw=PUBLIC):
    url = 'http://192.0.2.40:8080' + asset.ASSET_PATH
    request = types.SimpleNamespace(url=url, method='GET', resource_type='script',
        frame=page.main_frame, redirected_from=None, redirected_to=None,
        sizes=AsyncMock(return_value={'responseBodySize': len(raw)}))
    return types.SimpleNamespace(url=url, status=200, request=request,
        headers={'content-length': str(len(raw))}, from_service_worker=False,
        finished=AsyncMock(return_value=None), body=AsyncMock(return_value=raw))


def successful_normal_report():
    value = {'state': 'STREAM_ONLY_ACCEPTED',
        'scope': 'AUTHENTICATED_NATIVE_ENDPOINT_VISIBLE_PARTIALS_S03_NORMAL_MOTION_ONLY',
        'normal_motion_probe_schema': 'NOX_OWNER_BROWSER_NORMAL_MOTION_PROBE_V1',
        'browser_motion_preference': 'no-preference', 'maximum_native_posts': 1,
        'maximum_new_dialogs': 1, 'native_posts_admitted': 1,
        'production_configuration_changed': False, 'normal_motion_probe_verified': True,
        'normal_motion_mode_verified': True, 'normal_animation_evaluated': True,
        'normal_motion_observation_state': 'VERIFIED', 'strict_progressive_stream_observed': True,
        'two_proper_prefixes_before_done': True, 's03_readback_verified': True,
        'synthetic_number_sequence_pass': True, 'full_browser_qa_evaluated': False,
        'full_browser_qa_promoted': False, 'markdown_rendering_evaluated': False,
        'upstream_model_inference_verified': False, 'upstream_model_request_bound': False,
        'upstream_SSE_binding_verified': False, 'asset_identity_scope': asset.SCOPE,
        'asset_identity_verified': True, 'asset_binding': asset.initial_binding()}
    value['asset_binding'].update(state='VERIFIED', response_count=1, body_read_count=1,
        http_status=200, body_sha256=asset.ASSET_SHA, body_bytes=asset.ASSET_BYTES,
        content_encoding='identity', browser_reported_wire_bytes=asset.ASSET_BYTES,
        **{k: True for k in ('same_origin', 'exact_request_url', 'get_method', 'script_resource',
            'main_frame', 'no_redirect', 'service_worker_absent', 'known_content_encoding',
            'wire_length_header_valid', 'wire_size_bounded', 'body_verified', 'verified_before_submit',
            'verified_at_finish', 'listener_closed')})
    return value


class LoadedResponseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.page = Page()
        self.core = types.SimpleNamespace(stop_present=Mock(return_value=False))
        self.report = {'asset_binding': asset.initial_binding()}
        self.probe = asset.LoadedAsset(self.core, self.page, self.report, 'http://192.0.2.40:8080')

    async def asyncTearDown(self):
        if 'response' in self.page.listeners:
            await self.probe.close()

    async def test_actual_page_script_body_is_bound_before_post_and_at_finish(self):
        self.assertEqual(len(PUBLIC), asset.ASSET_BYTES)
        self.assertEqual(hashlib.sha256(PUBLIC).hexdigest(), asset.ASSET_SHA)
        item = response(self.page)
        self.page.listeners['response'](item)
        await self.probe.verify('BEFORE_POST')
        self.assertTrue(self.report['asset_binding']['verified_before_submit'])
        self.assertFalse(asset.complete(self.report['asset_binding']))
        await self.probe.verify('FINAL'); await self.probe.close()
        self.assertTrue(asset.complete(self.report['asset_binding']))
        item.body.assert_awaited_once()
        self.assertNotIn('192.0.2.40', json.dumps(self.report))
        self.assertNotIn(PUBLIC[:40].decode(), json.dumps(self.report))

    async def test_missing_response_cannot_admit_generation(self):
        with self.assertRaisesRegex(RuntimeError, 'PAGE_SCRIPT_RESPONSE_MISSING'):
            await self.probe.verify('BEFORE_POST')
        self.assertFalse(self.report['asset_binding']['verified_before_submit'])

    async def test_standalone_fetch_with_correct_bytes_is_not_script_evidence(self):
        item = response(self.page); item.request.resource_type = 'fetch'
        self.probe.on_response(item)
        with self.assertRaisesRegex(RuntimeError, 'RESPONSE_METADATA'):
            await self.probe.verify('BEFORE_POST')
        item.body.assert_not_called()

    async def test_origin_query_frame_status_redirect_and_transfer_metadata_are_required(self):
        mutations = (
            lambda r: setattr(r, 'url', 'http://192.0.2.41:8080' + asset.ASSET_PATH),
            lambda r: setattr(r.request, 'url', r.url + '?different'),
            lambda r: setattr(r.request, 'frame', object()),
            lambda r: setattr(r.request, 'method', 'POST'),
            lambda r: setattr(r, 'status', 304),
            lambda r: setattr(r.request, 'redirected_from', object()),
            lambda r: setattr(r, 'from_service_worker', True),
            lambda r: r.headers.update({'content-length': str(asset.WIRE_LIMIT + 1)}),
            lambda r: r.headers.update({'content-length': 'unknown'}),
            lambda r: r.headers.update({'content-encoding': 'unreviewed-codec'}),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                page = Page(); report = {'asset_binding': asset.initial_binding()}
                probe = asset.LoadedAsset(self.core, page, report, 'http://192.0.2.40:8080')
                item = response(page); mutate(item); probe.on_response(item)
                with self.assertRaisesRegex(RuntimeError, 'RESPONSE_METADATA'):
                    await probe.verify('BEFORE_POST')
                item.body.assert_not_called(); await probe.close()

    async def test_legitimate_gzip_wire_length_is_not_decoded_asset_length(self):
        item = response(self.page)
        wire = gzip.compress(PUBLIC, mtime=0)
        self.assertNotEqual(len(wire), len(PUBLIC))
        self.assertEqual(gzip.decompress(wire), PUBLIC)
        item.headers.update({'content-length': str(len(wire)), 'content-encoding': 'gzip'})
        item.request.sizes.return_value = {'responseBodySize': len(wire)}
        self.probe.on_response(item)
        await self.probe.verify('BEFORE_POST'); await self.probe.verify('FINAL'); await self.probe.close()
        self.assertTrue(asset.complete(self.report['asset_binding']))
        self.assertEqual(self.report['asset_binding']['browser_reported_wire_bytes'], len(wire))
        self.assertEqual(self.report['asset_binding']['body_bytes'], len(PUBLIC))

    async def test_absent_length_requires_bounded_browser_size_and_known_encoding(self):
        item = response(self.page); item.headers = {'content-encoding': 'br'}
        item.request.sizes.return_value = {'responseBodySize': 4096}
        self.probe.on_response(item)
        await self.probe.verify('BEFORE_POST'); await self.probe.verify('FINAL'); await self.probe.close()
        self.assertTrue(asset.complete(self.report['asset_binding']))
        self.assertIsNone(self.report['asset_binding']['declared_wire_bytes'])
        self.assertFalse(self.report['asset_binding']['wire_length_header_present'])

    async def test_unknown_or_mismatched_wire_size_prevents_body_read(self):
        for wire in (None, 0, -1, True, asset.WIRE_LIMIT + 1, asset.ASSET_BYTES - 1):
            page = Page(); report = {'asset_binding': asset.initial_binding()}
            probe = asset.LoadedAsset(self.core, page, report, 'http://192.0.2.40:8080')
            item = response(page); item.request.sizes.return_value = {'responseBodySize': wire}
            probe.on_response(item)
            with self.assertRaisesRegex(RuntimeError, 'WIRE_SIZE_'):
                await probe.verify('BEFORE_POST')
            item.body.assert_not_called(); await probe.close()

    async def test_compression_metadata_cannot_admit_wrong_decoded_content(self):
        item = response(self.page)
        item.headers = {'content-encoding': 'deflate', 'content-length': '4000'}
        item.request.sizes.return_value = {'responseBodySize': 4000}
        item.body.return_value = b'x' * asset.ASSET_BYTES
        self.probe.on_response(item)
        with self.assertRaisesRegex(RuntimeError, 'BODY_PIN'):
            await self.probe.verify('BEFORE_POST')

    async def test_same_length_wrong_bytes_hold_without_body_or_exception_export(self):
        private = (b'PRIVATE_TOKEN_DO_NOT_EXPORT' * 1000)[:asset.ASSET_BYTES]
        item = response(self.page, private); self.probe.on_response(item)
        with self.assertRaisesRegex(RuntimeError, 'BODY_PIN'):
            await self.probe.verify('BEFORE_POST')
        self.assertNotIn('PRIVATE_TOKEN', json.dumps(self.report))
        self.assertFalse(asset.complete(self.report['asset_binding']))

    async def test_declared_size_does_not_replace_actual_body_length_check(self):
        item = response(self.page); item.body.return_value = PUBLIC + b'!'
        self.probe.on_response(item)
        with self.assertRaisesRegex(RuntimeError, 'BODY_LENGTH'):
            await self.probe.verify('BEFORE_POST')

    async def test_second_script_after_pre_submit_invalidates_final_proof(self):
        first = response(self.page); second = response(self.page)
        self.probe.on_response(first); await self.probe.verify('BEFORE_POST')
        self.probe.on_response(second)
        with self.assertRaisesRegex(RuntimeError, 'DUPLICATE_RESPONSE'):
            await self.probe.verify('FINAL')
        second.body.assert_not_called()
        self.assertEqual(self.report['asset_binding']['response_count'], 2)

    async def test_body_timeout_and_read_error_are_categorical(self):
        async def pending():
            await asyncio.Event().wait()
        item = response(self.page); item.body.side_effect = pending
        with patch.object(asset, 'BODY_TIMEOUT', 0.01):
            self.probe.on_response(item)
            with self.assertRaisesRegex(RuntimeError, 'BODY_TIMEOUT'):
                await self.probe.verify('BEFORE_POST')
        page = Page(); report = {'asset_binding': asset.initial_binding()}
        probe = asset.LoadedAsset(self.core, page, report, 'http://192.0.2.40:8080')
        item = response(page); item.body.side_effect = RuntimeError('secret/private?token=hidden')
        probe.on_response(item)
        with self.assertRaisesRegex(RuntimeError, 'BODY_READ'):
            await probe.verify('BEFORE_POST')
        self.assertNotIn('secret', json.dumps(report)); await probe.close()

    async def test_owner_stop_and_outer_cancellation_are_not_soft_diagnostics(self):
        self.core.stop_present.return_value = True
        with self.assertRaisesRegex(RuntimeError, 'HOLD_OWNER_STOP'):
            await self.probe.verify('BEFORE_POST')
        self.core.stop_present.return_value = False
        async def pending():
            await asyncio.Event().wait()
        item = response(self.page); item.body.side_effect = pending; self.probe.on_response(item)
        task = asyncio.create_task(self.probe.verify('BEFORE_POST'))
        await asyncio.sleep(0); task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        await self.probe.close()
        self.assertFalse(asset.complete(self.report['asset_binding']))
        self.assertTrue(self.probe.task.done())


class CompositionTests(unittest.TestCase):
    def bundle(self):
        return {name: base64.b64encode((HERE / name).read_bytes()).decode() for name in entry.PINS}

    def test_original_route_oracles_and_timeouts_preserved_and_asset_before_budget_post(self):
        core, scope, _, gate, source = installed()
        self.assertIs(core.progressive_stream_valid, gate)
        self.assertEqual(scope.TOTAL_TIMEOUT, 140)
        self.assertEqual(core.EXPECTED, ','.join(map(str, range(1, 41))))
        before, after = ast.parse(source['before']), ast.parse(source['after'])
        guard = lambda tree: next(n for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef) and n.name == 'guard')
        self.assertEqual(ast.dump(guard(before)), ast.dump(guard(after)))
        self.assertLess(source['after'].index("verify('BEFORE_POST')"),
            source['after'].index("report['resources_at_submit'] = budget()"))
        self.assertLess(source['after'].index('_nox_loaded_asset(page, report, base)'),
            source['after'].index('await page.goto('))
        self.assertIn("reduced_motion='no-preference'", source['after'])
        for marker in ('progressive_stream_valid(final)', 'HOLD_SYNTHETIC_MODEL_QUALITY',
                       'HOLD_STREAM_ONLY_TWO_PROPER_PREFIXES_NOT_OBSERVED',
                       'HOLD_STREAM_ONLY_NATIVE_OR_S03', 'HOLD_OWNER_STOP'):
            self.assertIn(marker, source['after'])
        self.assertNotIn('page.request', source['after'])
        # A single proper prefix remains a failure even with an accepted asset.
        self.assertFalse(core.progressive_stream_valid({'ui_prefix_lengths_before_done': [5]}))

    def test_source_or_anchor_drift_fails_before_browser(self):
        with self.assertRaisesRegex(RuntimeError, 'NORMAL_SOURCE_PIN'):
            asset.install(None, b'', None, b'', None, b'', None, b'', None, b'changed')
        with self.assertRaisesRegex(RuntimeError, 'BROWSER_ANCHOR'):
            asset.rewrite_browser('async def browser_run():\n return None\n')

    def test_eight_source_closure_original_entry_reused_child_compiles(self):
        with patch.object(entry, 'BUNDLE', self.bundle()):
            delegated, program = entry.prepared()
        self.assertEqual(len(entry.PINS), 8)
        compile(program, '<asset-child-fixture>', 'exec')
        self.assertIn(b'asset.install(core,raw,transport,traw,release,rraw,scope,', program)
        self.assertIn(b'rc=scope.main(core)', program)
        self.assertNotIn(b'core.main()', program)
        self.assertEqual(delegated.run_child.__code__.co_filename, '<owner_browser_stream_only_entry.py>')
        self.assertIn(165, delegated.run_child.__code__.co_consts)
        self.assertEqual(set(delegated.PINS), set(entry.PINS) - {
            entry.NORMAL_ENTRY, 'owner_browser_stream_only_entry.py'})

    def test_parent_requires_both_normal_stream_and_actual_asset_proof(self):
        with patch.object(entry, 'BUNDLE', self.bundle()):
            delegated, _ = entry.prepared()
        value = successful_normal_report()
        with patch('builtins.print') as output:
            delegated.emit('browser_stream_only_receipt', value)
        row = json.loads(output.call_args.args[0].split('=', 1)[1])
        self.assertEqual(row['kind'], 'browser_normal_asset_receipt')
        for key in ('verified_before_submit', 'verified_at_finish', 'body_verified'):
            bad = successful_normal_report(); bad['asset_binding'][key] = False
            with self.assertRaisesRegex(RuntimeError, 'CHILD_ASSET_ACCEPTANCE'):
                delegated.emit('browser_stream_only_receipt', bad)
        bad = successful_normal_report(); bad['two_proper_prefixes_before_done'] = False
        with self.assertRaisesRegex(RuntimeError, 'CHILD_ACCEPTANCE'):
            delegated.emit('browser_stream_only_receipt', bad)

    def test_pre_post_hold_cannot_be_reported_as_asset_or_motion_acceptance(self):
        with patch.object(entry, 'BUNDLE', self.bundle()):
            delegated, _ = entry.prepared()
        value = successful_normal_report()
        value.update(state='HOLD', native_posts_admitted=0, normal_motion_probe_verified=False,
            asset_identity_verified=False, asset_binding=asset.initial_binding())
        with patch('builtins.print') as output:
            delegated.emit('browser_stream_only_receipt', value)
        row = json.loads(output.call_args.args[0].split('=', 1)[1])
        self.assertFalse(row['data']['asset_identity_verified'])
        self.assertEqual(row['data']['native_posts_admitted'], 0)

    def test_unknown_helper_source_rejected_before_private_composition(self):
        bundle = self.bundle(); bundle[entry.HELPER] = base64.b64encode(b'raise AssertionError()').decode()
        with patch.object(entry, 'BUNDLE', bundle), self.assertRaisesRegex(RuntimeError, 'BUNDLE_PIN'):
            entry.prepared()


if __name__ == '__main__':
    unittest.main()
