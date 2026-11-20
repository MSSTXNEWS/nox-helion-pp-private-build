"""Two owner-authenticated browser turns with an independent S03 history readback.

This is a separate acceptance scope. It reuses pinned QA instrumentation without
the full UI screenshot/layout/resize stages and cannot promote the full UI QA.
It requires terminal saved+s03_integrated records for both turns on one synthetic
dialog, then verifies the four ordered messages through the owner history route.
"""
from __future__ import annotations

import asyncio
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import time

BASE_SHA = '9530c6e71274bbbca997f0aea07a26c988cfd536ed1aa1ba4067753827ac56f9'
TRANSPORT_SHA = '360c155642ccdb43f39acf7b493068d3d2ac906bfd761c60d8c5ee51d48507fe'
RELEASE_SHA = 'eaa8af0e229c9ce0a730b7b472f8b9b8a1018fbd5cf7b8518890342d9d7047cb'
SERVED_BRIDGE_SHA256 = 'a7f64a536ac82cd5a1339cd31e63dfbb7dcf4feb34375c5128ec32279863af69'
SCHEMA = 'NOX_OWNER_BROWSER_STREAM_ONLY_QA_V2'
TOTAL_TIMEOUT = 230


def require(ok, code):
    if not ok:
        raise RuntimeError('HOLD_STREAM_ONLY_' + code)


def dialogue_challenge(token):
    """Keep stream length while making the follow-up depend on the first turn."""
    numbers = list(range(1, 41))
    secrets.SystemRandom().shuffle(numbers)
    if numbers[-10:] == list(range(1, 11)):
        numbers[-1], numbers[-2] = numbers[-2], numbers[-1]
    first = ','.join(map(str, numbers))
    second = ','.join(map(str, reversed(numbers[-10:])))
    label = '[NOX UI QA ' + token + '] '
    prompt = label + 'Повтори этот список чисел в том же порядке через запятую. Без пояснений: ' + first
    follow_up = label + ('Возьми последние десять чисел из своего предыдущего ответа '
                         'и напиши их в обратном порядке через запятую. Без пояснений.')
    return prompt, follow_up, first, second


def pre_post_admission(*, owner_authenticated, lease_held, stop_clear, resources, served_asset_sha256):
    """Fail closed immediately before the sole model POST."""
    require(owner_authenticated is True, 'PREPOST_OWNER_AUTH')
    require(lease_held is True, 'PREPOST_OWNER_LEASE')
    require(stop_clear is True, 'PREPOST_OWNER_STOP')
    require(isinstance(resources, dict), 'PREPOST_RESOURCE_SNAPSHOT')
    disk = resources.get('disk_free_bytes')
    ram = resources.get('cgroup_headroom_bytes')
    require(type(disk) is int and disk >= 7 * 1024 ** 3, 'PREPOST_DISK_RESERVE')
    require(type(ram) is int and ram >= 4 * 1024 ** 3, 'PREPOST_RAM_RESERVE')
    require(isinstance(served_asset_sha256, str)
            and re.fullmatch(r'[a-f0-9]{64}', served_asset_sha256)
            and served_asset_sha256 == SERVED_BRIDGE_SHA256, 'PREPOST_SERVED_ASSET_SHA')
    return {'owner_authenticated': True, 'qa_lease_held': True, 'stop_clear': True,
            'disk_floor_bytes': 7 * 1024 ** 3, 'ram_floor_bytes': 4 * 1024 ** 3,
            'served_asset_sha256': served_asset_sha256}


async def final_route_post_gate(stop_check, report, blocked, route):
    """Recheck STOP at the last network boundary and abort before the one POST."""
    try:
        stopped = stop_check()
    except Exception:
        stopped = None
    if stopped is not False:
        reason = 'HOLD_OWNER_STOP' if stopped is True else 'HOLD_OWNER_STOP_UNAVAILABLE'
        report['native_post_route_gate'] = {
            'state': 'HOLD', 'reason': reason, 'request_forwarded': False}
        blocked['owner_stop_before_native_post'] += 1
        return await route.abort()
    report['native_post_route_gate'] = {'state': 'CLEAR', 'stop_clear': True}
    return await route.continue_()


async def served_bridge_sha256(page):
    rows = await page.evaluate("""() => Array.from(document.scripts)
      .map(script => script.src ? new URL(script.src, location.href) : null)
      .filter(url => url && url.origin === location.origin
        && url.pathname.includes('nox-v135-resonance-owner-bridge'))
      .map(url => ({url:url.href, same_origin:url.origin === location.origin}))""")
    require(isinstance(rows, list) and len(rows) == 1
            and isinstance(rows[0], dict) and rows[0].get('same_origin') is True,
            'PREPOST_SERVED_ASSET_NOT_UNIQUE')
    response = await page.context.request.get(rows[0]['url'], max_redirects=0, timeout=6000)
    require(response.status == 200, 'PREPOST_SERVED_ASSET_HTTP')
    raw = await response.body()
    require(0 < len(raw) <= 2 * 1024 * 1024, 'PREPOST_SERVED_ASSET_SIZE')
    return hashlib.sha256(raw).hexdigest()


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
    paths.extend((Path('/workspace/NOX_STOP'),
                  Path('/root/nox/state/OWNER_MAINTENANCE.flag')))
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


def terminal_s03_records_valid(value, count):
    """Require exact terminal SSE done records for the one configured dialog."""
    records = value.get('done_records') if isinstance(value, dict) else None
    return (type(count) is int and isinstance(records, list) and len(records) == count
            and all(isinstance(record, dict) and record.get('saved') is True
                    and record.get('s03_integrated') is True
                    and record.get('dialog_matches') is True for record in records))


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
    body = replace_between(body, "    prompt='[NOX UI QA '+token+",
        "    second_permitted=False\n",
        "    prompt,second_prompt,first_expected,second_expected=_nox_dialogue_challenge(token)\n")
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
        "                        own=(request.method=='POST' and allowed_qa_request(\n"
        "                             stream_admitted,second_permitted,prompt,second_prompt,body,did))\n",
        "                        own=(request.method=='POST' and allowed_qa_request(\n"
        "                             stream_admitted,second_permitted,prompt,second_prompt,body,did))\n")
    body = replace_once(body,
        "                    if not own:\n                        blocked['non_qa_generation']+=1\n                        return await route.abort()\n",
        "                    if not own:\n                        blocked['non_qa_generation']+=1\n                        return await route.abort()\n"
        "                    if native_admitted>=2:\n                        blocked['duplicate_qa_generation']+=1\n                        return await route.abort()\n"
        "                    native_admitted+=1\n")
    body = replace_once(body,
        "                    # Consume admission before any uncertain network delivery:\n"
        "                    # never retry or double-submit an ambiguous native POST.\n"
        "                    stream_admitted+=1\n"
        "                return await route.continue_()\n",
        "                    # Consume admission before any uncertain network delivery:\n"
        "                    # never retry or double-submit an ambiguous native POST.\n"
        "                    stream_admitted+=1\n"
        "                    return await _nox_final_route_post_gate(report, blocked, route)\n"
        "                return await route.continue_()\n")
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
    # PR415 contains one idle_slots() inside the excluded screenshot/layout range.
    # Preserve the resource fence by binding the pre-submit check to the stable
    # composer input stage, which remains in the stream-only source.
    body = replace_once(body, "            report['browser_stage']='QA_PROMPT_FILL'\n",
        "            report['resources_before_submit']=budget()\n"
        "            report['served_asset_sha256']=await _nox_served_bridge_sha256(page)\n"
        "            report['browser_stage']='QA_PROMPT_FILL'\n")
    body = replace_once(body, "            report['browser_stage']='QA_SEND_CLICK'\n",
        "            report['resources_at_submit']=budget()\n"
        "            report['pre_post_admission']=_nox_pre_post_admission(\n"
        "                owner_authenticated=report.get('owner_auth_verified') == {'anonymous_status':401,'login_status':200,'session_status':200},\n"
        "                lease_held=report.get('owner_lease_held') is True,\n"
        "                stop_clear=not stop_present(), resources=report['resources_at_submit'],\n"
        "                served_asset_sha256=report.get('served_asset_sha256'))\n"
        "            report['browser_stage']='QA_SEND_CLICK'\n")
    body = replace_between(body,
        "            masks=[page.locator(selector) for selector in SENSITIVE_MASKS]\n",
        "            if not report['progressive_stream_render_verified']:\n",
        "            report['two_parts_observed']=_nox_two_parts_observed(final)\n"
        "            report['proper_prefix_count_before_done']=len(_nox_proper_prefixes(final))\n"
        "            report['two_proper_prefixes_before_done']=report['proper_prefix_count_before_done']>=2\n"
        "            report['strict_progressive_stream_observed']=progressive_stream_valid(final)\n"
        "            report['first_turn_terminal_sse_verified']=_nox_terminal_s03_records_valid(final,1)\n"
        "            report['authenticated_native_endpoint_stream_verified']=(\n"
        "                report.get('owner_auth_verified') == {'anonymous_status':401,'login_status':200,'session_status':200}\n"
        "                and report.get('actual_native_backend') is True and final.get('native_calls')==1)\n"
        "            if not report['authenticated_native_endpoint_stream_verified'] or not report['first_turn_terminal_sse_verified']:\n"
        "                raise RuntimeError('HOLD_STREAM_ONLY_NATIVE_OR_S03')\n")
    body = replace_once(body,
        "            if public!=EXPECTED:\n                raise RuntimeError('HOLD_SYNTHETIC_MODEL_QUALITY')\n",
        "            if not report['two_proper_prefixes_before_done']:\n"
        "                raise RuntimeError('HOLD_STREAM_ONLY_TWO_PROPER_PREFIXES_NOT_OBSERVED')\n"
        "            if public!=first_expected:\n                raise RuntimeError('HOLD_SYNTHETIC_MODEL_QUALITY')\n")
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

    body = replace_once(body,
        """            report['browser_stage']='QA_DIALOG_HISTORY'
            await page.wait_for_timeout(350)
            initial=await json_response(await context.request.get(
                base+'/api/ui/memory/dialogs/history?dialog_id='+did+'&limit=6',max_redirects=0,timeout=6000))
            if initial.get('messages')!=[]:
                raise RuntimeError('HOLD_SYNTHETIC_DIALOG_NOT_EMPTY')
            report['empty_dialog_history_verified']=True""",
        """            report['browser_stage']='QA_DIALOG_HISTORY'
            report['fresh_synthetic_dialog_preflight']=True""")
    body = replace_between(body,
        "            report['browser_stage']='QA_PERSISTED_HISTORY'\n",
        "            report['stop_visible_during_generation']",
        """            report['browser_stage']='QA_FIRST_TURN_TERMINAL_SSE'
            answer=await page.evaluate('window.__NOX_BROWSER_QA.answer')
            if not isinstance(answer,str) or not 1 <= len(answer) <= 4096:
                raise RuntimeError('HOLD_FIRST_TURN_ANSWER_BOUND')
            first_done=final.get('done') if isinstance(final,dict) else None
            first_terminal=_nox_terminal_s03_records_valid(final,1)
            saved=first_terminal
            native_equal=final.get('dom_answer_matches_native') is True
            public=public_numeric_answer(answer)
            report.update(stream=final,first_turn_terminal_sse_verified=first_terminal,
                          first_turn_sse_saved=isinstance(first_done,dict) and first_done.get('saved') is True,
                          first_turn_sse_s03_integrated=isinstance(first_done,dict) and first_done.get('s03_integrated') is True,
                          first_turn_sse_dialog_matches=isinstance(first_done,dict) and first_done.get('dialog_matches') is True,
                          actual_native_model_stream_verified=bool(final.get('native_calls')==1 and first_terminal),
                          answer_sha256=digest(answer.encode()),answer_characters=len(answer),
                          synthetic_number_sequence_pass=public==first_expected,
                          synthetic_public_numeric_answer=public,
                          progressive_stream_render_verified=progressive_stream_valid(final),
                          elapsed_turn_ms=round((time.monotonic()-started)*1000))
""")
    body = replace_once(body,
        """                report['browser_stage']='QA_SECOND_TURN_SEND'
""",
        """                report['resources_at_second_submit']=budget()
                report['served_asset_sha256_before_second_post']=await _nox_served_bridge_sha256(page)
                report['second_pre_post_admission']=_nox_pre_post_admission(
                    owner_authenticated=report.get('owner_auth_verified') == {'anonymous_status':401,'login_status':200,'session_status':200},
                    lease_held=report.get('owner_lease_held') is True,
                    stop_clear=not stop_present(), resources=report['resources_at_second_submit'],
                    served_asset_sha256=report['served_asset_sha256_before_second_post'])
                report['browser_stage']='QA_SECOND_TURN_SEND'
""")
    body = replace_once(body,
        """                if (not second_final or second_final.get('native_calls')!=2
                        or not second_final.get('done') or not second_final.get('dom_answer_matches_native')):
                    raise RuntimeError('HOLD_SECOND_TURN_STREAM_NOT_RENDERED')""",
        """                if (not second_final or second_final.get('native_calls')!=2
                        or not second_final.get('done') or not second_final.get('dom_answer_matches_native')
                        or not _nox_terminal_s03_records_valid(second_final,2)):
                    raise RuntimeError('HOLD_SECOND_TURN_STREAM_NOT_RENDERED')""")
    body = replace_between(body,
        "                # This endpoint is dialog-history, not the canonical S03 writer/readback.\n",
        "                if stream_admitted!=2:\n",
        """                second_public=public_numeric_answer(second_answer)
                second_progressive=progressive_stream_valid(second_final)
                second_done=isinstance(second_final.get('done'),dict) and all(
                    value is True for value in second_final['done'].values())
                terminal_pair_verified=_nox_terminal_s03_records_valid(second_final,2)
                same_dialog_id=terminal_pair_verified
                second_stop=bool(second_final.get('stop_samples',0)>0
                    and second_final.get('stop_samples')==second_final.get('stop_visible_samples')
                    and second_final.get('stop_occluded_samples')==0)
                history_verified=bool(second_saved and second_native_equal)
                authenticated_history=bool(
                    report.get('owner_auth_verified') == {'anonymous_status':401,'login_status':200,'session_status':200}
                    and history_verified)
                report.update(multiturn_dialog_history_verified=second_saved,
                              authenticated_s03_history_readback_verified=authenticated_history,
                              canonical_s03_receipt_verified=False,
                              canonical_s03_receipt_provider_present=False,
                              owner_authenticated_history_readback_gets=1,
                              both_terminal_sse_done_records_saved_s03_integrated=terminal_pair_verified,
                              same_dialog_id=same_dialog_id,
                              native_terminal_done_records=[
                                  {'saved':row.get('saved') is True,
                                   's03_integrated':row.get('s03_integrated') is True,
                                   'dialog_id_matches':row.get('dialog_matches') is True}
                                  for row in second_final.get('done_records',[])
                                  if isinstance(row,dict)],
                              multiturn_canonical_s03_verified=False,
                              multiturn_second_native_equal=second_native_equal,
                              multiturn_second_terminal_saved=second_done,
                              multiturn_second_visible_progressive=second_progressive,
                              multiturn_second_stop_visible=second_stop,
                              multiturn_second_answer_sha256=digest(second_answer.encode()),
                              multiturn_second_numeric_pass=second_public==second_expected,
                              multiturn_native_post_count=second_final['native_calls'],
                              multiturn_second_elapsed_ms=round((time.monotonic()-second_started)*1000))
                if not (terminal_pair_verified and same_dialog_id):
                    raise RuntimeError('HOLD_MULTITURN_TERMINAL_S03')
                if not authenticated_history:
                    raise RuntimeError('HOLD_AUTHENTICATED_S03_HISTORY_READBACK')
                if not (second_saved and second_native_equal and second_done
                        and second_progressive and second_stop
                        and second_public==second_expected):
                    raise RuntimeError('HOLD_MULTITURN_BROWSER')
""")
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
    core.OBSERVER_JS = replace_once(core.OBSERVER_JS,
        "   stopSamples:0,stopVisibleSamples:0,stopOccludedSamples:0};",
        "   stopSamples:0,stopVisibleSamples:0,stopOccludedSamples:0,doneRecords:[]};")
    core.OBSERVER_JS = replace_once(core.OBSERVER_JS,
        "           q.done={saved:frame.saved===true,s03_integrated:frame.s03_integrated===true,\n"
        "                   dialog_matches:frame.dialog_id===cfg.did};",
        "           q.done={saved:frame.saved===true,s03_integrated:frame.s03_integrated===true,\n"
        "                   dialog_matches:frame.dialog_id===cfg.did};\n"
        "           q.doneRecords.push({...q.done});")
    core.SNAPSHOT_JS = replace_once(core.SNAPSHOT_JS,
        "   native_bytes:q.nativeBytes,native_calls:q.nativeCalls,done:q.done,error:q.error,",
        "   native_bytes:q.nativeBytes,native_calls:q.nativeCalls,done:q.done,done_records:q.doneRecords,error:q.error,")
    require(core.progressive_stream_valid is original_gate, 'STRICT_GATE_CHANGED')
    core.SNAPSHOT_JS = replace_once(core.SNAPSHOT_JS, '   answer_characters:q.answer.length,',
        "   motion_preference_reduced:window.matchMedia('(prefers-reduced-motion: reduce)').matches,\n"
        '   answer_characters:q.answer.length,answer_normalized_characters:normalize(q.answer).length,')
    core.stop_present = lambda: stop_present(core.ROOT)
    core._nox_stream_only_viewport = lambda page, report: fixed_viewport(core, transport, page, report)
    core._nox_dialogue_challenge = dialogue_challenge
    core._nox_pre_post_admission = pre_post_admission
    core._nox_final_route_post_gate = lambda report, blocked, route: final_route_post_gate(core.stop_present, report, blocked, route)
    core._nox_served_bridge_sha256 = served_bridge_sha256
    core._nox_proper_prefixes = proper_prefixes
    core._nox_two_parts_observed = lambda value: two_parts_observed(release, value)
    core._nox_terminal_s03_records_valid = terminal_s03_records_valid
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
        report = {'schema': SCHEMA, 'scope': 'AUTHENTICATED_TWO_TURN_NATIVE_STREAM_S03_HISTORY_READBACK_REDUCED_MOTION_ONLY',
            'request': request, 'source_sha': source, 'started_at': time.time(), 'state': 'RUNNING',
            'owner_lease_held': True,
            'actual_native_backend': False, 'authenticated_native_endpoint_stream_verified': False,
            'authenticated_s03_history_readback_verified': False, 'canonical_s03_receipt_verified': False,
            'canonical_s03_receipt_provider_present': False, 'owner_authenticated_history_readback_gets': 0,
            'first_turn_terminal_sse_verified': False,
            'both_terminal_sse_done_records_saved_s03_integrated': False, 'same_dialog_id': False,
            'native_terminal_done_records': [], 'native_posts_admitted': 0,
            'upstream_model_inference_verified': False, 'upstream_model_request_bound': False,
            'synthetic_backend_used': False, 'stream_only_acceptance_verified': False,
            'strict_progressive_gate_unchanged': True, 'two_parts_observed': False,
            'full_browser_qa_evaluated': False, 'full_browser_qa_promoted': False,
            'screenshot_or_layout_matrix_evaluated': False, 'screenshots_exported': False,
            'private_text_or_credentials_exported': False, 'production_configuration_changed': False,
            'session_stop_requested_for_own_pending_stream': False, 'two_turn_mode': True,
            'fixture_number_count': 40, 'maximum_new_dialogs': 1, 'maximum_native_posts': 2,
            'browser_endpoint_protocol': 'NDJSON', 'upstream_SSE_binding_verified': False,
            'artifacts': [], 'rendering_mode': 'CPU_SWIFTSHADER_STREAM_ONLY_REDUCED_MOTION',
            'browser_motion_preference': 'reduce', 'normal_animation_evaluated': False,
            'diagnostics_content': 'COUNTS_PUBLIC_NUMBERS_HASHES_AND_SAFE_ROUTE_CATEGORIES'}
        try:
            asyncio.run(asyncio.wait_for(browser_operation(core, report, directory, available), timeout=TOTAL_TIMEOUT))
            require(report.get('native_posts_admitted') == 2, 'NATIVE_POST_COUNT')
            require(report.get('both_terminal_sse_done_records_saved_s03_integrated') is True
                    and report.get('same_dialog_id') is True, 'TERMINAL_S03_RECORDS')
            require(report.get('authenticated_s03_history_readback_verified') is True
                    and report.get('owner_authenticated_history_readback_gets') == 1,
                    'S03_HISTORY_READBACK')
            require(report.get('canonical_s03_receipt_verified') is False,
                    'CANONICAL_S03_RECEIPT_SCOPE')
            require(report.get('stream_only_acceptance_verified') is True, 'ACCEPTANCE_MISSING')
            report['state'] = 'STREAM_ONLY_ACCEPTED'
        except BaseException as exc:
            route_gate = report.get('native_post_route_gate')
            route_hold = (route_gate.get('reason') if isinstance(route_gate, dict)
                          and route_gate.get('state') == 'HOLD'
                          and route_gate.get('reason') in ('HOLD_OWNER_STOP', 'HOLD_OWNER_STOP_UNAVAILABLE')
                          and route_gate.get('request_forwarded') is False else None)
            report.update(state='HOLD', reason=route_hold or (
                'HOLD_STREAM_ONLY_TOTAL_TIMEOUT' if isinstance(exc, TimeoutError) else core.safe_error(exc)))
        finally:
            report['finished_at'] = time.time()
            raw = json.dumps(report, separators=(',', ':'), allow_nan=False).encode()
            require(len(raw) <= 100000, 'RECEIPT_LIMIT')
            core.write_private(directory / 'receipt.json', raw)
            core.emit('browser_stream_only_receipt', report)
        return 0 if report['state'] == 'STREAM_ONLY_ACCEPTED' else 2
    finally:
        os.close(lock)
