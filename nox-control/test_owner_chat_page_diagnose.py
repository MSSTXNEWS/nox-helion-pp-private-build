import ast
import asyncio
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parent
SPEC = importlib.util.spec_from_file_location('page_diag_tested', ROOT / 'owner_chat_page_diagnose.py')
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)
BLOBS = {name: (ROOT / name).read_bytes() for name in m.PINS}


class AsyncObject:
    def __init__(self, value): self.value = value
    async def __aenter__(self): return self.value
    async def __aexit__(self, *args): pass


class Requests:
    def __init__(self, anonymous=401): self.posts = []; self.gets = []; self.anonymous = anonymous
    async def get(self, url, **kwargs):
        self.gets.append(url)
        return types.SimpleNamespace(status=self.anonymous if url.endswith('/api/ui/executors') else 200)
    async def post(self, url, **kwargs):
        self.posts.append(url)
        return types.SimpleNamespace(status=200)


class Page:
    def __init__(self, context):
        self.context = context; self.listeners = {}; self.url = 'http://192.0.2.2:8080/nox-web-v29/pc/resonance.html'
    def on(self, name, callback): self.listeners[name] = callback
    async def goto(self, url, **kwargs):
        aborted = []
        async def abort(): aborted.append(True)
        async def continued(): raise AssertionError('A model POST must never pass')
        await self.context.guard(types.SimpleNamespace(
            request=types.SimpleNamespace(method='POST',url='http://192.0.2.2:8080/api/nox/chat'),
            abort=abort,continue_=continued))
        assert aborted == [True]
        for path in ['/api/nox/mood?secret=not-exported','/api/private/'+'c'*32]:
            self.listeners['response'](types.SimpleNamespace(url='http://192.0.2.2:8080'+path,status=401,
                request=types.SimpleNamespace(method='GET',resource_type='fetch')))
        self.listeners['console'](types.SimpleNamespace(type='error',text='private text never read'))
        return types.SimpleNamespace(status=200)
    async def wait_for_function(self, *args, **kwargs): return True
    async def evaluate(self, value):
        assert value == m.LIBRARIES_JS
        return {'marked':{'present':False,'version':None},'fixture':{'passed':False}}


class Context:
    def __init__(self, anonymous=401): self.request=Requests(anonymous);self.closed=False
    def set_default_timeout(self, value): pass
    async def route(self, pattern, callback): self.guard=callback
    async def new_page(self): return Page(self)
    async def close(self): self.closed=True


class Browser:
    version='143.0.0.0'
    def __init__(self, context):self.context=context;self.closed=False
    async def new_context(self, **kwargs):
        assert kwargs['service_workers']=='block' and kwargs['accept_downloads'] is False
        return self.context
    async def close(self):self.closed=True


def composed_run(anonymous=401):
    core=m.module(m.CORE,BLOBS[m.CORE]);context=Context(anonymous);browser=Browser(context)
    async def launch(**kwargs):
        assert kwargs['env']['CUDA_VISIBLE_DEVICES']=='' and '--use-angle=swiftshader' in kwargs['args']
        return browser
    runtime=types.SimpleNamespace(chromium=types.SimpleNamespace(launch=launch))
    api=types.ModuleType('playwright.async_api');api.async_playwright=lambda:AsyncObject(runtime);api.TimeoutError=TimeoutError
    core.local_base=lambda:'http://192.0.2.2:8080'
    core.__dict__.update(_page_category=m.category,_page_request_gate=m.request_gate,_page_stop=lambda:False,
        _page_budget=lambda:{'read_only':True},_page_resource_types=m.RESOURCE_TYPES,
        _page_poll_seconds=0,_page_libraries_js=m.LIBRARIES_JS,_page_chat_sha=m.PUBLIC_CHAT_SOURCE_SHA)
    exec(compile(m.browser_source(BLOBS[m.CORE]),'<test-browser>','exec'),core.__dict__)
    report={}
    proxy=types.ModuleType('chat_proxy');proxy._read_chat_password=lambda:'synthetic-password'
    with patch.dict(sys.modules,{'playwright':types.ModuleType('playwright'),'playwright.async_api':api,'chat_proxy':proxy}):
        try:asyncio.run(core.browser_run(report,None,{'system_browser_candidates':[]}))
        finally:sys.path=[item for item in sys.path if item!='/root/nox/scripts']
    return report,context,browser


class DiagnosticTests(unittest.TestCase):
    def test_routes_never_export_query_or_unknown_path(self):
        origin='192.0.2.2:8080'
        self.assertEqual(m.category('http://'+origin+'/api/nox/mood?token=SECRET#private',origin),'/api/nox/mood')
        self.assertEqual(m.category('http://'+origin+'/api/nox/mood/SECRET',origin),'OTHER_API')
        self.assertEqual(m.category('https://foreign.invalid/api/nox/mood?token=SECRET',origin),'OTHER_ORIGIN')
        self.assertNotIn('SECRET',m.category('http://'+origin+'/private/SECRET',origin))

    def test_all_application_mutations_models_and_private_history_blocked(self):
        origin='192.0.2.2:8080';base='http://'+origin
        for method in ('POST','PUT','PATCH','DELETE','CONNECT','OPTIONS'):
            self.assertEqual(m.request_gate(method,base+'/api/nox/status',origin),'APPLICATION_MUTATION')
        for path in m.MODEL_PATHS:self.assertEqual(m.request_gate('GET',base+path,origin),'MODEL_ENDPOINT')
        for path in m.PRIVATE_HISTORY:self.assertEqual(m.request_gate('GET',base+path+'?dialog_id=PRIVATE',origin),'PRIVATE_HISTORY')
        self.assertIsNone(m.request_gate('GET',base+'/api/nox/mood?limit=12',origin))

    def test_exact_frozen_dependencies_and_pin_rejection(self):
        for name,pin in m.PINS.items():self.assertEqual(hashlib.sha256(BLOBS[name]).hexdigest(),pin)
        with patch.object(m,'BUNDLE',{k:base64.b64encode(v).decode() for k,v in BLOBS.items()}):
            self.assertEqual(m.sources(),BLOBS)
        with self.assertRaisesRegex(RuntimeError,'CORE_PIN'):m.browser_source(BLOBS[m.CORE]+b'\n')

    def test_only_two_auth_posts_and_no_core_main(self):
        text=m.browser_source(BLOBS[m.CORE]);tree=ast.parse(text)
        posts=[node for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='post']
        self.assertEqual(len(posts),2)
        paths=[node.args[0].right.value for node in posts]
        self.assertEqual(paths,['/chat/login','/chat/logout'])
        self.assertNotIn('dialogs/create',text);self.assertNotIn('capture_private_screenshot',text)
        child=m.child_program(BLOBS);ast.parse(child)
        self.assertNotIn('core.main(',child.decode());self.assertNotIn('entry.main(',child.decode())

    def test_operator_exec_without_source_file_compiles_same_child(self):
        value=types.ModuleType('operator_exec');value.__file__='<native-entry>'
        exec(compile((ROOT/'owner_chat_page_diagnose.py').read_bytes(),value.__file__,'exec'),value.__dict__)
        self.assertEqual(value.child_program(BLOBS),m.child_program(BLOBS))

    def test_composed_browser_sends_auth_only_and_keeps_observed_401(self):
        report,context,browser=composed_run()
        self.assertEqual(context.request.posts,['http://192.0.2.2:8080/chat/login','http://192.0.2.2:8080/chat/logout'])
        self.assertTrue(context.closed and browser.closed)
        self.assertEqual(report['network'],[
            {'path_category':'/api/nox/mood','status':401,'resource_type':'fetch','count':1},
            {'path_category':'OTHER_API','status':401,'resource_type':'fetch','count':1}])
        self.assertEqual(report['blocked_request_counts'],{'APPLICATION_MUTATION':1})
        self.assertFalse(report['libraries']['fixture']['passed'])
        self.assertNotIn('not-exported',json.dumps(report))

    def test_failed_anonymous_gate_retains_original_category(self):
        with self.assertRaisesRegex(RuntimeError,'HOLD_ANONYMOUS_OWNER_SCOPE'):composed_run(200)

    def test_library_version_projection_and_js_syntax(self):
        program='global.window={marked:{version:"15.0.12"},DOMPurify:{version:"secret/path"},hljs:{versionString:"11.11.1"}};console.log(JSON.stringify(('+m.LIBRARIES_JS+')()));'
        run=subprocess.run(['node','-'],input=program,text=True,capture_output=True,timeout=5,check=True)
        value=json.loads(run.stdout)
        self.assertEqual(value['marked']['version'],'15.0.12')
        self.assertIsNone(value['dompurify']['version'])
        self.assertEqual(value['highlight']['version'],'11.11.1')
        self.assertFalse(value['fixture']['attempted'])
        self.assertFalse(value['fixture']['real_model_markdown_verified'])

    def test_timeout_cleanup_kills_ignoring_descendant_after_leader_exit(self):
        source='''import os,signal,time
p=os.fork()
if p==0:
 signal.signal(signal.SIGTERM,signal.SIG_IGN)
 print(os.getpid(),flush=True)
 while True:time.sleep(1)
while True:time.sleep(1)
'''
        proc=subprocess.Popen([sys.executable,'-u','-c',source],stdout=subprocess.PIPE,start_new_session=True,text=True)
        descendant=int(proc.stdout.readline());identity=m.child_identity(proc.pid)
        try:
            m.stop_owned_child(proc,identity)
            self.assertIsNotNone(proc.returncode)
            path=Path('/proc')/str(descendant)/'stat'
            if path.exists():
                raw=path.read_bytes();self.assertEqual(raw[raw.rfind(b')')+2:].split()[0],b'Z')
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid,9);proc.wait(timeout=3)

    def test_cleanup_refuses_foreign_identity_before_signal(self):
        proc=types.SimpleNamespace(pid=123)
        with patch.object(m,'child_identity',return_value=(os.getpid(),123,123,999)),patch.object(m.os,'killpg') as kill:
            with self.assertRaisesRegex(RuntimeError,'CHILD_OWNERSHIP'):
                m.stop_owned_child(proc,(os.getpid(),123,123,998))
            kill.assert_not_called()


if __name__=='__main__':unittest.main()
