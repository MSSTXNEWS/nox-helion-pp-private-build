"""Focused normal-motion composition/control evidence; no native or browser run."""
import asyncio
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch

import owner_browser_normal_motion_entry as entry
import owner_chat_normal_motion_qa as normal

HERE = Path(__file__).parent


def installed():
    loaded = {}
    for name in ('owner_chat_browser_qa', 'owner_chat_browser_transport_qa',
                 'owner_chat_browser_release_qa', 'owner_chat_stream_only_qa'):
        raw = (HERE / (name + '.py')).read_bytes()
        module = types.ModuleType('_normal_test_' + name)
        exec(compile(raw, '<' + name + '>', 'exec'), module.__dict__)
        loaded[name] = module, raw
    core, raw = loaded['owner_chat_browser_qa']
    transport, traw = loaded['owner_chat_browser_transport_qa']
    release, rraw = loaded['owner_chat_browser_release_qa']
    scope, sraw = loaded['owner_chat_stream_only_qa']
    original_gate = core.progressive_stream_valid
    normal.install(core, raw, transport, traw, release, rraw, scope, sraw)
    return core, scope, release, original_gate


def stream():
    return {'motion_preference_no_preference': True, 'motion_preference_reduced': False,
        'motion_runtime_reduce': False, 'motion_runtime_eco': False, 'motion_runtime_stop': False,
        'normal_token_span_samples_before_done': 2, 'normal_token_span_peak_before_done': 3,
        'ui_token_span_peak': 3, 'native_calls': 1, 'ui_before_native_done': True,
        'ui_body_visible': True, 'dom_answer_matches_native': True,
        'ui_measurement_kind': 'CUMULATIVE_VISIBLE_ASSISTANT_BODY',
        'native_delta_count': 149, 'done': {'saved': True, 's03_integrated': True, 'dialog_matches': True},
        'answer_characters': 149, 'answer_normalized_characters': 110,
        'ui_prefix_lengths_before_done': [33, 66], 'ui_first_ms': 1000.0, 'native_done_ms': 2000.0}


def report():
    return {'state': 'STREAM_ONLY_ACCEPTED', 'scope': normal.SCOPE,
        'normal_motion_probe_schema': normal.PROBE_SCHEMA, 'browser_motion_preference': 'no-preference',
        'maximum_native_posts': 1, 'maximum_new_dialogs': 1, 'native_posts_admitted': 1,
        'production_configuration_changed': False, 'normal_motion_mode_verified': True,
        'stream_only_acceptance_verified': True, 'normal_motion_probe_verified': True,
        'strict_progressive_stream_observed': True, 'two_proper_prefixes_before_done': True,
        's03_readback_verified': True, 'synthetic_number_sequence_pass': True,
        'proper_prefix_count_before_done': 2, 'stream': stream()}


class CompositionTests(unittest.TestCase):
    def test_frozen_oracle_auth_single_post_and_excluded_stages_preserved(self):
        core, scope, _, original_gate = installed()
        self.assertIs(core.progressive_stream_valid, original_gate)
        self.assertEqual(core.EXPECTED, ','.join(map(str, range(1, 41))))
        self.assertIn('no-preference', core.browser_run.__code__.co_consts)
        self.assertNotIn('reduce', core.browser_run.__code__.co_consts)
        for name in ('capture_private_screenshot', 'check_report_layout', '_nox_responsive_layout',
                     'require_screenshot_captures', 'set_viewport_size'):
            self.assertNotIn(name, core.browser_run.__code__.co_names)
        for name in ('json_response', 'progressive_stream_valid', 'public_numeric_answer',
                     '_nox_wait_send_release', '_nox_wire_start', '_nox_route_evidence', 'budget'):
            self.assertIn(name, core.browser_run.__code__.co_names)
        self.assertIn('/chat/login', core.browser_run.__code__.co_consts)
        self.assertIn('/api/nox/stop', core.browser_run.__code__.co_consts)
        guard = next(v for v in core.browser_run.__code__.co_consts
                     if isinstance(v, types.CodeType) and v.co_name == 'guard')
        self.assertIn('native_admitted', guard.co_freevars)
        self.assertIn('duplicate_qa_generation', guard.co_consts)
        self.assertIn('POST', guard.co_consts)
        self.assertIn('normal_motion_', scope.main.__code__.co_consts)
        self.assertIn('_nox_normal_finalize', scope.main.__code__.co_names)

    def test_one_proper_prefix_stays_unaccepted_despite_normal_spans(self):
        core, scope, _, _ = installed(); value = stream()
        value['ui_prefix_lengths_before_done'] = [66]
        self.assertTrue(normal.normal_stream_valid(value))
        self.assertFalse(core.progressive_stream_valid(value))
        self.assertEqual(scope.proper_prefixes(value), [66])
        value['ui_prefix_lengths_before_done'] = [33, 66, 110]
        self.assertTrue(core.progressive_stream_valid(value))
        self.assertEqual(scope.proper_prefixes(value), [33, 66])

    def test_mode_guards_reject_reduction_eco_stop_unknown_and_boolean_counters(self):
        value = stream(); self.assertTrue(normal.normal_stream_valid(value))
        for key in ('motion_runtime_reduce', 'motion_runtime_eco', 'motion_runtime_stop', 'motion_preference_reduced'):
            self.assertFalse(normal.normal_stream_valid({**value, key: True}))
            self.assertFalse(normal.normal_stream_valid({**value, key: None}))
        self.assertFalse(normal.normal_stream_valid({**value, 'motion_preference_no_preference': False}))
        for key in ('normal_token_span_samples_before_done', 'normal_token_span_peak_before_done', 'ui_token_span_peak'):
            for invalid in (0, True, None, 513):
                self.assertFalse(normal.normal_stream_valid({**value, key: invalid}))
        self.assertFalse(normal.normal_stream_valid({**value, 'native_calls': True}))

    def test_no_post_is_not_observed_and_never_accepted(self):
        value = report(); value.update(state='HOLD', native_posts_admitted=0,
            normal_motion_probe_verified=False, stream_only_acceptance_verified=False)
        normal.finalize_observation(value)
        self.assertFalse(value['normal_animation_evaluated'])
        self.assertFalse(value['normal_motion_probe_verified'])
        self.assertEqual(value['normal_motion_observation_state'], 'NOT_OBSERVED_NO_POST')
        self.assertEqual(value['proper_prefix_observation_state'], 'NOT_OBSERVED_NO_POST')
        entry.receipt_scope(value)

    def test_final_success_is_scoped_and_cannot_promote_markdown_or_upstream(self):
        value = report(); normal.finalize_observation(value); entry.receipt_scope(value)
        self.assertTrue(value['normal_motion_probe_verified'])
        self.assertTrue(value['normal_animation_evaluated'])
        self.assertEqual(value['normal_motion_observation_state'], 'VERIFIED')
        for key in ('markdown_rendering_evaluated', 'client_gpu_performance_evaluated',
                    'full_browser_qa_evaluated', 'full_browser_qa_promoted',
                    'upstream_model_inference_verified', 'upstream_model_request_bound', 'upstream_SSE_binding_verified'):
            self.assertIs(value[key], False)
        value['normal_motion_probe_verified'] = False
        with self.assertRaisesRegex(RuntimeError, 'CHILD_ACCEPTANCE'):
            entry.receipt_scope(value)

    def test_changed_source_or_control_anchor_rejected_before_execution(self):
        with self.assertRaisesRegex(RuntimeError, 'SCOPE_PIN'):
            normal.install(None, b'', None, b'', None, b'', None, b'changed')
        with self.assertRaisesRegex(RuntimeError, 'AWAIT_SOURCE_MISSING'):
            normal.instrument_awaits('async def f():\n return 1\n',
                [('page.click()', ('DIALOG_PRIMARY_CLICK',))])

    def test_real_observer_counts_only_visible_normal_spans_before_done(self):
        core, _, _, _ = installed()
        observer = core.OBSERVER_JS.replace('__CONFIG__', '{"did":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}')
        harness = r"""
globalThis.window=globalThis;globalThis.innerWidth=1440;globalThis.innerHeight=1000;
const box=()=>({left:0,right:300,top:0,bottom:100,x:0,y:0,width:300,height:100});
let watchers=[];globalThis.MutationObserver=class{constructor(cb){this.cb=cb;}observe(){watchers.push(this.cb);}};
globalThis.HTMLCanvasElement=class{};HTMLCanvasElement.prototype.getContext=()=>null;
globalThis.requestAnimationFrame=cb=>cb();globalThis.fetch=async()=>({});
globalThis.addEventListener=(name,cb)=>{if(name==='DOMContentLoaded')cb();};
globalThis.getComputedStyle=()=>({display:'block',visibility:'visible',opacity:'1',contentVisibility:'visible',overflowX:'visible',overflowY:'visible'});
let spans=[{textContent:'1,',getBoundingClientRect:box,parentElement:null},{textContent:'2',getBoundingClientRect:box,parentElement:null}];
const body={innerText:'1,2',getBoundingClientRect:box,parentElement:null,querySelectorAll:()=>spans};
const mount={contains:node=>node===body||spans.includes(node)};
globalThis.document={hidden:false,getElementById:id=>id==='messages'?mount:null};
""" + observer + r"""
const q=window.__NOX_BROWSER_QA;q.started=performance.now();q.nativeCalls=1;q.answer='1,2,3,4';q.uiBody=body;
watchers.forEach(cb=>cb());
const first={samples:q.normalSpanSamples,peak:q.normalSpanPeak,prefixes:[...q.uiPrefixLengthsBeforeDone]};
q.nativeDone=50;body.innerText='1,2,3';watchers.forEach(cb=>cb());
const doneSamples=q.normalSpanSamples;
q.nativeDone=null;spans=[];watchers.forEach(cb=>cb());
console.log(JSON.stringify({first,doneSamples,withoutSpans:q.normalSpanSamples}));
"""
        result = subprocess.run(['node', '-e', harness], capture_output=True, text=True, timeout=5, check=True)
        value = json.loads(result.stdout)
        self.assertEqual(value['first'], {'samples': 1, 'peak': 2, 'prefixes': [3]})
        self.assertEqual(value['doneSamples'], 1)
        self.assertEqual(value['withoutSpans'], 1)


class AwaitTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        _, _, self.release, _ = installed()
        self.core = types.SimpleNamespace(stop_present=Mock(return_value=False))

    async def test_success_records_label_and_time_without_argument_or_result(self):
        value = {}; operation = AsyncMock(return_value={'private': 'argument and result'})
        actual = await normal.observe_await(self.core, self.release, value, 'DIALOG_SCROLL', operation)
        self.assertEqual(actual, {'private': 'argument and result'})
        record = value['control_awaits']['operations'][0]
        self.assertEqual(record['label'], 'DIALOG_SCROLL'); self.assertEqual(record['state'], 'RETURNED')
        self.assertGreaterEqual(record['elapsed_ms'], 0)
        self.assertNotIn('argument and result', json.dumps(value))

    async def test_timeout_is_categorical_and_retains_exact_failing_await(self):
        value = {}; operation = AsyncMock(side_effect=TimeoutError('Bearer secret https://host/?signed=private'))
        with self.assertRaises(TimeoutError):
            await normal.observe_await(self.core, self.release, value, 'DIALOG_HIT_TEST_AFTER', operation)
        record = value['control_awaits']['operations'][0]
        self.assertEqual(record['label'], 'DIALOG_HIT_TEST_AFTER')
        self.assertEqual(record['error_category'], 'BOUNDED_EVALUATION_TIMEOUT')
        self.assertNotIn('secret', json.dumps(value)); self.assertNotIn('https', json.dumps(value))

    async def test_cancellation_propagates_with_no_false_success(self):
        value = {}; operation = AsyncMock(side_effect=asyncio.CancelledError())
        with self.assertRaises(asyncio.CancelledError):
            await normal.observe_await(self.core, self.release, value, 'DIALOG_SELECTED_WAIT', operation)
        self.assertEqual(value['control_awaits']['operations'][0]['state'], 'CANCELLED')

    async def test_stop_prevents_operation_and_fixed_label_scope_is_mandatory(self):
        value = {}; operation = AsyncMock(); self.core.stop_present.return_value = True
        with self.assertRaisesRegex(RuntimeError, 'HOLD_OWNER_STOP'):
            await normal.observe_await(self.core, self.release, value, 'DIALOG_PRIMARY_CLICK', operation)
        operation.assert_not_awaited()
        self.assertEqual(value['control_awaits']['operations'][0]['state'], 'OWNER_STOP')
        with self.assertRaisesRegex(RuntimeError, 'AWAIT_LABEL'):
            await normal.observe_await(self.core, self.release, {}, 'private dynamic label', operation)


class EntryTests(unittest.TestCase):
    def bundle(self):
        return {name: base64.b64encode((HERE / name).read_bytes()).decode() for name in entry.PINS}

    def test_exact_six_source_closure_and_private_child_compile(self):
        with patch.object(entry, 'BUNDLE', self.bundle()):
            delegated, program = entry.prepared()
        self.assertEqual(len(entry.PINS), 6)
        self.assertEqual(set(delegated.PINS), set(entry.PINS) - {entry.ENTRY})
        compile(program, '<normal-motion-child>', 'exec')
        self.assertIn(b'normal.install(core,raw,transport,traw,release,rraw,scope,', program)
        self.assertIn(b'rc=scope.main(core)', program)
        self.assertNotIn(b'core.main()', program)
        self.assertEqual(delegated.run_child.__code__.co_filename, '<' + entry.ENTRY + '>')
        self.assertEqual(delegated.existing_runtime.__code__.co_filename, '<' + entry.ENTRY + '>')
        self.assertNotIn('owner_browser_runtime_repair_entry.py', entry.PINS)

    def test_tampered_helper_rejected_before_loading_or_browser(self):
        bundle = self.bundle(); bundle[entry.HELPER] = base64.b64encode(b'raise RuntimeError("must not execute")').decode()
        with patch.object(entry, 'BUNDLE', bundle), self.assertRaisesRegex(RuntimeError, 'BUNDLE_PIN'):
            entry.prepared()

    def test_parent_emit_preserves_hold_and_only_accepts_normal_proof(self):
        with patch.object(entry, 'BUNDLE', self.bundle()):
            delegated, _ = entry.prepared()
        bad = report(); normal.finalize_observation(bad); bad['browser_motion_preference'] = 'reduce'
        with self.assertRaisesRegex(RuntimeError, 'CHILD_SCOPE'):
            delegated.emit('browser_stream_only_receipt', bad)
        value = report(); value.update(state='HOLD', native_posts_admitted=0,
            normal_motion_probe_verified=False, stream_only_acceptance_verified=False)
        normal.finalize_observation(value)
        with patch('builtins.print') as output:
            delegated.emit('browser_stream_only_receipt', value)
        row = json.loads(output.call_args.args[0].split('=', 1)[1])
        self.assertEqual(row['kind'], 'browser_normal_motion_receipt')
        self.assertFalse(row['data']['normal_motion_probe_verified'])
        self.assertEqual(row['data']['normal_motion_observation_state'], 'NOT_OBSERVED_NO_POST')


if __name__ == '__main__':
    unittest.main()
