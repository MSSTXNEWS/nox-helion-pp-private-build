"""One authenticated browser turn, visible prefixes and exact S03 readback.

This is a separate acceptance scope. It reuses pinned QA instrumentation without
the full UI screenshot/layout/resize stages and cannot promote the full UI QA.
The production UI, proxy, model, training and original QA sources are unchanged.
"""
from __future__ import annotations

import asyncio
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time

BASE_SHA = '9530c6e71274bbbca997f0aea07a26c988cfd536ed1aa1ba4067753827ac56f9'
TRANSPORT_SHA = 'e8d256f4ab4de1d53859c1da74237622871354b5d84442bdff1171631f9f05f0'
RELEASE_SHA = '42abf7b769b4103f9f3799048fe68da5c93937dbef9b56a8e4a2b5aac2072bc7'
SCHEMA = 'NOX_OWNER_BROWSER_STREAM_ONLY_QA_V1'
TOTAL_TIMEOUT = 140


def require(ok, code):
    if not ok:
        raise RuntimeError('HOLD_STREAM_ONLY_' + code)


def replace_once(source, old, new):
    require(source.count(old) == 1, 'SOURCE_ANCHOR')
    return source.replace(old, new, 1)


def replace_between(source, start, end, replacement):
    require(source.count(start) == source.count(end) == 1, 'SOURCE_RANGE')
    left, right = source.index(start), source.index(end)
    require(left < right, 'SOURCE_ORDER')
    return source[:left] + replacement + source[right:]


def stop_present(root):
    paths = [root / name for name in ('STOP', 'STOP.flag', 'stop.flag', '.stop', 'program/STOP', 'state/STOP')]
    paths.append(Path('/workspace/NOX_STOP'))
    return any(path.exists() or path.is_symlink() for path in paths)


def proper_prefixes(value):
    """Compare normalized visible prefixes with the normalized complete answer."""
    if not isinstance(value, dict):
        return []
    size = value.get('answer_normalized_characters')
    raw_size = value.get('answer_characters')
    prefixes = value.get('ui_prefix_lengths_before_done')
    if (type(size) is not int or type(raw_size) is not int or not 3 <= size <= raw_size <= 4096
            or not isinstance(prefixes, list) or not 1 <= len(prefixes) <= 80
            or any(type(n) is not int or not 3 <= n <= size for n in prefixes)
            or any(a >= b for a, b in zip(prefixes, prefixes[1:]))):
        return []
    return [n for n in prefixes if n < size]


def two_parts_observed(release, value):
    prefixes = proper_prefixes(value)
    if not prefixes:
        return False
    normalized = dict(value, answer_characters=value['answer_normalized_characters'],
                      ui_prefix_lengths_before_done=prefixes)
    return release.two_parts_observed(normalized)


async def fixed_viewport(core, transport, page, report):
    """Bounded supplemental geometry evidence, independent of stream acceptance.

    A missing diagnostic sample cannot establish a layout failure. A measured
    mismatch still stops this fixed-viewport run. Cancellation and owner STOP
    always propagate; neither is converted into a diagnostic timeout.
    """
    record = {'state': 'OBSERVING', 'stage': 'DOM', 'verified': False,
              'per_sample_timeout_seconds': 2, 'timeout_blocks_stream_test': False,
              'samples': []}
    report['fixed_viewport_diagnostic'] = record
    values = {}
    operations = (('DOM', lambda: page.evaluate(transport.VIEWPORT_JS)),
                  ('CDP', lambda: page._nox_transport_cdp.send('Page.getLayoutMetrics')))
    for stage, operation in operations:
        if core.stop_present():
            raise RuntimeError('HOLD_OWNER_STOP')
        record['stage'] = stage
        started = time.monotonic()
        try:
            values[stage] = await asyncio.wait_for(operation(), timeout=2)
        except TimeoutError:
            record['samples'].append({'stage': stage, 'state': 'TIMEOUT',
                'elapsed_ms': round((time.monotonic()-started)*1000, 3)})
            record.update(state='DIAGNOSTIC_TIMEOUT', reason='FIXED_VIEWPORT_' + stage + '_TIMEOUT')
            if core.stop_present():
                raise RuntimeError('HOLD_OWNER_STOP')
            return
        record['samples'].append({'stage': stage, 'state': 'OBSERVED',
            'elapsed_ms': round((time.monotonic()-started)*1000, 3)})
        if stage == 'DOM':
            require(isinstance(values[stage], dict)
                    and values[stage].get('width') == 1440 and values[stage].get('height') == 1000,
                    'FIXED_VIEWPORT')
    if core.stop_present():
        raise RuntimeError('HOLD_OWNER_STOP')
    proof = transport.viewport_projection(values['DOM'], values['CDP'], {'width': 1440, 'height': 1000})
    report['fixed_viewport_proof'] = proof
    record.update(state='VERIFIED' if proof['matches'] is True else 'MISMATCH',
                  verified=proof['matches'] is True)
    require(proof['matches'] is True, 'FIXED_VIEWPORT')


async def browser_operation(core, report, directory, available):
    """Keep an inner operation timeout distinct from the outer 140s deadline."""
    try:
        return await core.browser_run(report, directory, available)
    except TimeoutError as exc:
        raise RuntimeError('HOLD_STREAM_ONLY_BROWSER_OPERATION_TIMEOUT') from exc


def rewrite_browser(body):
    body = replace_once(body,
        "                                         base_url=base,service_workers='block',accept_downloads=False)",
        "                                         base_url=base,service_workers='block',accept_downloads=False,reduced_motion='reduce')")
    body = replace_once(body,
        "            before=await page.evaluate(SNAPSHOT_JS)\n            report['graphics_before']=before\n",
        "            before=await page.evaluate(SNAPSHOT_JS)\n            report['graphics_before']=before\n"
        "            if before.get('motion_preference_reduced') is not True:\n"
        "                raise RuntimeError('HOLD_STREAM_ONLY_MOTION_PREFERENCE_NOT_APPLIED')\n")
    body = replace_once(body,
        "    network=[];console=collections.Counter();page_errors=[];blocked=collections.Counter();did=None\n",
        "    network=[];console=collections.Counter();page_errors=[];blocked=collections.Counter();did=None;native_admitted=0\n")
    body = replace_once(body, "            async def guard(route):\n",
        "            async def guard(route):\n                nonlocal native_admitted\n")
    body = replace_once(body,
        "                        own=isinstance(body,dict) and body.get('message')==prompt and body.get('dialog_id')==did\n",
        "                        own=request.method=='POST' and isinstance(body,dict) and body.get('message')==prompt and body.get('dialog_id')==did\n")
    body = replace_once(body,
        "                    if not own:\n                        blocked['non_qa_generation']+=1\n                        return await route.abort()\n",
        "                    if not own:\n                        blocked['non_qa_generation']+=1\n                        return await route.abort()\n"
        "                    if native_admitted>=1:\n                        blocked['duplicate_qa_generation']+=1\n                        return await route.abort()\n"
        "                    native_admitted+=1\n")
    body = replace_once(body, "            report['actual_native_backend']=True\n",
        "            report['actual_native_backend']=True\n"
        "            report['owner_auth_verified']={'anonymous_status':401,'login_status':200,'session_status':200}\n")
    # In the stream-only QA, Playwright locator auto-wait could stall before any
    # native POST, despite the measured owner hit target already being visible.
    # Use exactly one physical click after a fresh, privacy-safe hit test; the
    # original aria-current wait below must still prove target selection.
    body = replace_between(body,
        "            report['browser_stage']='QA_DIALOG_CLICK'\n",
        '            await page.wait_for_function("title=>',
        "            report['browser_stage']='QA_DIALOG_CLICK'\n"
        "            control=await target.first.evaluate(CONTROL_JS)\n"
        "            report['qa_dialog_controls']['pointer_at_click']=control\n"
        "            if (not control['in_view'] or not control['pointer_hit_own_button']\n"
        "                    or control['rail_collapsed'] or control['rail_pointer_events']=='none'):\n"
        "                raise RuntimeError('HOLD_QA_DIALOG_POINTER_OCCLUDED')\n"
        "            if stop_present():\n"
        "                raise RuntimeError('HOLD_OWNER_STOP')\n"
        "            await page.mouse.click(control['x'],control['y'])\n"
        "            report['qa_dialog_controls']['physical_pointer_click']=True\n")
    body = replace_between(body,
        "            report['browser_stage']='QA_EMPTY_SCREENSHOT'\n",
        "            if stop_present():\n                raise RuntimeError('HOLD_OWNER_STOP')\n            idle_slots()\n",
        "            report['browser_stage']='STREAM_ONLY_FIXED_VIEWPORT'\n"
        "            await _nox_stream_only_viewport(page,report)\n")
    body = replace_once(body,
        "            report['browser_stage']='QA_REPORTS_COMPOSER_LAYOUT'\n"
        "            await check_report_layout(page,report)\n", '')
    body = replace_once(body, "            idle_slots()\n", "            report['resources_before_submit']=budget()\n")
    body = replace_once(body, "            report['browser_stage']='QA_SEND_CLICK'\n",
        "            report['resources_at_submit']=budget()\n"
        "            report['browser_stage']='QA_SEND_CLICK'\n")
    body = replace_between(body,
        "            masks=[page.locator(selector) for selector in SENSITIVE_MASKS]\n",
        "            if not report['progressive_stream_render_verified']:\n",
        "            report['two_parts_observed']=_nox_two_parts_observed(final)\n"
        "            report['proper_prefix_count_before_done']=len(_nox_proper_prefixes(final))\n"
        "            report['two_proper_prefixes_before_done']=report['proper_prefix_count_before_done']>=2\n"
        "            report['strict_progressive_stream_observed']=progressive_stream_valid(final)\n"
        "            if not report['authenticated_native_endpoint_stream_verified'] or not report['s03_readback_verified']:\n"
        "                raise RuntimeError('HOLD_STREAM_ONLY_NATIVE_OR_S03')\n")
    body = replace_once(body,
        "            if public!=EXPECTED:\n                raise RuntimeError('HOLD_SYNTHETIC_MODEL_QUALITY')\n",
        "            if not report['two_proper_prefixes_before_done']:\n"
        "                raise RuntimeError('HOLD_STREAM_ONLY_TWO_PROPER_PREFIXES_NOT_OBSERVED')\n"
        "            if public!=EXPECTED:\n                raise RuntimeError('HOLD_SYNTHETIC_MODEL_QUALITY')\n")
    body = replace_once(body,
        "                    report['two_parts_observed']=_nox_two_parts_observed(report['stream_final'])\n",
        "                    report['two_parts_observed']=_nox_two_parts_observed(report['stream_final'])\n"
        "                    report['proper_prefix_count_before_done']=len(_nox_proper_prefixes(report['stream_final']))\n"
        "                    report['two_proper_prefixes_before_done']=report['proper_prefix_count_before_done']>=2\n")
    body = replace_once(body,
        "    report['functional_acceptance_verified']=True\n    require_screenshot_captures(report)",
        "    report['stream_only_acceptance_verified']=True")
    body = replace_once(body, "                    if pending:\n",
        "                    if pending:\n"
        "                        report['session_stop_requested_for_own_pending_stream']=True\n")
    body = replace_once(body, "            report['privacy_guard_counts']=dict(blocked)\n",
        "            report['privacy_guard_counts']=dict(blocked)\n"
        "            report['native_posts_admitted']=native_admitted\n")
    for forbidden in ('capture_private_screenshot(', 'check_report_layout(', '_nox_responsive_layout(',
                      'require_screenshot_captures(', 'set_viewport_size('):
        require(forbidden not in body, 'EXCLUDED_STAGE_PRESENT')
    return body


def install(core, raw, transport, transport_raw, release, release_raw):
    require(tuple(hashlib.sha256(value).hexdigest() for value in (raw, transport_raw, release_raw))
            == (BASE_SHA, TRANSPORT_SHA, RELEASE_SHA), 'DEPENDENCY_PIN')
    original_gate = core.progressive_stream_valid
    original_rewrite = release.rewrite_browser
    release.rewrite_browser = lambda body: rewrite_browser(original_rewrite(body))
    release.install(core, raw, transport, transport_raw)
    require(core.progressive_stream_valid is original_gate, 'STRICT_GATE_CHANGED')
    core.SNAPSHOT_JS = replace_once(core.SNAPSHOT_JS, '   answer_characters:q.answer.length,',
        "   motion_preference_reduced:window.matchMedia('(prefers-reduced-motion: reduce)').matches,\n"
        '   answer_characters:q.answer.length,answer_normalized_characters:normalize(q.answer).length,')
    core.stop_present = lambda: stop_present(core.ROOT)
    core._nox_stream_only_viewport = lambda page, report: fixed_viewport(core, transport, page, report)
    core._nox_proper_prefixes = proper_prefixes
    core._nox_two_parts_observed = lambda value: two_parts_observed(release, value)
    return core


def private_directory(path, create=False):
    require(not path.is_symlink(), 'PRIVATE_DIRECTORY')
    if create:
        path.mkdir(mode=0o700, exist_ok=False)
    info = path.stat(follow_symlinks=False)
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid()
            and stat.S_IMODE(info.st_mode) == 0o700, 'PRIVATE_DIRECTORY')


def main(core):
    os.environ.pop('DEBUG', None); os.environ.pop('PWDEBUG', None)
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    require(bool(re.fullmatch(r'[0-9]{1,24}', request)) and bool(re.fullmatch(r'[a-f0-9]{40}', source)), 'OWNER_CONTEXT')
    available = core.inventory()
    require(available['playwright_installed'] is True and available['playwright_version'] == core.PLAYWRIGHT_PIN,
            'EXISTING_BROWSER_RUNTIME')
    require(not core.stop_present(), 'OWNER_STOP')
    private_directory(core.STATE)
    lock = os.open(core.STATE / 'qa.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(lock)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
                and stat.S_IMODE(info.st_mode) == 0o600, 'LOCK_SCOPE')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        directory = core.STATE / ('stream_only_' + request)
        private_directory(directory, create=True)
        os.nice(10)
        affinity = sorted(os.sched_getaffinity(0))
        if len(affinity) > 2:
            os.sched_setaffinity(0, set(affinity[:2]))
        report = {'schema': SCHEMA, 'scope': 'AUTHENTICATED_NATIVE_ENDPOINT_VISIBLE_PARTIALS_S03_REDUCED_MOTION_ONLY',
            'request': request, 'source_sha': source, 'started_at': time.time(), 'state': 'RUNNING',
            'actual_native_backend': False, 'authenticated_native_endpoint_stream_verified': False,
            'upstream_model_inference_verified': False, 'upstream_model_request_bound': False,
            'synthetic_backend_used': False, 'stream_only_acceptance_verified': False,
            'strict_progressive_gate_unchanged': True, 'two_parts_observed': False,
            'full_browser_qa_evaluated': False, 'full_browser_qa_promoted': False,
            'screenshot_or_layout_matrix_evaluated': False, 'screenshots_exported': False,
            'private_text_or_credentials_exported': False, 'production_configuration_changed': False,
            'session_stop_requested_for_own_pending_stream': False,
            'fixture_number_count': 40, 'maximum_new_dialogs': 1, 'maximum_native_posts': 1,
            'browser_endpoint_protocol': 'NDJSON', 'upstream_SSE_binding_verified': False,
            'artifacts': [], 'rendering_mode': 'CPU_SWIFTSHADER_STREAM_ONLY_REDUCED_MOTION',
            'browser_motion_preference': 'reduce', 'normal_animation_evaluated': False,
            'diagnostics_content': 'COUNTS_PUBLIC_NUMBERS_HASHES_AND_SAFE_ROUTE_CATEGORIES'}
        try:
            asyncio.run(asyncio.wait_for(browser_operation(core, report, directory, available), timeout=TOTAL_TIMEOUT))
            require(report.get('stream_only_acceptance_verified') is True, 'ACCEPTANCE_MISSING')
            report['state'] = 'STREAM_ONLY_ACCEPTED'
        except BaseException as exc:
            report.update(state='HOLD', reason='HOLD_STREAM_ONLY_TOTAL_TIMEOUT'
                          if isinstance(exc, TimeoutError) else core.safe_error(exc))
        finally:
            report['finished_at'] = time.time()
            raw = json.dumps(report, separators=(',', ':'), allow_nan=False).encode()
            require(len(raw) <= 100000, 'RECEIPT_LIMIT')
            core.write_private(directory / 'receipt.json', raw)
            core.emit('browser_stream_only_receipt', report)
        return 0 if report['state'] == 'STREAM_ONLY_ACCEPTED' else 2
    finally:
        os.close(lock)
