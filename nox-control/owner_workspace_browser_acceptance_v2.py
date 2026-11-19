#!/usr/bin/env python3
"""Categorical phase diagnostics for the unchanged passive workspace acceptance."""
import base64
import hashlib
import json
import re
import types

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

BASE = 'owner_workspace_browser_acceptance.py'
BASE_SHA = '83cb9a19c2be4112b2f1c4fda40b838550a59524b1d3ac475b92e9f283f3548a'
SCHEMA = 'NOX_OWNER_WORKSPACE_BROWSER_ACCEPTANCE_V2'
KIND = 'workspace_browser_acceptance_v2'
PINS = {
    BASE: BASE_SHA,
    'owner_chat_page_diagnose.py': '9587860e23ee3617bd47afb3dd15ba677e4e9f3f6d80774599de59cb1a14dc8a',
    'owner_browser_stream_only_entry.py': '2ec4dde5563dd5307b9c2136b97fe3079709253f7b9617ad1037efd7f260d999',
    'owner_chat_browser_qa.py': 'b76198d8117c3912fb7e1a1ef19c01abc41aa3ac87f4ad919612342edf593587',
}


def require(ok, code):
    if not ok:
        raise RuntimeError('HOLD_WORKSPACE_BROWSER_V2_' + code)


def change_once(text, old, new):
    require(text.count(old) == 1, 'COMPOSITION_SEAM')
    return text.replace(old, new, 1)


PHASE_HELPER = r'''
            report['workspace_diagnostics']={'schema':'NOX_WORKSPACE_PASSIVE_PHASES_V1',
                'phase':'NOT_STARTED','steps':[],'timeout_scope':None,
                'durations_scope':'BROWSER_AUTOMATION_AWAIT_NOT_NETWORK_THROUGHPUT'}
            async def workspace_step(label,action):
                if label not in ('NAVIGATION','ASSET_HEADERS','ASSET_FINISHED','ASSET_SIZES',
                        'ASSET_BODY','WORKSPACE_READY','LIVE_UI_READY'):
                    raise RuntimeError('HOLD_WORKSPACE_BROWSER_PHASE_SCOPE')
                diagnostic=report['workspace_diagnostics']
                if len(diagnostic['steps'])>=12:
                    raise RuntimeError('HOLD_WORKSPACE_BROWSER_PHASE_BOUND')
                row={'phase':label,'state':'RUNNING','elapsed_seconds':0.0}
                diagnostic['steps'].append(row);diagnostic['phase']=label
                report['browser_stage']=label
                began=time.monotonic()
                try:
                    value=await action()
                except asyncio.CancelledError:
                    row.update(state='CANCELLED',exception_type='CANCELLED')
                    raise
                except Exception as exc:
                    category={'TimeoutError':'TIMEOUT','RuntimeError':'RUNTIME_ERROR',
                        'TypeError':'TYPE_ERROR','Error':'BROWSER_ERROR'}.get(type(exc).__name__,'OTHER_EXCEPTION')
                    row.update(state='FAILED',exception_type=category)
                    raise
                else:
                    row['state']='COMPLETE'
                    return value
                finally:
                    row['elapsed_seconds']=round(max(0.0,time.monotonic()-began),4)
'''


def instrument_capture(capture, workspace_js):
    text = capture.replace('__WORKSPACE_JS_LITERAL__', repr(workspace_js))
    changes = (
        ('headers=await asset.all_headers()',
         "headers=await workspace_step('ASSET_HEADERS',asset.all_headers)"),
        ('if await asset.finished() is not None:',
         "if await workspace_step('ASSET_FINISHED',asset.finished) is not None:"),
        ("sizes=await request.sizes();wire=sizes.get('responseBodySize')",
         "sizes=await workspace_step('ASSET_SIZES',request.sizes);wire=sizes.get('responseBodySize')"),
        ('raw=await asset.body()', "raw=await workspace_step('ASSET_BODY',asset.body)"),
        ("                report['workspace_asset']=await asyncio.wait_for(body(),timeout=3)\n",
         "                try:\n"
         "                    report['workspace_asset']=await asyncio.wait_for(body(),timeout=3)\n"
         "                except TimeoutError:\n"
         "                    report['workspace_diagnostics']['timeout_scope']='ASSET_BODY_3S'\n"
         "                    raise RuntimeError('HOLD_WORKSPACE_BROWSER_'+report['workspace_diagnostics']['phase']+'_TIMEOUT') from None\n"),
        ("report['workspace']=await page.evaluate(" + repr(workspace_js) + ')',
         "report['workspace']=await workspace_step('WORKSPACE_READY',lambda:page.evaluate(" + repr(workspace_js) + '))'),
        ('            await asyncio.wait_for(workspace_capture(),timeout=5)\n',
         "            try:\n"
         "                await asyncio.wait_for(workspace_capture(),timeout=5)\n"
         "            except TimeoutError:\n"
         "                report['workspace_diagnostics']['timeout_scope']='WORKSPACE_CAPTURE_5S'\n"
         "                raise RuntimeError('HOLD_WORKSPACE_BROWSER_'+report['workspace_diagnostics']['phase']+'_TIMEOUT') from None\n"),
    )
    for old, new in changes:
        text = change_once(text, old, new)
    return text


def prepared():
    blobs = {}
    for name, pin in PINS.items():
        value = BUNDLE.get(name)
        require(isinstance(value, str) and 0 < len(value) <= 262144, 'BUNDLE_BOUND')
        raw = base64.b64decode(value, validate=True)
        require(0 < len(raw) <= 131072 and hashlib.sha256(raw).hexdigest() == pin, 'BUNDLE_PIN')
        blobs[name] = raw
    wrapper = types.ModuleType('_workspace_acceptance_frozen')
    wrapper.__file__ = '<' + BASE + '>'
    wrapper.__dict__['__NOX_' + 'BUNDLE_JSON__'] = dict(BUNDLE)
    exec(compile(blobs[BASE], wrapper.__file__, 'exec'), wrapper.__dict__)
    require(wrapper.PINS == {k: v for k, v in PINS.items() if k != BASE}, 'FROZEN_CLOSURE')
    base = wrapper.prepared()
    old_capture = wrapper.WORKSPACE_CAPTURE.replace('__WORKSPACE_JS_LITERAL__', repr(wrapper.WORKSPACE_JS))
    tail = change_once(base.PAGE_TAIL, old_capture,
                       instrument_capture(wrapper.WORKSPACE_CAPTURE, wrapper.WORKSPACE_JS))
    tail = change_once(tail, "            report['browser_stage']='NAVIGATION'\n",
                       PHASE_HELPER + "            report['browser_stage']='NAVIGATION'\n")
    tail = change_once(tail, "response=await page.goto(base+'/',wait_until='domcontentloaded',timeout=20000)",
        "response=await workspace_step('NAVIGATION',lambda:page.goto(base+'/',wait_until='domcontentloaded',timeout=20000))")
    tail = change_once(tail,
        "await page.wait_for_function(\"window.__NOX_OWNER_LIVE_UI===true && !!document.querySelector('#prompt')\",timeout=12000)",
        "await workspace_step('LIVE_UI_READY',lambda:page.wait_for_function(\"window.__NOX_OWNER_LIVE_UI===true && !!document.querySelector('#prompt')\",timeout=12000))")
    base.PAGE_TAIL = tail
    base.SCHEMA = SCHEMA; base.KIND = KIND
    compile(base.browser_source(blobs[base.CORE]), '<workspace-phase-browser>', 'exec')
    return base


def main():
    return prepared().main()


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        reason = str(exc)
        if not re.fullmatch('HOLD_[A-Z0-9_]{1,140}', reason):
            reason = 'HOLD_WORKSPACE_BROWSER_V2_PREFLIGHT'
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': KIND, 'data': {
            'schema': SCHEMA, 'state': 'HOLD', 'reason': reason, 'private_content_exported': False}},
            separators=(',', ':')), flush=True)
        raise SystemExit(2)
