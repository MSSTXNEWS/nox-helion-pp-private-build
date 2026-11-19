"""Bounded read-only send-release observation layered over the frozen QA.

No UI or acceptance gate is changed. A separate two-part observation records
one visible proper prefix followed by the matching final response; the stricter
two-growing-prefixes-before-done criterion remains the original function.
"""
from __future__ import annotations

import ast
import asyncio
import hashlib
import math
import time

BASE_SHA = '96671d865167bc71ba9966e245cecb30d355813bf6b0180b2b94a566cd66bfc1'
TRANSPORT_SHA = '7a3cbcff6d075d078da3404b845cb04f7cf641d293cde94d7c7f25f754dc7ac6'
CONTROL_STATE_JS = r"""() => {
 const controls=document.querySelectorAll('#chatForm [type=submit]');
 const node=controls.length===1?controls[0]:null;
 const phases=['idle','thinking','speaking','stopped','error','done'];
 return {count:controls.length,present:!!node,disabled:node?node.disabled===true:null,
   phase:phases.includes(document.body?.dataset.noxPhase)?document.body.dataset.noxPhase:'OTHER'};
}"""


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise RuntimeError('HOLD_QA_RELEASE_SOURCE_ANCHOR')
    return source.replace(old, new, 1)


def error_category(exc):
    text = str(exc).lower()
    if 'closed' in text and any(x in text for x in ('page', 'context', 'browser', 'target')):
        return 'TARGET_CLOSED'
    if 'execution context' in text and any(x in text for x in ('destroyed', 'not found')):
        return 'EXECUTION_CONTEXT_CHANGED'
    if 'cannot read properties of null' in text or 'cannot read property' in text:
        return 'NULL_PROPERTY_EVALUATION'
    if isinstance(exc, TimeoutError) or 'timeout' in type(exc).__name__.lower() or 'timeout' in text:
        return 'BOUNDED_EVALUATION_TIMEOUT'
    if 'detached' in text:
        return 'FRAME_OR_NODE_DETACHED'
    return 'EVALUATION_ERROR'


def control_projection(value):
    if not isinstance(value, dict):
        raise RuntimeError('HOLD_QA_RELEASE_CONTROL_SCHEMA')
    count = value.get('count')
    if type(count) is not int or not 0 <= count <= 100 or type(value.get('present')) is not bool:
        raise RuntimeError('HOLD_QA_RELEASE_CONTROL_SCHEMA')
    disabled = value.get('disabled')
    if disabled is not None and type(disabled) is not bool:
        raise RuntimeError('HOLD_QA_RELEASE_CONTROL_SCHEMA')
    if value['present'] != (count == 1) or (count == 1) != (disabled is not None):
        raise RuntimeError('HOLD_QA_RELEASE_CONTROL_SCHEMA')
    return {'count': count, 'present': value['present'], 'disabled': disabled,
            'phase': value.get('phase') if value.get('phase') in
                ('idle', 'thinking', 'speaking', 'stopped', 'error', 'done') else 'OTHER'}


async def wait_send_release(page, report, stop):
    started = time.monotonic(); deadline = started+10
    record = {'state': 'OBSERVING', 'timeout_ms': 10000, 'attempts': 0,
              'error_counts': {}, 'last_control': None, 'raw_exception_exported': False}
    report['send_release_observation'] = record
    while True:
        if stop():
            record.update(state='HOLD', reason='HOLD_OWNER_STOP')
            raise RuntimeError('HOLD_OWNER_STOP')
        remaining = deadline-time.monotonic()
        if remaining <= 0:
            record.update(state='HOLD', reason='HOLD_QA_SEND_RELEASE_NOT_READY',
                          elapsed_ms=round((time.monotonic()-started)*1000))
            raise RuntimeError('HOLD_QA_SEND_RELEASE_NOT_READY')
        record['attempts'] += 1
        try:
            value = await asyncio.wait_for(page.evaluate(CONTROL_STATE_JS), timeout=min(1, remaining))
            observation = control_projection(value)
        except RuntimeError as exc:
            if str(exc) == 'HOLD_QA_RELEASE_CONTROL_SCHEMA':
                record.update(state='HOLD', reason=str(exc))
                raise
            category = error_category(exc)
            record['error_counts'][category] = record['error_counts'].get(category, 0)+1
            if category == 'TARGET_CLOSED':
                record.update(state='HOLD', reason='HOLD_QA_RELEASE_TARGET_CLOSED')
                raise RuntimeError('HOLD_QA_RELEASE_TARGET_CLOSED') from None
        except Exception as exc:
            category = error_category(exc)
            record['error_counts'][category] = record['error_counts'].get(category, 0)+1
            if category == 'TARGET_CLOSED':
                record.update(state='HOLD', reason='HOLD_QA_RELEASE_TARGET_CLOSED')
                raise RuntimeError('HOLD_QA_RELEASE_TARGET_CLOSED') from None
        else:
            record['last_control'] = observation
            if observation['count'] == 1 and observation['disabled'] is False:
                record.update(state='READY', elapsed_ms=round((time.monotonic()-started)*1000))
                return
        await asyncio.sleep(min(.1, max(0, deadline-time.monotonic())))


def two_parts_observed(value):
    """Separate observation; never substitutes for progressive_stream_valid."""
    if not isinstance(value, dict):
        return False
    first, done = value.get('ui_first_ms'), value.get('native_done_ms')
    count, prefixes = value.get('answer_characters'), value.get('ui_prefix_lengths_before_done')
    completed = value.get('done')
    return bool(type(value.get('native_calls')) is int and value['native_calls'] == 1 and value.get('ui_before_native_done') is True
        and value.get('ui_measurement_kind') == 'CUMULATIVE_VISIBLE_ASSISTANT_BODY'
        and value.get('ui_body_visible') is True and value.get('dom_answer_matches_native') is True
        and isinstance(completed, dict)
        and all(completed.get(k) is True for k in ('saved','owner_dialog_saved','dialog_matches'))
        and completed.get('s03_integrated') is False
        and completed.get('canonical_s03_write_verified') is False
        and completed.get('writer')=='V112_OWNER_DIALOG_WRITER'
        and type(count) is int and 3 <= count <= 4096 and isinstance(prefixes, list) and 1 <= len(prefixes) <= 80
        and all(type(n) is int and 3 <= n < count for n in prefixes)
        and all(a < b for a, b in zip(prefixes, prefixes[1:]))
        and type(first) in (int,float) and type(done) in (int,float)
        and math.isfinite(first) and math.isfinite(done) and 0 <= first < done)


def rewrite_browser(body):
    body = replace_once(body,
        "                report['browser_stage']='QA_TURN_'+str(turn_index+1)+'_SEND_RELEASE'\n"
        "                await page.wait_for_function(\"!document.querySelector('#chatForm [type=submit]').disabled\",timeout=10000)\n",
        "                report['browser_stage']='QA_TURN_'+str(turn_index+1)+'_SEND_RELEASE'\n"
        "                await _nox_wait_send_release(page,report)\n")
    body = replace_once(body,
        "                    report['stream_final']=await page.evaluate(SNAPSHOT_JS)\n",
        "                    report['stream_final']=await page.evaluate(SNAPSHOT_JS)\n"
        "                    report['two_parts_observed']=_nox_two_parts_observed(report['stream_final'])\n"
        "                    report['strict_progressive_stream_observed']=progressive_stream_valid(report['stream_final'])\n"
        "                    report['two_parts_observation_scope']='VISIBLE_PROPER_PREFIX_BEFORE_DONE_THEN_MATCHING_FINAL'\n")
    return body


def install(core, raw, transport, transport_raw):
    if hashlib.sha256(raw).hexdigest() != BASE_SHA or hashlib.sha256(transport_raw).hexdigest() != TRANSPORT_SHA:
        raise RuntimeError('HOLD_QA_RELEASE_DEPENDENCY_PIN')
    text = transport_raw.decode(); tree = ast.parse(text)
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'install')
    source = ast.get_source_segment(text, node)
    source = replace_once(source,
        "    exec(compile(body,'<reviewed-browser-transport-diagnostic>','exec'),core.__dict__)",
        "    exec(compile(_nox_release_rewrite(body),'<reviewed-browser-release-diagnostic>','exec'),core.__dict__)")
    transport.__dict__['_nox_release_rewrite'] = rewrite_browser
    exec(compile(source, '<reviewed-release-install>', 'exec'), transport.__dict__)
    async def release(page, report):
        await wait_send_release(page, report, core.stop_present)
    core.__dict__.update(_nox_wait_send_release=release, _nox_two_parts_observed=two_parts_observed)
    return transport.install(core, raw)
