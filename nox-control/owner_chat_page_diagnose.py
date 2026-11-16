#!/usr/bin/env python3
"""Read one authenticated page: fixed public routes and Markdown capabilities.

Reuse the exact isolated Chromium runtime and frozen owner authentication.
No dialog, generation, tool, service, source, config or screenshot is created.
Only auth login/logout POSTs are allowed; page application mutations are blocked.
"""
from __future__ import annotations

import ast
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import time
import types
import urllib.parse

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

ENTRY = 'owner_browser_stream_only_entry.py'
CORE = 'owner_chat_browser_qa.py'
PINS = {
    ENTRY: '2ec4dde5563dd5307b9c2136b97fe3079709253f7b9617ad1037efd7f260d999',
    CORE: 'b76198d8117c3912fb7e1a1ef19c01abc41aa3ac87f4ad919612342edf593587',
}
PROXY = Path('/root/nox/scripts/chat_proxy.py')
PROXY_SHA = 'a427aa68ed7760380880c5d1c9ddb0714bef367ee5162a20602dbe43b6722d90'
SCHEMA = 'NOX_OWNER_CHAT_PAGE_DIAGNOSTIC_V1'
PREFIX = 'NOX_MAINT_REPAIR='
KIND = 'chat_page_diagnostic'
PUBLIC_CHAT_SOURCE_SHA = '06e9d15f1de53dc2e821cdcb5e0920f4332eef31ef22030e67bc63b0b859c237'
PUBLIC_CHAT_PATH = '/nox-web-v29/pc/v24/nox-v24-chat.js'
POLL_SECONDS = 32
API_PATHS = frozenset((
    '/api/nox/status', '/api/pc-metrics', '/api/nox/training-live', '/api/nox/progress',
    '/api/nox/birth', '/api/nox/memory', '/api/nox/creator', '/api/nox/history',
    '/api/nox/mood', '/api/nox/reminders/due', '/api/nox/weather', '/api/nox/session',
    '/api/settings', '/api/notifications', '/api/ui/executors', '/api/ui/memory/dialogs',
    '/api/ui/memory/dialogs/history', '/api/nox/self/observations', '/chat/session',
))
LIBRARY_PATHS = {
    '/nox-web-v29/pc/vendor/v22/marked.umd.js': 'MARKED_SCRIPT',
    '/nox-web-v29/pc/vendor/v22/purify.min.js': 'DOMPURIFY_SCRIPT',
    '/nox-web-v29/pc/vendor/v24/highlight.min.js': 'HIGHLIGHT_SCRIPT',
    PUBLIC_CHAT_PATH: 'PUBLIC_CHAT_SCRIPT',
    '/nox-web-v29/nox-v135-resonance-owner-bridge.js': 'OWNER_BRIDGE_SCRIPT',
}
PRIVATE_HISTORY = frozenset(('/api/nox/history', '/api/ui/memory/dialogs/history'))
MODEL_PATHS = frozenset(('/api/nox/chat', '/api/nox/chat/stream', '/api/nox/voice/speech'))
RESOURCE_TYPES = frozenset(('document', 'script', 'stylesheet', 'image', 'font', 'fetch', 'xhr', 'media', 'other'))


def require(ok, code):
    if not ok:
        raise RuntimeError('HOLD_PAGE_DIAGNOSTIC_' + code)


def safe(exc):
    value = str(exc)
    return value if re.fullmatch(r'HOLD_[A-Z0-9_]{1,130}', value) else type(exc).__name__


PROJECTORS = r'''
def category(url, origin):
    try:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme not in ('http', 'https') or parsed.netloc != origin:
            return 'OTHER_ORIGIN'
        if parsed.path in API_PATHS:
            return parsed.path
        if parsed.path in LIBRARY_PATHS:
            return LIBRARY_PATHS[parsed.path]
        if parsed.path in ('/', '/nox-web-v29/pc/resonance.html'):
            return 'OWNER_PAGE'
        return 'OTHER_API' if parsed.path.startswith('/api/') else 'OTHER_STATIC'
    except Exception:
        return 'UNCLASSIFIED'


def request_gate(method, url, origin):
    try:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme not in ('http', 'https') or parsed.netloc != origin:
            return 'EXTERNAL_ORIGIN'
        if method not in ('GET', 'HEAD'):
            return 'APPLICATION_MUTATION'
        if parsed.path in MODEL_PATHS:
            return 'MODEL_ENDPOINT'
        if parsed.path in PRIVATE_HISTORY:
            return 'PRIVATE_HISTORY'
        return None
    except Exception:
        return 'UNKNOWN_REQUEST'
'''
exec(compile(PROJECTORS, '<fixed-public-route-projectors>', 'exec'), globals())


LIBRARIES_JS = r"""() => {
 const version=v => typeof v==='string' && /^\d{1,3}(?:\.\d{1,3}){1,3}(?:[-+][0-9A-Za-z._-]{1,20})?$/.test(v) ? v : null;
 const m=window.marked,p=window.DOMPurify,h=window.hljs;
 const out={marked:{present:!!m,parse:typeof m?.parse==='function',version:version(m?.version||m?.VERSION)},
   dompurify:{present:!!p,sanitize:typeof p?.sanitize==='function',version:version(p?.version)},
   highlight:{present:!!h,highlight_element:typeof h?.highlightElement==='function',version:version(h?.versionString)},
   fixture:{attempted:false,passed:false,scope:'DETACHED_PUBLIC_LIBRARY_PIPELINE_ONLY',
     live_message_dom_changed:false,real_model_markdown_verified:false}};
 if(!out.marked.parse||!out.dompurify.sanitize||!out.highlight.highlight_element)return out;
 out.fixture.attempted=true;
 try {
   const text='# NOX\n\n**Bold** and *italic*.\n\n- one\n- two\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n> quote\n\n```javascript\nconst value = 7;\n```';
   const html=p.sanitize(m.parse(text,{breaks:true,gfm:true}),{USE_PROFILES:{html:true}});
   if(typeof html!=='string'||html.length>16384)throw Error('fixture');
   const node=document.createElement('div');node.innerHTML=html;
   node.querySelectorAll('pre code').forEach(c=>h.highlightElement(c));
   const dirty=p.sanitize('<script>throw 1</script><p onclick="throw 1">ok</p>',{USE_PROFILES:{html:true}});
   const checked=document.createElement('template');checked.innerHTML=dirty;
   const checks={heading:node.querySelectorAll('h1').length===1,strong:node.querySelectorAll('strong').length===1,
     emphasis:node.querySelectorAll('em').length===1,list_items:node.querySelectorAll('li').length===2,
     table:node.querySelectorAll('table').length===1,quote:node.querySelectorAll('blockquote').length===1,
     fenced_code:node.querySelectorAll('pre code.language-javascript').length===1,
     syntax_highlight:!!node.querySelector('pre code.hljs .hljs-keyword'),
     dangerous_markup_removed:!checked.content.querySelector('script,[onclick]')};
   out.fixture.checks=checks;out.fixture.passed=Object.values(checks).every(Boolean);
 } catch(e) {out.fixture.error='PUBLIC_LIBRARY_FIXTURE_ERROR';}
 return out;
}"""

PAGE_TAIL = r'''
            report['owner_auth_verified']=True
            report['auth_login_posts']=1
            network=collections.Counter();blocked=collections.Counter();console=collections.Counter()
            page_errors=collections.Counter();observed=[0];public_chat_response=[None]
            async def guard(route):
                code=_page_request_gate(route.request.method,route.request.url,origin)
                if _page_stop():code='OWNER_STOP'
                if code:
                    blocked[code]+=1
                    return await route.abort()
                return await route.continue_()
            await context.route('**/*',guard)
            page=await context.new_page()
            def response_seen(response):
                observed[0]+=1
                if observed[0]>512:
                    report['response_count_truncated']=True
                    return
                route=_page_category(response.url,origin)
                kind=response.request.resource_type
                if kind not in _page_resource_types:kind='other'
                status=response.status if type(response.status) is int and 100<=response.status<=599 else 0
                network[(route,status,kind)]+=1
                if route=='PUBLIC_CHAT_SCRIPT' and response.request.method=='GET' and response.status==200:
                    if public_chat_response[0] is None:public_chat_response[0]=response
                    else:report['public_chat_script_duplicate']=True
            def console_seen(message):
                if message.type in ('error','warning'):console[message.type]+=1
            def error_seen(error):
                matched=re.match(r'(TypeError|ReferenceError|SyntaxError|RangeError|Error)\b',str(error))
                page_errors[matched[1] if matched else 'JAVASCRIPT_EXCEPTION']+=1
            page.on('response',response_seen);page.on('console',console_seen);page.on('pageerror',error_seen)
            page.on('dialog',lambda dialog:asyncio.create_task(dialog.dismiss()))
            report['browser_stage']='NAVIGATION'
            response=await page.goto(base+'/',wait_until='domcontentloaded',timeout=20000)
            if response is None or response.status!=200 or urllib.parse.urlsplit(page.url).path!=PAGE:
                raise RuntimeError('HOLD_GRAPHICAL_OWNER_ROUTE')
            await page.wait_for_function("window.__NOX_OWNER_LIVE_UI===true && !!document.querySelector('#prompt')",timeout=12000)
            report['browser_stage']='PASSIVE_POLLING'
            sampled=time.monotonic()
            while time.monotonic()-sampled<_page_poll_seconds:
                if _page_stop():raise RuntimeError('HOLD_OWNER_STOP')
                await asyncio.sleep(.25)
            report['poll_observed_seconds']=round(time.monotonic()-sampled,3)
            report['libraries']=await asyncio.wait_for(page.evaluate(_page_libraries_js),timeout=4)
            report['public_chat_source']={'expected_sha256':_page_chat_sha,'state':'NOT_BOUND'}
            response=public_chat_response[0]
            if response is not None and not report.get('public_chat_script_duplicate'):
                async def public_body():
                    await response.finished()
                    sizes=await response.request.sizes()
                    size=sizes.get('responseBodySize')
                    if type(size) is not int or not 0<size<=65536:
                        raise RuntimeError('HOLD_PAGE_DIAGNOSTIC_PUBLIC_SCRIPT_WIRE_BOUND')
                    raw=await response.body()
                    if len(raw)>65536:raise RuntimeError('HOLD_PAGE_DIAGNOSTIC_PUBLIC_SCRIPT_BODY_BOUND')
                    return raw
                try:
                    raw=await asyncio.wait_for(public_body(),timeout=3)
                    report['public_chat_source'].update(state='OBSERVED',bytes=len(raw),sha256=digest(raw),
                        matches_reviewed_source=digest(raw)==_page_chat_sha)
                except Exception as exc:
                    report['public_chat_source'].update(state='UNBOUND',reason=safe_error(exc))
            if _page_stop():raise RuntimeError('HOLD_OWNER_STOP')
            report['browser_stage']='OBSERVED'
        finally:
            if 'network' in locals():
                report['network']=[{'path_category':key[0],'status':key[1],'resource_type':key[2],'count':count}
                    for key,count in sorted(network.items())]
                report['response_count']=min(observed[0],512)
                report['console_counts']=dict(console);report['page_exception_counts']=dict(page_errors)
                report['blocked_request_counts']=dict(blocked)
            try:
                await context.request.post(base+'/chat/logout',data={},max_redirects=0,timeout=3000)
                report['auth_logout_posts']=1
            except Exception:report['auth_logout_completed']=False
            password=None
            await context.close();await browser.close()
'''


def browser_source(raw):
    """Retain the exact launch/auth prefix; stop before first dialog creation."""
    require(hashlib.sha256(raw).hexdigest() == PINS[CORE], 'CORE_PIN')
    source = raw.decode()
    tree = ast.parse(source)
    functions = [node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == 'browser_run']
    require(len(functions) == 1, 'BROWSER_FUNCTION')
    original = ast.get_source_segment(source, functions[0])
    marker = "            created=await json_response(await context.request.post(base+'/api/ui/memory/dialogs/create',\n"
    require(original.count(marker) == 1, 'AUTH_SEAM')
    prefix = original[:original.index(marker)]
    old = "    report.update(nonloopback_auth=True,resources=budget(),synthetic_prompt_sha256=digest(prompt.encode()))\n"
    require(prefix.count(old) == 1, 'BUDGET_SEAM')
    prefix = prefix.replace(old, "    report.update(nonloopback_auth=True,resources=_page_budget())\n")
    # These variables were only for the omitted synthetic-dialog/generation path.
    prefix = '\n'.join(line for line in prefix.splitlines()
        if not line.startswith(('    token=', '    title=', '    prompt=', '    network=[];'))) + '\n'
    result = prefix + PAGE_TAIL
    compile(result, '<read-only-page-browser>', 'exec')
    require("'/api/ui/memory/dialogs/create'" not in result and "'/api/nox/chat/stream'" not in result,
            'NO_APPLICATION_POST')
    return result


def module(name, raw):
    value = types.ModuleType('_nox_page_' + name.removesuffix('.py'))
    value.__file__ = '<' + name + '>'
    exec(compile(raw, value.__file__, 'exec'), value.__dict__)
    return value


def sources():
    out = {}
    for name, pin in PINS.items():
        encoded = BUNDLE.get(name)
        require(isinstance(encoded, str) and 0 < len(encoded) <= 262144, 'BUNDLE_BOUND')
        raw = base64.b64decode(encoded, validate=True)
        require(0 < len(raw) <= 131072 and hashlib.sha256(raw).hexdigest() == pin, 'BUNDLE_PIN')
        out[name] = raw
    return out


def child_program(blobs):
    # Only reviewed definitions and our finite browser body are evaluated.
    return ("import asyncio,base64,hashlib,importlib.metadata,json,os,re,sys,time,types,urllib.parse\n"
        "sys.dont_write_bytecode=True\n"
        "if sys.prefix!='/root/nox/browser_qa/venv' or importlib.metadata.version('playwright')!='1.65.2':raise RuntimeError('HOLD_PAGE_DIAGNOSTIC_RUNTIME')\n"
        + 'blobs=' + repr({k: base64.b64encode(v).decode() for k,v in blobs.items()}) + '\n'
        + 'pins=' + repr(PINS) + '\nloaded={}\n'
        "for name,encoded in blobs.items():\n"
        " raw=base64.b64decode(encoded,validate=True)\n"
        " if hashlib.sha256(raw).hexdigest()!=pins[name]:raise RuntimeError('HOLD_PAGE_DIAGNOSTIC_CHILD_PIN')\n"
        " value=types.ModuleType('_page_'+name);value.__file__='<'+name+'>';sys.modules[value.__name__]=value\n"
        " exec(compile(raw,value.__file__,'exec'),value.__dict__);loaded[name]=value\n"
        + 'core=loaded[' + repr(CORE) + '];entry=loaded[' + repr(ENTRY) + ']\n'
        + "os.nice(10)\naffinity=sorted(os.sched_getaffinity(0))\nif len(affinity)>2:os.sched_setaffinity(0,set(affinity[:2]))\n"
        + 'API_PATHS=' + repr(tuple(sorted(API_PATHS))) + '\nLIBRARY_PATHS=' + repr(LIBRARY_PATHS)
        + '\nPRIVATE_HISTORY=' + repr(tuple(sorted(PRIVATE_HISTORY))) + '\nMODEL_PATHS=' + repr(tuple(sorted(MODEL_PATHS))) + '\n'
        + PROJECTORS + '\n'
        + "core.__dict__.update(_page_category=category,_page_request_gate=request_gate,_page_stop=entry.stop_present,_page_budget=entry.resource_budget,"
        + '_page_resource_types=' + repr(RESOURCE_TYPES) + ',_page_poll_seconds=' + str(POLL_SECONDS)
        + ',_page_libraries_js=' + repr(LIBRARIES_JS) + ',_page_chat_sha=' + repr(PUBLIC_CHAT_SOURCE_SHA) + ')\n'
        + 'exec(compile(' + repr(browser_source(blobs[CORE])) + ",'<readonly-browser>','exec'),core.__dict__)\n"
        + 'report=' + repr({'schema':SCHEMA,'state':'RUNNING','application_posts_sent':0,'generation_requests_sent':0,
            'dialogs_created':0,'production_changes':False,'private_content_exported':False,
            'rendering_mode':'CPU_SWIFTSHADER_NOT_USER_GPU_BENCHMARK','markdown_end_to_end_verified':False,
            'library_versions_missing_are_unknown':True,'history_requests_blocked':True}) + '\n'
        "report.update(request=os.environ['NOX_OWNER_REQUEST_ID'],source_sha=os.environ['NOX_OWNER_SOURCE_SHA'],started_at=time.time())\n"
        "try:\n"
        " asyncio.run(asyncio.wait_for(core.browser_run(report,None,core.inventory()),timeout=75))\n"
        " report['state']='DIAGNOSTIC_OBSERVED'\n"
        "except BaseException as exc:\n"
        " report.update(state='HOLD',reason='HOLD_PAGE_DIAGNOSTIC_TIMEOUT' if isinstance(exc,TimeoutError) else core.safe_error(exc))\n"
        "report['finished_at']=time.time()\n"
        + 'core.emit(' + repr(KIND) + ',report)\n'
        "raise SystemExit(0 if report['state']=='DIAGNOSTIC_OBSERVED' else 2)\n").encode()


def proxy_pin():
    import stat
    fd = os.open(PROXY, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        a = os.fstat(fd)
        require(stat.S_ISREG(a.st_mode) and a.st_uid == os.geteuid() and not a.st_mode & 0o022
                and 0 < a.st_size <= 262144, 'PROXY_METADATA')
        raw = os.read(fd, 262145); b = os.fstat(fd); named = PROXY.stat(follow_symlinks=False)
        identity = lambda s: (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns,s.st_mode)
        require(identity(a) == identity(b) == identity(named) and len(raw) == a.st_size
                and hashlib.sha256(raw).hexdigest() == PROXY_SHA, 'PROXY_PIN')
    finally:
        os.close(fd)


def child_identity(pid):
    with open('/proc/' + str(pid) + '/stat', 'rb') as stream:
        raw = stream.read(8193)
    require(len(raw) <= 8192, 'CHILD_IDENTITY_BOUND')
    fields = raw[raw.rfind(b')') + 2:].split()
    return tuple(int(fields[index]) for index in (1, 2, 3, 19))


def stop_owned_child(proc, identity):
    # Do not poll/wait/reap after TERM until the final group KILL. An exited
    # unreaped leader pins the PGID while a Chromium descendant ignores TERM.
    require(identity is not None and identity[:3] == (os.getpid(), proc.pid, proc.pid)
            and child_identity(proc.pid) == identity, 'CHILD_OWNERSHIP')
    os.killpg(proc.pid, signal.SIGTERM)
    time.sleep(2)
    require(child_identity(proc.pid) == identity, 'CHILD_IDENTITY_CHANGED')
    try: os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError: pass
    proc.communicate(timeout=3)


def main():
    blobs = sources(); entry = module(ENTRY, blobs[ENTRY]); request, source = entry.owner_context()
    python = entry.existing_runtime(); entry.resource_budget(); proxy_pin()
    program = child_program(blobs); compile(program,'<page-diagnostic-child>','exec')
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        proc = subprocess.Popen([str(python),'-I','-B','-'],stdin=subprocess.PIPE,stdout=output,stderr=errors,
            env=entry.child_environment(request,source),start_new_session=True)
        identity = child_identity(proc.pid)
        try:
            proc.communicate(program,timeout=80)
        except subprocess.TimeoutExpired:
            stop_owned_child(proc,identity)
            raise RuntimeError('HOLD_PAGE_DIAGNOSTIC_CHILD_TIMEOUT') from None
        require(output.tell() <= 131072 and errors.tell() <= 1048576,'OUTPUT_BOUND')
        output.seek(0); lines=output.read(131073).decode('utf-8','replace').splitlines()
    rows=[json.loads(line[len(PREFIX):]) for line in lines if line.startswith(PREFIX)]
    require(len(rows)==1 and rows[0].get('kind')==KIND,'RESULT')
    value=rows[0].get('data');require(isinstance(value,dict) and value.get('schema')==SCHEMA
        and value.get('request')==request and value.get('source_sha')==source
        and value.get('application_posts_sent')==value.get('generation_requests_sent')==value.get('dialogs_created')==0
        and value.get('production_changes') is False and value.get('private_content_exported') is False,'SCOPE')
    proxy_pin();require(not entry.stop_present(),'OWNER_STOP')
    require((proc.returncode==0)==(value.get('state')=='DIAGNOSTIC_OBSERVED'),'RESULT_STATE')
    value['source_pins']=PINS
    print(PREFIX+json.dumps({'kind':KIND,'data':value},separators=(',',':'),allow_nan=False),flush=True)
    if proc.returncode==0:print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
    return 0 if proc.returncode==0 else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(PREFIX+json.dumps({'kind':KIND,'data':{'schema':SCHEMA,'state':'HOLD','reason':safe(exc),
            'private_content_exported':False}},separators=(',',':')),flush=True)
        raise SystemExit(2)
