"""Concrete stream-only regressions. No native browser, service or model calls."""
import asyncio
import base64
from collections import Counter
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
    def test_missing_prepost_auth_lease_stop_resources_or_served_sha_blocks_model_post(self):
        base = {'owner_authenticated': True, 'lease_held': True, 'stop_clear': True,
                'resources': {'disk_free_bytes': 8 * 1024 ** 3, 'cgroup_headroom_bytes': 5 * 1024 ** 3},
                'served_asset_sha256': scope.SERVED_BRIDGE_SHA256}
        variants = [
            ('owner_authenticated', False, 'PREPOST_OWNER_AUTH'),
            ('lease_held', False, 'PREPOST_OWNER_LEASE'),
            ('stop_clear', False, 'PREPOST_OWNER_STOP'),
            ('resources', {'disk_free_bytes': 6 * 1024 ** 3, 'cgroup_headroom_bytes': 5 * 1024 ** 3}, 'PREPOST_DISK_RESERVE'),
            ('resources', {'disk_free_bytes': 8 * 1024 ** 3, 'cgroup_headroom_bytes': 3 * 1024 ** 3}, 'PREPOST_RAM_RESERVE'),
            ('served_asset_sha256', None, 'PREPOST_SERVED_ASSET_SHA'),
            ('served_asset_sha256', '0' * 64, 'PREPOST_SERVED_ASSET_SHA'),
        ]
        for field, value, hold in variants:
            with self.subTest(field=field, value=value):
                observed = dict(base, **{field: value})
                model_posts = []
                def submit_once():
                    scope.pre_post_admission(**observed)
                    model_posts.append('POST')
                with self.assertRaisesRegex(RuntimeError, hold):
                    submit_once()
                self.assertEqual(model_posts, [])

    def test_route_boundary_rechecks_stop_after_prepost_and_blocks_forwarding(self):
        observed = {'owner_authenticated': True, 'lease_held': True, 'stop_clear': True,
            'resources': {'disk_free_bytes': 8 * 1024 ** 3, 'cgroup_headroom_bytes': 5 * 1024 ** 3},
            'served_asset_sha256': scope.SERVED_BRIDGE_SHA256}
        scope.pre_post_admission(**observed)
        stop = {'present': False}
        report = {}
        blocked = Counter()
        route = types.SimpleNamespace(abort=AsyncMock(return_value='ABORTED'),
                                      continue_=AsyncMock(return_value='CONTINUED'))
        stop['present'] = True  # STOP appears after pre-post admission, before route forwarding.
        result = asyncio.run(scope.final_route_post_gate(lambda: stop['present'], report, blocked, route))
        self.assertEqual(result, 'ABORTED')
        route.abort.assert_awaited_once()
        route.continue_.assert_not_awaited()
        self.assertEqual(report['native_post_route_gate'], {
            'state': 'HOLD', 'reason': 'HOLD_OWNER_STOP', 'request_forwarded': False})
        self.assertEqual(blocked['owner_stop_before_native_post'], 1)

    def test_prepost_gate_is_compiled_before_single_send_click(self):
        core, _, _, _ = installed()
        constants = core.browser_run.__code__.co_consts
        joined = '\n'.join(value for value in constants if isinstance(value, str))
        names = core.browser_run.__code__.co_names
        self.assertIn('_nox_pre_post_admission', names)
        self.assertIn('_nox_served_bridge_sha256', names)
        import dis
        instructions = list(dis.get_instructions(core.browser_run))
        gate_offset = next(item.offset for item in instructions if item.opname in ('LOAD_GLOBAL', 'LOAD_NAME') and item.argval == '_nox_pre_post_admission')
        send_offset = next(item.offset for item in instructions if item.opname == 'LOAD_CONST' and item.argval == 'QA_SEND_CLICK')
        self.assertLess(gate_offset, send_offset)
        self.assertIn('PREPOST_SERVED_ASSET_SHA', scope.pre_post_admission.__code__.co_consts)

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
        # Keep the existing owner-authenticated admission and final STOP fence;
        # only two authorized synthetic turns may reach the model.
        self.assertIn('fresh_qa_post_admission', guard.co_names)
        self.assertIn('_nox_final_route_post_gate', guard.co_names)
        self.assertIn(False, guard.co_consts)
        self.assertIn('continue_', scope.final_route_post_gate.__code__.co_names)
        self.assertIn('abort', scope.final_route_post_gate.__code__.co_names)
        self.assertIn('duplicate_qa_generation', guard.co_consts)
        self.assertIn('answer_normalized_characters:normalize(q.answer).length', core.SNAPSHOT_JS)
        self.assertIn("window.matchMedia('(prefers-reduced-motion: reduce)').matches", core.SNAPSHOT_JS)
        self.assertIn('reduce', core.browser_run.__code__.co_consts)
        self.assertIn('HOLD_STREAM_ONLY_MOTION_PREFERENCE_NOT_APPLIED', core.browser_run.__code__.co_consts)
        self.assertEqual(core.EXPECTED, ','.join(map(str, range(1, 41))))

    def test_two_turn_challenge_uses_the_first_answer_without_leaking_it(self):
        core, _, _, _ = installed()
        with patch.object(scope.secrets, 'SystemRandom') as random:
            random.return_value.shuffle.side_effect = lambda numbers: numbers.reverse()
            prompt, follow_up, first, second = core._nox_dialogue_challenge('fixtureqa')
        self.assertEqual(first, ','.join(map(str, range(40, 0, -1))))
        self.assertNotEqual(second, '10,9,8,7,6,5,4,3,2,1')
        self.assertEqual(second, ','.join(first.split(',')[-10:][::-1]))
        self.assertTrue(prompt.endswith(first))
        self.assertTrue(follow_up.startswith('[NOX UI QA fixtureqa]'))
        self.assertFalse(any(character.isdigit() for character in follow_up))
        code = core.browser_run.__code__
        self.assertIn('_nox_dialogue_challenge', code.co_names)
        self.assertIn('first_expected', code.co_varnames)
        self.assertIn('second_expected', code.co_varnames)
        self.assertNotIn('10,9,8,7,6,5,4,3,2,1', code.co_consts)

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
    def test_failed_post_promotion_validation_restores_original_runtime(self):
        # Simulate the failure after the candidate directory was made live.
        # No browser, host service, package download or model is used.
        for had_previous in (True, False):
            with self.subTest(had_previous=had_previous), tempfile.TemporaryDirectory() as folder:
                root = Path(folder); area = root / 'browser_qa'
                if had_previous:
                    area.mkdir(mode=0o700)
                    (area / 'original.txt').write_text('keep-existing-runtime')
                def fake_install(args, env, code, timeout_sec=180):
                    if code == 'VENV':
                        child = Path(args[-1]) / 'bin/python'
                        child.parent.mkdir(parents=True)
                        child.write_bytes(b'new-candidate')
                        child.chmod(0o700)
                fake_spec = dict(entry.ENV_SPEC, base_python=os.path.realpath(os.sys.executable))
                with patch.object(entry, 'ROOT', root), patch.object(entry, 'AREA', area), \
                     patch.object(entry, 'ENV_SPEC', fake_spec), \
                     patch.object(entry, 'resource_budget'), \
                     patch.object(entry, 'plain_directory'), \
                     patch.object(entry, '_checked_install', side_effect=fake_install), \
                     patch.object(entry, 'existing_runtime', side_effect=[
                         FileNotFoundError('missing-old-runtime'),
                         RuntimeError('HOLD_POSTPROMOTION_RUNTIME_INVALID')]), \
                     patch.object(entry.shutil, 'disk_usage',
                                  return_value=types.SimpleNamespace(free=8 * 1024**3)):
                    with self.assertRaisesRegex(RuntimeError, 'HOLD_POSTPROMOTION_RUNTIME_INVALID'):
                        entry.ensure_runtime('123')
                self.assertEqual(sorted(path.name for path in root.iterdir()),
                                 ['browser_qa'] if had_previous else [])
                if had_previous:
                    self.assertEqual((area / 'original.txt').read_text(), 'keep-existing-runtime')
                else:
                    self.assertFalse(area.exists())

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

    def test_child_environment_requires_owner_served_html_pin(self):
        # The child cannot infer its pin from a response or a source marker.
        # A missing/invalid owner pin fails before any subprocess or model POST.
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, 'HOLD_STREAM_ONLY_ENTRY_SERVED_HTML_SHA256_PIN_MISSING'):
                entry.child_environment('123', 'a' * 40)
        for bad in ('', 'a' * 63, 'A' * 64, 'not-a-sha'):
            with self.subTest(pin=bad), patch.dict(os.environ, {
                    'NOX_OWNER_EXPECTED_SERVED_HTML_SHA256': bad}):
                with self.assertRaisesRegex(RuntimeError, 'HOLD_STREAM_ONLY_ENTRY_SERVED_HTML_SHA256_PIN_MISSING'):
                    entry.child_environment('123', 'a' * 40)

    def test_child_environment_does_not_forward_owner_secrets_or_debug(self):
        with patch.dict(os.environ, {'PRIVATE_KEY': 'secret', 'DEBUG': 'secret', 'PWDEBUG': '1',
                                     'NOX_CHAT_PASSWORD': 'private', 'CUDA_VISIBLE_DEVICES': '1',
                                     'NOX_OWNER_EXPECTED_SERVED_HTML_SHA256': 'f' * 64}):
            value = entry.child_environment('123', 'a' * 40)
        self.assertEqual(value['CUDA_VISIBLE_DEVICES'], '')
        self.assertEqual(value['NOX_OWNER_EXPECTED_SERVED_HTML_SHA256'], 'f' * 64)
        for key in ('PRIVATE_KEY', 'DEBUG', 'PWDEBUG', 'NOX_CHAT_PASSWORD'):
            self.assertNotIn(key, value)

    def test_resource_drift_after_bootstrap_blocks_child_before_spawn(self):
        # A freshly installed isolated browser may consume the RAM/disk
        # reserve previously checked in main(); the final gate must block.
        with patch.object(entry, 'resource_budget',
                          side_effect=RuntimeError('HOLD_STREAM_ONLY_ENTRY_RAM_RESERVE')) as budget, \
             patch.object(entry, 'stop_present') as stop, \
             patch.object(entry.subprocess, 'Popen') as launch:
            with self.assertRaisesRegex(RuntimeError, 'HOLD_STREAM_ONLY_ENTRY_RAM_RESERVE'):
                entry.run_child(Path('/already/python'), b'program', '123', 'a' * 40)
        budget.assert_called_once_with()
        stop.assert_not_called()
        launch.assert_not_called()

    def test_outer_timeout_terminates_only_new_qa_process_group(self):
        process = Mock(pid=234567, returncode=-15)
        process.communicate.side_effect = [subprocess.TimeoutExpired(['private'], 165), (None, None)]
        with patch.dict(os.environ, {'NOX_OWNER_EXPECTED_SERVED_HTML_SHA256': 'f' * 64}), \
             patch.object(entry, 'resource_budget'), \
             patch.object(entry, 'stop_present', return_value=False), \
             patch.object(entry.subprocess, 'Popen', return_value=process) as popen, \
             patch.object(entry.os, 'killpg') as kill:
            with self.assertRaisesRegex(RuntimeError, 'CHILD_TIMEOUT'):
                entry.run_child(Path('/already/installed/python'), b'public program', '123', 'a' * 40)
        self.assertTrue(popen.call_args.kwargs['start_new_session'])
        self.assertEqual(kill.call_args.args, (234567, signal.SIGTERM))
        self.assertEqual(popen.call_args.args[0], ['/already/installed/python', '-I', '-B', '-'])

    def test_nonzero_hold_result_cannot_become_acceptance_or_leak_stderr(self):
        value = {'schema': scope.SCHEMA, 'request': '123', 'source_sha': 'a' * 40,
            'state': 'HOLD', 'reason': 'HOLD_PROGRESSIVE_STREAM_NOT_OBSERVED',
            'stream_only_acceptance_verified': False, 'full_browser_qa_promoted': False,
            'upstream_model_inference_verified': False, 'two_turn_mode': True,
            'maximum_new_dialogs': 1, 'maximum_native_posts': 2,
            'first_turn_terminal_sse_verified': False,
            'authenticated_s03_history_readback_verified': False,
            'canonical_s03_receipt_verified': False,
            'canonical_s03_receipt_provider_present': False,
            'owner_authenticated_history_readback_gets': 0, 'native_posts_admitted': 0,
            'both_terminal_sse_done_records_saved_s03_integrated': False,
            'same_dialog_id': False, 'native_terminal_done_records': []}
        def launch(argv, **kwargs):
            kwargs['stdout'].write((entry.PREFIX + json.dumps({'kind': 'browser_stream_only_receipt', 'data': value}) + '\n').encode())
            kwargs['stderr'].write(b'private cookie and password')
            return Mock(pid=12, returncode=2, communicate=Mock(return_value=(None, None)))
        with patch.dict(os.environ, {'NOX_OWNER_EXPECTED_SERVED_HTML_SHA256': 'f' * 64}), \
             patch.object(entry, 'resource_budget'), \
             patch.object(entry, 'stop_present', return_value=False), \
             patch.object(entry.subprocess, 'Popen', side_effect=launch), \
             patch.object(entry, 'emit') as emit:
            self.assertEqual(entry.run_child(Path('/already/python'), b'program', '123', 'a' * 40), 2)
        self.assertNotIn('private', json.dumps(emit.call_args.args))
        self.assertEqual(emit.call_args.args[1]['state'], 'HOLD')


if __name__ == '__main__':
    unittest.main()
