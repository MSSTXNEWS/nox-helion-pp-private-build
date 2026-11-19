"""Concrete stream-only regressions. No native browser, service or model calls."""
import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch

import owner_browser_stream_only_entry as entry
import owner_chat_stream_only_qa as scope

HERE = Path(__file__).parent


def installed():
    loaded = {}
    for name in ('owner_chat_browser_qa', 'owner_chat_browser_transport_qa', 'owner_chat_browser_release_qa'):
        raw = (HERE / (name + '.py')).read_bytes()
        value = types.ModuleType('_stream_only_test_' + name)
        exec(compile(raw, '<' + name + '>', 'exec'), value.__dict__)
        loaded[name] = value, raw
    core, raw = loaded['owner_chat_browser_qa']
    transport, traw = loaded['owner_chat_browser_transport_qa']
    release, rraw = loaded['owner_chat_browser_release_qa']
    original_gate = core.progressive_stream_valid
    scope.install(core, raw, transport, traw, release, rraw)
    return core, transport, release, original_gate


def observation(prefixes):
    return {'native_calls': 1, 'native_delta_count': 149, 'ui_before_native_done': True,
        'ui_measurement_kind': 'CUMULATIVE_VISIBLE_ASSISTANT_BODY', 'ui_body_visible': True,
        'dom_answer_matches_native': True,
        'done': {'saved': True, 's03_integrated': True, 'dialog_matches': True},
        'answer_characters': 149, 'answer_normalized_characters': 110,
        'ui_prefix_lengths_before_done': prefixes, 'ui_first_ms': 5751.5, 'native_done_ms': 5971.1}


class ScopeTests(unittest.TestCase):
    def test_exact_compilation_skips_layout_stages_without_altering_frozen_gate(self):
        core, _, _, original_gate = installed()
        self.assertIs(core.progressive_stream_valid, original_gate)
        names = core.browser_run.__code__.co_names
        for name in ('capture_private_screenshot', 'check_report_layout', '_nox_responsive_layout',
                     'require_screenshot_captures', 'set_viewport_size'):
            self.assertNotIn(name, names)
        for name in ('click_send', 'json_response', 'public_numeric_answer', 'progressive_stream_valid',
                     'budget', '_nox_wait_send_release', '_nox_wire_start', '_nox_route_evidence'):
            self.assertIn(name, names)
        self.assertIn('/chat/login', core.browser_run.__code__.co_consts)
        self.assertIn('/api/nox/stop', core.browser_run.__code__.co_consts)
        guard = next(value for value in core.browser_run.__code__.co_consts
                     if isinstance(value, types.CodeType) and value.co_name == 'guard')
        self.assertIn('native_admitted', guard.co_freevars)
        self.assertIn('duplicate_qa_generation', guard.co_consts)
        self.assertIn('answer_normalized_characters:normalize(q.answer).length', core.SNAPSHOT_JS)
        self.assertIn("window.matchMedia('(prefers-reduced-motion: reduce)').matches", core.SNAPSHOT_JS)
        self.assertIn('reduce', core.browser_run.__code__.co_consts)
        self.assertIn('HOLD_STREAM_ONLY_MOTION_PREFERENCE_NOT_APPLIED', core.browser_run.__code__.co_consts)
        self.assertEqual(core.EXPECTED, ','.join(map(str, range(1, 41))))

    def test_stream_only_dialog_click_is_single_fresh_pointer_gated(self):
        core, _, _, _ = installed()
        code = core.browser_run.__code__
        self.assertIn('pointer_at_click', code.co_consts)
        self.assertIn('physical_pointer_click', code.co_consts)
        self.assertIn('HOLD_QA_DIALOG_POINTER_OCCLUDED', code.co_consts)
        self.assertIn('HOLD_OWNER_STOP', code.co_consts)
        self.assertIn('mouse', code.co_names)
        self.assertIn('click', code.co_names)
        self.assertNotIn('click_error_projection', code.co_names)
        self.assertTrue(any(isinstance(c, str) and c.startswith('title=>[...document.querySelectorAll')
                            for c in code.co_consts))

    def test_one_proper_prefix_remains_two_parts_not_strict_acceptance(self):
        core, _, release, _ = installed()
        value = observation([66])
        self.assertTrue(scope.two_parts_observed(release, value))
        self.assertEqual(scope.proper_prefixes(value), [66])
        self.assertFalse(core.progressive_stream_valid(value))

    def test_whitespace_and_full_answer_before_done_do_not_fake_proper_prefixes(self):
        core, _, release, _ = installed()
        self.assertFalse(scope.two_parts_observed(release, observation([110])))
        self.assertEqual(scope.proper_prefixes(observation([110])), [])
        value = observation([66, 110])
        self.assertTrue(core.progressive_stream_valid(value))  # Frozen legacy predicate unchanged.
        self.assertTrue(scope.two_parts_observed(release, value))
        self.assertEqual(scope.proper_prefixes(value), [66])  # Only one genuine proper prefix.
        self.assertEqual(scope.proper_prefixes(observation([33, 66, 110])), [33, 66])
        for invalid in ([66, 66], [111], [False], [90, 66]):
            self.assertEqual(scope.proper_prefixes(observation(invalid)), [])

    def test_changed_source_is_rejected_before_composition(self):
        with self.assertRaisesRegex(RuntimeError, 'DEPENDENCY_PIN'):
            scope.install(types.ModuleType('x'), b'changed', types.ModuleType('y'), b'changed',
                          types.ModuleType('z'), b'changed')
        bundle = {name: base64.b64encode((HERE / name).read_bytes()).decode() for name in entry.PINS}
        with patch.object(entry, 'BUNDLE', bundle):
            blobs = entry.sources(); program = entry.child_program(blobs)
            compile(program, '<stream-only-child>', 'exec')
        self.assertIn(b'scope.main(core)', program)
        self.assertNotIn(b'core.main()', program)
        self.assertEqual(set(entry.PINS), {'owner_chat_browser_qa.py', 'owner_chat_browser_transport_qa.py',
            'owner_chat_browser_release_qa.py', 'owner_chat_stream_only_qa.py'})
        bundle['owner_chat_stream_only_qa.py'] = base64.b64encode(b'changed').decode()
        with patch.object(entry, 'BUNDLE', bundle), self.assertRaisesRegex(RuntimeError, 'BUNDLE_PIN'):
            entry.sources()

    def test_reviewed_pr415_dependencies_match_and_each_mismatch_holds(self):
        files={
            'owner_chat_browser_qa.py':(HERE/'owner_chat_browser_qa.py').read_bytes(),
            'owner_chat_browser_transport_qa.py':(HERE/'owner_chat_browser_transport_qa.py').read_bytes(),
            'owner_chat_browser_release_qa.py':(HERE/'owner_chat_browser_release_qa.py').read_bytes(),
        }
        reviewed='9530c6e71274bbbca997f0aea07a26c988cfd536ed1aa1ba4067753827ac56f9'
        self.assertEqual(scope.BASE_SHA, reviewed)
        self.assertEqual(hashlib.sha256(files['owner_chat_browser_qa.py']).hexdigest(), reviewed)
        self.assertEqual(hashlib.sha256(files['owner_chat_browser_transport_qa.py']).hexdigest(),
                         scope.TRANSPORT_SHA)
        self.assertEqual(hashlib.sha256(files['owner_chat_browser_release_qa.py']).hexdigest(),
                         scope.RELEASE_SHA)
        module_types=(types.ModuleType('core'),types.ModuleType('transport'),types.ModuleType('release'))
        names=('owner_chat_browser_qa.py','owner_chat_browser_transport_qa.py','owner_chat_browser_release_qa.py')
        for index,name in enumerate(names):
            values=[files[item] for item in names]
            values[index]+=b' '
            args=(module_types[0],values[0],module_types[1],values[1],module_types[2],values[2])
            with self.subTest(dependency=name), self.assertRaisesRegex(RuntimeError, 'DEPENDENCY_PIN'):
                scope.install(*args)
            bundle={item:base64.b64encode((HERE/item).read_bytes()).decode() for item in entry.PINS}
            bundle[name]=base64.b64encode(values[index]).decode()
            with self.subTest(bundle_dependency=name), patch.object(entry, 'BUNDLE', bundle), \
                    self.assertRaisesRegex(RuntimeError, 'BUNDLE_PIN'):
                entry.sources()

    def test_dangling_stop_is_not_treated_as_absent(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'STOP').symlink_to(root / 'missing')
            self.assertTrue(scope.stop_present(root))


class ViewportTests(unittest.IsolatedAsyncioTestCase):
    def page(self):
        return types.SimpleNamespace(evaluate=AsyncMock(return_value={'width': 1440, 'height': 1000}),
            _nox_transport_cdp=types.SimpleNamespace(send=AsyncMock(return_value={
                'cssLayoutViewport': {'clientWidth': 1440, 'clientHeight': 1000},
                'cssVisualViewport': {'clientWidth': 1440, 'clientHeight': 1000}})))

    async def test_single_fixed_viewport_is_verified_without_resize_or_screenshot(self):
        core, transport, _, _ = installed()
        page = types.SimpleNamespace(evaluate=AsyncMock(return_value={'width': 1440, 'height': 1000}),
            _nox_transport_cdp=types.SimpleNamespace(send=AsyncMock(return_value={
                'cssLayoutViewport': {'clientWidth': 1440, 'clientHeight': 1000},
                'cssVisualViewport': {'clientWidth': 1440, 'clientHeight': 1000}})))
        report = {}
        with patch.object(core, 'stop_present', return_value=False):
            await scope.fixed_viewport(core, transport, page, report)
            self.assertTrue(report['fixed_viewport_proof']['matches'])
            page.evaluate.return_value = {'width': 1280, 'height': 720}
            with self.assertRaisesRegex(RuntimeError, 'FIXED_VIEWPORT'):
                await scope.fixed_viewport(core, transport, page, {})
        self.assertEqual(page._nox_transport_cdp.send.await_args.args, ('Page.getLayoutMetrics',))

    async def test_diagnostic_dom_timeout_does_not_invent_viewport_or_stream_acceptance(self):
        core, transport, _, _ = installed(); page = self.page(); report = {}
        page.evaluate.side_effect = TimeoutError()
        with patch.object(core, 'stop_present', return_value=False):
            await scope.fixed_viewport(core, transport, page, report)
        record = report['fixed_viewport_diagnostic']
        self.assertEqual(record['reason'], 'FIXED_VIEWPORT_DOM_TIMEOUT')
        self.assertFalse(record['verified'])
        self.assertNotIn('fixed_viewport_proof', report)
        self.assertNotIn('stream_only_acceptance_verified', report)
        page._nox_transport_cdp.send.assert_not_awaited()

    async def test_cdp_timeout_preserves_dom_measurement_and_distinct_stage(self):
        core, transport, _, _ = installed(); page = self.page(); report = {}
        page._nox_transport_cdp.send.side_effect = TimeoutError()
        with patch.object(core, 'stop_present', return_value=False):
            await scope.fixed_viewport(core, transport, page, report)
        record = report['fixed_viewport_diagnostic']
        self.assertEqual(record['reason'], 'FIXED_VIEWPORT_CDP_TIMEOUT')
        self.assertEqual([x['state'] for x in record['samples']], ['OBSERVED', 'TIMEOUT'])
        self.assertFalse(record['verified'])

    async def test_measured_dom_mismatch_stops_even_if_cdp_would_timeout(self):
        core, transport, _, _ = installed(); page = self.page()
        page.evaluate.return_value = {'width': 1280, 'height': 720}
        page._nox_transport_cdp.send.side_effect = TimeoutError()
        with patch.object(core, 'stop_present', return_value=False), self.assertRaisesRegex(RuntimeError, 'FIXED_VIEWPORT'):
            await scope.fixed_viewport(core, transport, page, {})
        page._nox_transport_cdp.send.assert_not_awaited()

    async def test_diagnostic_cancellation_and_owner_stop_never_become_soft_timeouts(self):
        core, transport, _, _ = installed(); page = self.page()
        page.evaluate.side_effect = asyncio.CancelledError()
        with patch.object(core, 'stop_present', return_value=False), self.assertRaises(asyncio.CancelledError):
            await scope.fixed_viewport(core, transport, page, {})
        page.evaluate.side_effect = TimeoutError()
        with patch.object(core, 'stop_present', side_effect=[False, True]), self.assertRaisesRegex(RuntimeError, 'HOLD_OWNER_STOP'):
            await scope.fixed_viewport(core, transport, page, {})

    async def test_operation_timeout_is_not_outer_deadline(self):
        core = types.SimpleNamespace(browser_run=AsyncMock(side_effect=TimeoutError()))
        with self.assertRaisesRegex(RuntimeError, 'BROWSER_OPERATION_TIMEOUT'):
            await scope.browser_operation(core, {}, None, {})
        core.browser_run.side_effect = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await scope.browser_operation(core, {}, None, {})


class EntryTests(unittest.TestCase):
    def test_existing_runtime_validation_cannot_create_or_install_missing_runtime(self):
        with tempfile.TemporaryDirectory() as folder:
            area = Path(folder) / 'browser_qa'; area.mkdir(mode=0o700)
            with patch.object(entry, 'AREA', area), patch.object(entry.subprocess, 'Popen') as popen:
                with self.assertRaises(FileNotFoundError):
                    entry.existing_runtime()
                self.assertEqual(list(area.iterdir()), [])
                popen.assert_not_called()
            marker = area / 'owner-environment.json'
            marker.write_text(json.dumps(entry.ENV_SPEC)); marker.chmod(0o600)
            (area / 'venv/bin').mkdir(parents=True)
            target = area / 'trusted-python'; target.write_bytes(b'fixture'); target.chmod(0o700)
            python = area / 'venv/bin/python'; python.symlink_to(target)
            before = marker.read_bytes()
            with patch.object(entry, 'AREA', area):
                self.assertEqual(entry.existing_runtime(), python)
                marker.chmod(0o644)
                with self.assertRaisesRegex(RuntimeError, 'RUNTIME_MARKER'):
                    entry.existing_runtime()
            self.assertEqual(before, marker.read_bytes())

    def test_child_environment_does_not_forward_owner_secrets_or_debug(self):
        with patch.dict(os.environ, {'PRIVATE_KEY': 'secret', 'DEBUG': 'secret', 'PWDEBUG': '1',
                                     'NOX_CHAT_PASSWORD': 'private', 'CUDA_VISIBLE_DEVICES': '1'}):
            value = entry.child_environment('123', 'a' * 40)
        self.assertEqual(value['CUDA_VISIBLE_DEVICES'], '')
        for key in ('PRIVATE_KEY', 'DEBUG', 'PWDEBUG', 'NOX_CHAT_PASSWORD'):
            self.assertNotIn(key, value)

    def test_outer_timeout_terminates_only_new_qa_process_group(self):
        process = Mock(pid=234567, returncode=-15)
        process.communicate.side_effect = [subprocess.TimeoutExpired(['private'], 165), (None, None)]
        with patch.object(entry, 'stop_present', return_value=False), patch.object(entry.subprocess, 'Popen', return_value=process) as popen, patch.object(entry.os, 'killpg') as kill:
            with self.assertRaisesRegex(RuntimeError, 'CHILD_TIMEOUT'):
                entry.run_child(Path('/already/installed/python'), b'public program', '123', 'a' * 40)
        self.assertTrue(popen.call_args.kwargs['start_new_session'])
        self.assertEqual(kill.call_args.args, (234567, signal.SIGTERM))
        self.assertEqual(popen.call_args.args[0], ['/already/installed/python', '-I', '-B', '-'])

    def test_nonzero_hold_result_cannot_become_acceptance_or_leak_stderr(self):
        value = {'schema': scope.SCHEMA, 'request': '123', 'source_sha': 'a' * 40,
            'state': 'HOLD', 'reason': 'HOLD_PROGRESSIVE_STREAM_NOT_OBSERVED',
            'stream_only_acceptance_verified': False, 'full_browser_qa_promoted': False,
            'upstream_model_inference_verified': False}
        def launch(argv, **kwargs):
            kwargs['stdout'].write((entry.PREFIX + json.dumps({'kind': 'browser_stream_only_receipt', 'data': value}) + '\n').encode())
            kwargs['stderr'].write(b'private cookie and password')
            return Mock(pid=12, returncode=2, communicate=Mock(return_value=(None, None)))
        with patch.object(entry, 'stop_present', return_value=False), patch.object(entry.subprocess, 'Popen', side_effect=launch), patch.object(entry, 'emit') as emit:
            self.assertEqual(entry.run_child(Path('/already/python'), b'program', '123', 'a' * 40), 2)
        self.assertNotIn('private', json.dumps(emit.call_args.args))
        self.assertEqual(emit.call_args.args[1]['state'], 'HOLD')


if __name__ == '__main__':
    unittest.main()
