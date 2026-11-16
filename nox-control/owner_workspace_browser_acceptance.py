#!/usr/bin/env python3
"""Passive workspace capability acceptance over the pinned page diagnostic."""
import base64
import hashlib
import json
import re
import types

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

BASE = 'owner_chat_page_diagnose.py'
BASE_SHA = '9587860e23ee3617bd47afb3dd15ba677e4e9f3f6d80774599de59cb1a14dc8a'
ASSET_PATH = '/nox-web-v29/pc/workspace.js'
ASSET_SHA = '984b604dc18d9a0c5224518e24b90e58b0b5e3bae89b2aa2996fec3dff5bb4a8'
ASSET_BYTES = 7278
SCHEMA = 'NOX_OWNER_WORKSPACE_BROWSER_ACCEPTANCE_V1'
KIND = 'workspace_browser_acceptance'
PINS = {
    BASE: BASE_SHA,
    'owner_browser_stream_only_entry.py': '2ec4dde5563dd5307b9c2136b97fe3079709253f7b9617ad1037efd7f260d999',
    'owner_chat_browser_qa.py': 'b76198d8117c3912fb7e1a1ef19c01abc41aa3ac87f4ad919612342edf593587',
}


def require(ok, code):
    if not ok:
        raise RuntimeError('HOLD_WORKSPACE_BROWSER_' + code)


WORKSPACE_JS = r"""async () => {
 const w=window.NoxWorkspace;
 const out={native_flag:window.NOX_NATIVE_OWNER===true,workspace_native:w?.native===true,
   ready_resolved:false,ready_rejected:false,capability_schema:null,settings:null,storage_scope:null};
 if(!w||!w.ready||typeof w.ready.then!=='function')return out;
 let timer;
 try {
   await Promise.race([w.ready,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('WAIT')),4500);})]);
   out.ready_resolved=true;
 } catch(e) {out.ready_rejected=true;return out;}
 finally {if(timer!==undefined)clearTimeout(timer);}
 const cap=w.capabilities;
 out.capability_schema=cap?.schema==='NOX_NATIVE_UI_WORKSPACE_V1' ? cap.schema : null;
 out.settings=typeof cap?.settings==='boolean' ? cap.settings : null;
 const scope=w.storageScope;
 out.storage_scope=['BROWSER_VISUAL_PREFS','NATIVE_OWNER_PENDING','EXISTING_WEB_WORKSPACE','SERVER_SETTINGS'].includes(scope) ? scope : null;
 return out;
}"""

WORKSPACE_CAPTURE = r'''
            async def workspace_capture():
                if len(workspace_responses)!=1:
                    raise RuntimeError('HOLD_WORKSPACE_BROWSER_ASSET_RESPONSE_COUNT')
                asset=workspace_responses[0];request=asset.request
                parsed=urllib.parse.urlsplit(asset.url)
                if (parsed.scheme not in ('http','https') or parsed.netloc!=origin
                        or parsed.path!='/nox-web-v29/pc/workspace.js' or parsed.query or parsed.fragment
                        or request.method!='GET' or request.resource_type!='script'
                        or request.frame!=page.main_frame or request.redirected_from is not None
                        or asset.status!=200 or asset.from_service_worker):
                    raise RuntimeError('HOLD_WORKSPACE_BROWSER_ASSET_RESPONSE_SCOPE')
                async def body():
                    headers=await asset.all_headers()
                    encoding=headers.get('content-encoding','identity').lower()
                    length=headers.get('content-length')
                    if encoding not in ('identity','gzip','br','deflate'):
                        raise RuntimeError('HOLD_WORKSPACE_BROWSER_ASSET_ENCODING')
                    if length is not None and (not re.fullmatch('[0-9]{1,8}',length) or not 0<int(length)<=16384):
                        raise RuntimeError('HOLD_WORKSPACE_BROWSER_ASSET_LENGTH')
                    if await asset.finished() is not None:
                        raise RuntimeError('HOLD_WORKSPACE_BROWSER_ASSET_UNFINISHED')
                    sizes=await request.sizes();wire=sizes.get('responseBodySize')
                    if type(wire) is not int or not 0<wire<=16384 or (length is not None and wire!=int(length)):
                        raise RuntimeError('HOLD_WORKSPACE_BROWSER_ASSET_WIRE_BOUND')
                    raw=await asset.body()
                    if len(raw)!=7278 or digest(raw)!='984b604dc18d9a0c5224518e24b90e58b0b5e3bae89b2aa2996fec3dff5bb4a8':
                        raise RuntimeError('HOLD_WORKSPACE_BROWSER_ASSET_SHA')
                    return {'schema':'NOX_BROWSER_WORKSPACE_ASSET_BINDING_V1','path':'/nox-web-v29/pc/workspace.js',
                        'sha256':digest(raw),'bytes':len(raw),'wire_bytes':wire,'same_page_response':True,
                        'additional_gets':0,'response_body_exported':False}
                report['workspace_asset']=await asyncio.wait_for(body(),timeout=3)
                report['workspace']=await page.evaluate(__WORKSPACE_JS_LITERAL__)
                value=report['workspace']
                if (not isinstance(value,dict) or value.get('native_flag') is not True
                        or value.get('workspace_native') is not True or value.get('ready_resolved') is not True
                        or value.get('ready_rejected') is not False
                        or value.get('capability_schema')!='NOX_NATIVE_UI_WORKSPACE_V1'
                        or value.get('settings') is not False or value.get('storage_scope')!='BROWSER_VISUAL_PREFS'):
                    raise RuntimeError('HOLD_WORKSPACE_BROWSER_CAPABILITY_BRANCH')
            workspace_started=time.monotonic()
            await asyncio.wait_for(workspace_capture(),timeout=5)
            report['workspace_observation_seconds']=round(time.monotonic()-workspace_started,3)
            report['workspace_proof_scope']='SAME_PAGE_PINNED_SCRIPT_AND_NATIVE_FALSE_SETTINGS_VISUAL_BRANCH'
            report['all_legacy_unauthorized_polling_fixed']=False
            report['workspace_diagnostic_base_sha256']='9587860e23ee3617bd47afb3dd15ba677e4e9f3f6d80774599de59cb1a14dc8a'
'''


def composed_tail(base):
    tail = base.PAGE_TAIL
    replacements = (
        ("            page_errors=collections.Counter();observed=[0];public_chat_response=[None]\n",
         "            page_errors=collections.Counter();observed=[0];public_chat_response=[None];workspace_responses=[]\n"
         "            report['workspace_acceptance_verified']=False\n"),
        ("                network[(route,status,kind)]+=1\n",
         "                network[(route,status,kind)]+=1\n"
         "                if route=='WORKSPACE_SCRIPT' and len(workspace_responses)<2:workspace_responses.append(response)\n"),
        ("            await page.wait_for_function(\"window.__NOX_OWNER_LIVE_UI===true && !!document.querySelector('#prompt')\",timeout=12000)\n",
         WORKSPACE_CAPTURE.replace('__WORKSPACE_JS_LITERAL__', repr(WORKSPACE_JS)) +
         "            await page.wait_for_function(\"window.__NOX_OWNER_LIVE_UI===true && !!document.querySelector('#prompt')\",timeout=12000)\n"),
        ("            if _page_stop():raise RuntimeError('HOLD_OWNER_STOP')\n            report['browser_stage']='OBSERVED'\n",
         "            if report.get('response_count_truncated'):raise RuntimeError('HOLD_WORKSPACE_BROWSER_RESPONSE_BOUND')\n"
         "            if len(workspace_responses)!=1:raise RuntimeError('HOLD_WORKSPACE_BROWSER_LATE_DUPLICATE_ASSET')\n"
         "            if _page_stop():raise RuntimeError('HOLD_OWNER_STOP')\n"
         "            report['workspace_acceptance_verified']=True\n            report['browser_stage']='OBSERVED'\n"),
    )
    for old, new in replacements:
        require(tail.count(old) == 1, 'COMPOSITION_SEAM')
        tail = tail.replace(old, new, 1)
    return tail


def prepared():
    raw = {}
    for name, pin in PINS.items():
        text = BUNDLE.get(name)
        require(isinstance(text, str) and 0 < len(text) <= 262144, 'BUNDLE_BOUND')
        data = base64.b64decode(text, validate=True)
        require(0 < len(data) <= 131072 and hashlib.sha256(data).hexdigest() == pin, 'BUNDLE_PIN')
        raw[name] = data
    base = types.ModuleType('_nox_workspace_browser_base')
    base.__file__ = '<' + BASE + '>'
    base.__dict__['__NOX_' + 'BUNDLE_JSON__'] = dict(BUNDLE)
    exec(compile(raw[BASE], base.__file__, 'exec'), base.__dict__)
    require(base.PINS == {name: pin for name, pin in PINS.items() if name != BASE}, 'RUNTIME_CLOSURE')
    base.PAGE_TAIL = composed_tail(base)
    base.LIBRARY_PATHS = {**base.LIBRARY_PATHS, ASSET_PATH: 'WORKSPACE_SCRIPT'}
    base.API_PATHS = frozenset((*base.API_PATHS, '/api/ui/capabilities'))
    base.SCHEMA = SCHEMA; base.KIND = KIND
    # This remains the reviewed auth-only route, polling, process deadline and cleanup.
    compile(base.browser_source(raw[base.CORE]), '<passive-workspace-browser>', 'exec')
    return base


def main():
    return prepared().main()


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        reason = str(exc)
        if not re.fullmatch('HOLD_[A-Z0-9_]{1,140}', reason):
            reason = 'HOLD_WORKSPACE_BROWSER_PREFLIGHT'
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': KIND, 'data': {
            'schema': SCHEMA, 'state': 'HOLD', 'reason': reason, 'private_content_exported': False}},
            separators=(',', ':')), flush=True)
        raise SystemExit(2)
