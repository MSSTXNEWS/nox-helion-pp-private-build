"""One normal-motion numeric turn with private, categorical await diagnostics.

The reduced-motion scope and all production sources stay frozen. This private
overlay preserves its native/auth/S03/strict-prefix oracle and adds evidence of
visible span.tok rendering before native done. It is not full UI or Markdown QA.
"""
from __future__ import annotations

import ast
import asyncio
import hashlib
import time

SCOPE_SHA = '534e09c9fd8ed0bbfc3c0e973eaf4790fa850b65e5483b4a011f8a92ce058e90'
SCOPE = 'AUTHENTICATED_NATIVE_ENDPOINT_VISIBLE_PARTIALS_S03_NORMAL_MOTION_ONLY'
PROBE_SCHEMA = 'NOX_OWNER_BROWSER_NORMAL_MOTION_PROBE_V1'
AWAIT_SCHEMA = 'NOX_OWNER_BROWSER_CONTROL_AWAITS_V1'
AWAIT_LABELS = frozenset((
    'DIALOG_LIST_COUNT', 'DIALOG_TITLE_COUNT', 'DIALOG_RAIL_TOGGLE_COUNT',
    'DIALOG_ATTACHED_WAIT', 'DIALOG_POST_ATTACH_COUNT', 'DIALOG_HIT_TEST_BEFORE',
    'DIALOG_RAIL_CLICK', 'DIALOG_RAIL_VISIBLE_WAIT', 'DIALOG_SCROLL',
    'DIALOG_PRIMARY_CLICK', 'DIALOG_HIT_TEST_AFTER', 'DIALOG_POINTER_CLICK',
    'DIALOG_SELECTED_WAIT', 'DIALOG_HISTORY_SETTLE', 'PROMPT_FILL', 'SEND_ENABLED_WAIT',
    'SEND_CONTROL_SEQUENCE', 'SEND_HIT_TEST_BEFORE', 'SEND_PRIMARY_CLICK',
    'SEND_NATIVE_COUNT_AFTER', 'SEND_HIT_TEST_AFTER', 'SEND_ENABLED_AFTER', 'SEND_POINTER_CLICK',
))


def require(ok, code):
    if not ok:
        raise RuntimeError('HOLD_NORMAL_MOTION_QA_' + code)


def replace_once(source, old, new):
    require(source.count(old) == 1, 'SOURCE_ANCHOR')
    return source.replace(old, new, 1)


def motion_mode_valid(value):
    return isinstance(value, dict) and all(value.get(key) is expected for key, expected in (
        ('motion_preference_no_preference', True), ('motion_preference_reduced', False),
        ('motion_runtime_reduce', False), ('motion_runtime_eco', False), ('motion_runtime_stop', False)))


def normal_stream_valid(value):
    if not motion_mode_valid(value):
        return False
    samples = value.get('normal_token_span_samples_before_done')
    peak = value.get('normal_token_span_peak_before_done')
    return bool(type(samples) is int and 1 <= samples <= 200
        and type(peak) is int and 1 <= peak <= 512
        and type(value.get('ui_token_span_peak')) is int and peak <= value['ui_token_span_peak'] <= 512
        and type(value.get('native_calls')) is int and value['native_calls'] == 1
        and value.get('ui_before_native_done') is True and value.get('ui_body_visible') is True
        and value.get('dom_answer_matches_native') is True)


def finalize_observation(report):
    """Absence of a POST is NOT_OBSERVED, never a rendering or quality PASS."""
    posts = report.get('native_posts_admitted')
    value = report.get('stream') or report.get('stream_final')
    observed = type(posts) is int and posts == 1
    verified = (observed and report.get('state') == 'STREAM_ONLY_ACCEPTED'
        and report.get('stream_only_acceptance_verified') is True
        and report.get('normal_motion_probe_verified') is True
        and report.get('strict_progressive_stream_observed') is True
        and report.get('two_proper_prefixes_before_done') is True
        and report.get('s03_readback_verified') is True and normal_stream_valid(value))
    report['normal_motion_probe_verified'] = bool(verified)
    report['normal_animation_evaluated'] = bool(observed and normal_stream_valid(value))
    report['normal_motion_observation_state'] = ('VERIFIED' if verified else
        'OBSERVED_NOT_ACCEPTED' if observed else 'NOT_OBSERVED_NO_POST')
    count = report.get('proper_prefix_count_before_done')
    report['proper_prefix_observation_state'] = ('NOT_OBSERVED_NO_POST' if not observed else
        'PROPER_PREFIXES_OBSERVED' if type(count) is int and count > 0 else 'NO_PROPER_PREFIX_OBSERVED')
    report['normal_animation_scope'] = 'VISIBLE_NORMAL_TOKEN_SPANS_ONLY_NOT_FPS_OR_FULL_GRAPHICS'
    report['markdown_rendering_evaluated'] = False
    report['client_gpu_performance_evaluated'] = False
    report['full_browser_qa_evaluated'] = False
    report['full_browser_qa_promoted'] = False
    report['upstream_model_inference_verified'] = False
    report['upstream_model_request_bound'] = False
    report['upstream_SSE_binding_verified'] = False


async def observe_await(core, release, report, label, operation):
    """Record fixed labels and elapsed time, never an argument, result or error text.

    Original Playwright operation timeouts and the enclosing 140s scope remain
    unchanged. Outer cancellation is recorded and propagated, not swallowed.
    """
    require(label in AWAIT_LABELS, 'AWAIT_LABEL')
    record = report.setdefault('control_awaits', {'schema': AWAIT_SCHEMA,
        'private_arguments_or_results_exported': False, 'raw_exceptions_exported': False,
        'operation_timeouts_changed': False, 'operations': []})
    rows = record['operations']; require(len(rows) < 48, 'AWAIT_RECORD_BOUND')
    row = {'label': label, 'state': 'WAITING'}; rows.append(row)
    started = time.monotonic()
    try:
        if core.stop_present():
            row['state'] = 'OWNER_STOP'
            raise RuntimeError('HOLD_OWNER_STOP')
        value = await operation()
        if core.stop_present():
            row['state'] = 'OWNER_STOP'
            raise RuntimeError('HOLD_OWNER_STOP')
        row['state'] = 'RETURNED'
        return value
    except asyncio.CancelledError:
        row['state'] = 'CANCELLED'
        raise
    except BaseException as exc:
        if row['state'] != 'OWNER_STOP':
            row.update(state='ERROR', error_category=release.error_category(exc))
        raise
    finally:
        row['elapsed_ms'] = round((time.monotonic() - started) * 1000, 3)


def instrument_awaits(source, specifications):
    """Wrap only exact fixed control expressions; reject source drift."""
    wanted = {ast.dump(ast.parse(expression, mode='eval').body): list(labels)
              for expression, labels in specifications}
    require(len(wanted) == len(specifications), 'AWAIT_SPEC_DUPLICATE')
    tree = ast.parse(source)

    class Instrument(ast.NodeTransformer):
        def visit_Await(self, node):
            key = ast.dump(node.value)
            if key not in wanted:
                return self.generic_visit(node)
            require(wanted[key] and not any(isinstance(n, ast.Await) for n in ast.walk(node.value)),
                    'AWAIT_SOURCE_DRIFT')
            label = wanted[key].pop(0); require(label in AWAIT_LABELS, 'AWAIT_LABEL')
            operation = ast.Lambda(args=ast.arguments(posonlyargs=[], args=[], kwonlyargs=[],
                kw_defaults=[], defaults=[]), body=node.value)
            call = ast.Call(func=ast.Name(id='_nox_normal_await', ctx=ast.Load()),
                args=[ast.Name(id='report', ctx=ast.Load()), ast.Constant(label), operation], keywords=[])
            return ast.copy_location(ast.Await(value=call), node)

    tree = Instrument().visit(tree)
    require(all(not labels for labels in wanted.values()), 'AWAIT_SOURCE_MISSING')
    ast.fix_missing_locations(tree)
    result = ast.unparse(tree)
    compile(result, '<normal-motion-control-awaits>', 'exec')
    return result


def rewrite_browser(source):
    source = replace_once(source, "reduced_motion='reduce'", "reduced_motion='no-preference'")
    source = replace_once(source,
        "            if before.get('motion_preference_reduced') is not True:\n"
        "                raise RuntimeError('HOLD_STREAM_ONLY_MOTION_PREFERENCE_NOT_APPLIED')\n",
        "            report['normal_motion_mode_verified']=_nox_normal_motion_mode(before)\n"
        "            if report['normal_motion_mode_verified'] is not True:\n"
        "                raise RuntimeError('HOLD_NORMAL_MOTION_QA_MODE_NOT_APPLIED')\n")
    source = replace_once(source,
        "    report['stream_only_acceptance_verified']=True",
        "    if not _nox_normal_stream_valid(report.get('stream')):\n"
        "        raise RuntimeError('HOLD_NORMAL_MOTION_QA_VISIBLE_TOKEN_SPANS_NOT_OBSERVED')\n"
        "    report['normal_motion_probe_verified']=True\n"
        "    report['stream_only_acceptance_verified']=True")
    specifications = (
        ("page.locator('#nativeChats').count()", ('DIALOG_LIST_COUNT',)),
        ('target.count()', ('DIALOG_TITLE_COUNT', 'DIALOG_POST_ATTACH_COUNT')),
        ("page.locator('[data-action=\"toggle-rail\"]').count()", ('DIALOG_RAIL_TOGGLE_COUNT',)),
        ("target.first.wait_for(state='attached',timeout=10000)", ('DIALOG_ATTACHED_WAIT',)),
        ('target.first.evaluate(CONTROL_JS)', ('DIALOG_HIT_TEST_BEFORE', 'DIALOG_HIT_TEST_AFTER')),
        ("page.locator('[data-action=\"toggle-rail\"]').first.click()", ('DIALOG_RAIL_CLICK',)),
        ('''page.wait_for_function("document.getElementById('v24Rail')?.dataset.collapsed!=='true' && Number(getComputedStyle(document.getElementById('v24Rail')).opacity)>.95",timeout=5000)''', ('DIALOG_RAIL_VISIBLE_WAIT',)),
        ('''target.first.evaluate("el=>el.scrollIntoView({block:'nearest',inline:'nearest',behavior:'instant'})")''', ('DIALOG_SCROLL',)),
        ('target.first.click(timeout=3500)', ('DIALOG_PRIMARY_CLICK',)),
        ("page.mouse.click(control['x'],control['y'])", ('DIALOG_POINTER_CLICK',)),
        ('''page.wait_for_function("title=>[...document.querySelectorAll('#nativeChats button[role=listitem]')].some(b=>b.getAttribute('aria-current')==='true'&&b.querySelector('.t')?.textContent===title)",arg=title,timeout=7000)''', ('DIALOG_SELECTED_WAIT',)),
        ('page.wait_for_timeout(350)', ('DIALOG_HISTORY_SETTLE',)),
        ("page.locator('#prompt').fill(prompt)", ('PROMPT_FILL',)),
        ('''page.wait_for_function("!document.querySelector('#chatForm [type=submit]').disabled",timeout=10000)''', ('SEND_ENABLED_WAIT',)),
        ('click_send(page, report)', ('SEND_CONTROL_SEQUENCE',)),
    )
    return instrument_awaits(source, specifications)


def rewritten_main(raw):
    text = raw.decode(); tree = ast.parse(text)
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
    source = ast.get_source_segment(text, node)
    source = replace_once(source, "('stream_only_' + request)", "('normal_motion_' + request)")
    source = replace_once(source, "'AUTHENTICATED_NATIVE_ENDPOINT_VISIBLE_PARTIALS_S03_REDUCED_MOTION_ONLY'", repr(SCOPE))
    source = replace_once(source, "'CPU_SWIFTSHADER_STREAM_ONLY_REDUCED_MOTION'", "'CPU_SWIFTSHADER_STREAM_ONLY_NORMAL_MOTION'")
    source = replace_once(source,
        "'browser_motion_preference': 'reduce', 'normal_animation_evaluated': False,",
        "'browser_motion_preference': 'no-preference', 'normal_animation_evaluated': False,\n"
        "            'normal_motion_probe_schema': 'NOX_OWNER_BROWSER_NORMAL_MOTION_PROBE_V1',\n"
        "            'normal_motion_probe_verified': False, 'normal_motion_mode_verified': False,\n"
        "            'normal_motion_observation_state': 'NOT_OBSERVED_NO_POST',\n"
        "            'proper_prefix_observation_state': 'NOT_OBSERVED_NO_POST',\n"
        "            'markdown_rendering_evaluated': False, 'client_gpu_performance_evaluated': False,")
    source = replace_once(source,
        "            require(report.get('stream_only_acceptance_verified') is True, 'ACCEPTANCE_MISSING')",
        "            require(report.get('stream_only_acceptance_verified') is True, 'ACCEPTANCE_MISSING')\n"
        "            require(report.get('normal_motion_probe_verified') is True, 'NORMAL_MOTION_ACCEPTANCE_MISSING')")
    return replace_once(source, "            report['finished_at'] = time.time()",
        "            _nox_normal_finalize(report)\n            report['finished_at'] = time.time()")


def install(core, raw, transport, traw, release, rraw, scope, sraw):
    require(hashlib.sha256(sraw).hexdigest() == SCOPE_SHA, 'SCOPE_PIN')
    original_gate = core.progressive_stream_valid
    original_rewrite = scope.rewrite_browser
    scope.rewrite_browser = lambda body: rewrite_browser(original_rewrite(body))
    scope.install(core, raw, transport, traw, release, rraw)
    require(core.progressive_stream_valid is original_gate, 'STRICT_GATE_CHANGED')
    core.SNAPSHOT_JS = replace_once(core.SNAPSHOT_JS,
        "   motion_preference_reduced:window.matchMedia('(prefers-reduced-motion: reduce)').matches,",
        "   motion_preference_reduced:window.matchMedia('(prefers-reduced-motion: reduce)').matches,\n"
        "   motion_preference_no_preference:window.matchMedia('(prefers-reduced-motion: no-preference)').matches,\n"
        "   motion_runtime_reduce:document.documentElement.dataset.reducedMotion==='reduce',\n"
        "   motion_runtime_eco:document.body.dataset.noxGfx==='ECO',\n"
        "   motion_runtime_stop:document.body.dataset.noxFx==='stop',")
    core.OBSERVER_JS = replace_once(core.OBSERVER_JS,
        '   uiVisible:false,uiMaxTokenSpans:0,contexts:[],draws:0,',
        '   uiVisible:false,uiMaxTokenSpans:0,normalSpanSamples:0,normalSpanPeak:0,contexts:[],draws:0,')
    core.OBSERVER_JS = replace_once(core.OBSERVER_JS,
        '     if(q.nativeDone===null){\n       q.uiBeforeDone=true;',
        '     if(q.nativeDone===null){\n       q.uiBeforeDone=true;\n'
        '       if(spans.length>0){q.normalSpanSamples=Math.min(200,q.normalSpanSamples+1);\n'
        '         q.normalSpanPeak=Math.max(q.normalSpanPeak,spans.length);}')
    core.SNAPSHOT_JS = replace_once(core.SNAPSHOT_JS,
        '   ui_token_span_peak:q.uiMaxTokenSpans,',
        '   ui_token_span_peak:q.uiMaxTokenSpans,\n'
        '   normal_token_span_samples_before_done:q.normalSpanSamples,\n'
        '   normal_token_span_peak_before_done:q.normalSpanPeak,')
    text = raw.decode(); tree = ast.parse(text)
    node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'click_send')
    click_source = instrument_awaits(ast.get_source_segment(text, node), (
        ('target.evaluate(CONTROL_JS)', ('SEND_HIT_TEST_BEFORE', 'SEND_HIT_TEST_AFTER')),
        ('target.click(timeout=3500)', ('SEND_PRIMARY_CLICK',)),
        ('page.evaluate(SNAPSHOT_JS)', ('SEND_NATIVE_COUNT_AFTER',)),
        ('target.is_enabled()', ('SEND_ENABLED_AFTER',)),
        ("page.mouse.click(control['x'],control['y'])", ('SEND_POINTER_CLICK',)),
    ))
    core.__dict__.update(_nox_normal_await=lambda report, label, operation:
        observe_await(core, release, report, label, operation),
        _nox_normal_motion_mode=motion_mode_valid, _nox_normal_stream_valid=normal_stream_valid)
    exec(compile(click_source, '<normal-motion-send-awaits>', 'exec'), core.__dict__)
    scope.__dict__['_nox_normal_finalize'] = finalize_observation
    exec(compile(rewritten_main(sraw), '<normal-motion-scope>', 'exec'), scope.__dict__)
    return core
