"""Offline boundary checks; audit() pipeline is exercised only with fake I/O."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import time
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('reviewed_ui_audit',HERE/'owner_native_audit.py')
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)


class FakeResponse:
    def __init__(self,body=b'const x = 1;',status=200,mime='application/javascript'):
        self.body=body;self.status=status;self.headers={'Content-Type':mime}
    def read(self,n):return self.body[:n]
    def __enter__(self):return self
    def __exit__(self,*args):pass


class AuditScopeTests(unittest.TestCase):
    def test_observed_script_paths_have_one_origin_no_traversal(self):
        for raw in ('nox-chat.js','./nox-chat.js','/nox-web-v29/nox-chat.js','http://127.0.0.1:18775/nox-web-v29/nox-chat.js'):
            self.assertEqual(a.canonical_script_path(raw),'/nox-web-v29/nox-chat.js')
        self.assertEqual(a.canonical_script_path('assets/chat.js?v=13'),'/nox-web-v29/assets/chat.js?v=13')
        for raw in ('https://evil.invalid/a.js','//evil.invalid/a.js','/api/nox/chat/stream',
                    '../a.js','%2e%2e/a.js','a.js?token=private','a.js#secret','a.js\n',
                    'http://user@127.0.0.1:18775/a.js','http://[bad/a.js'):
            with self.subTest(raw=raw):self.assertIsNone(a.canonical_script_path(raw))

    def test_model_and_mutating_routes_never_reach_opener(self):
        client=a.AuditHTTP(time.monotonic()+30)
        with patch.object(client.opener,'open',side_effect=AssertionError('unexpected I/O')):
            for path in ('/api/nox/chat/stream','/api/nox/stop','/api/ui/memory/dialogs/create',
                         '/v1/chat/completions','/slots','/api/nox/status','/nox/home'):
                with self.subTest(path=path),self.assertRaises(a.Hold):client.read(path)
            client.allowed_scripts.add('/api/nox/chat/stream')
            with self.assertRaises(a.Hold):client.read('/api/nox/chat/stream')
        self.assertEqual(client.requests,0)

    def test_only_observed_script_and_status_can_be_read(self):
        client=a.AuditHTTP(time.monotonic()+30);client.allowed_scripts.add('/nox-web-v29/nox-chat.js')
        observed=[]
        def opener(req,timeout):
            observed.append((req.full_url,req.get_method(),req.data))
            return FakeResponse()
        with patch.object(client.opener,'open',side_effect=opener):
            client.read('/nox-web-v29/nox-chat.js')
            client.status_observed=True;client.read('/api/nox/status')
            client.read(a.CHAT_ALIAS)
        self.assertEqual(observed,[('http://127.0.0.1:18775/nox-web-v29/nox-chat.js','GET',None),
                                   ('http://127.0.0.1:18775/api/nox/status','GET',None),
                                   ('http://127.0.0.1:18775/nox/chat','GET',None)])

    def test_real_v13_relative_script_forms_and_owner_flag_order(self):
        scripts='<script defer src="./nox-ui.js"></script><script defer src="./nox-shared-chrome-v10.js"></script><script defer src="./nox-chat.js"></script>'
        flag='<script>window.NOX_NATIVE_OWNER=true;</script>'
        parser=a.PageProjection();parser.feed(flag+scripts);out=parser.summary()
        self.assertEqual(parser.scripts,['/nox-web-v29/nox-ui.js','/nox-web-v29/nox-shared-chrome-v10.js','/nox-web-v29/nox-chat.js'])
        self.assertTrue(out['owner_flag_before_critical_scripts']);self.assertFalse(out['owner_flag_activation_verified'])
        late=a.PageProjection();late.feed(scripts+flag)
        self.assertFalse(late.summary()['owner_flag_before_critical_scripts'])
        inert=a.PageProjection();inert.feed(flag.replace('<script>','<script type="application/json">')+scripts)
        self.assertFalse(inert.summary()['owner_flag_before_critical_scripts'])
        for raw in ('../nox-ui.js','//evil.invalid/nox-ui.js','assets/./nox-ui.js'):
            self.assertIsNone(a.canonical_script_path(raw))

    def test_late_failure_preserves_safe_partial_html_and_completed_script(self):
        page=b'<title>NOX HELION</title><script>window.NOX_NATIVE_OWNER=true;</script><script src="./workspace.js"></script><script src="./nox-chat.js"></script>'
        clients=[]
        class FakeClient:
            def __init__(self,deadline):
                self.jar=['synthetic-cookie'];self.requests=0;self.total=0;self.allowed_scripts=set();self.status_observed=False
                clients.append(self)
            def read(self,path,**kwargs):
                self.requests+=1
                if path.endswith('nox-chat.js'):raise TimeoutError('PRIVATE_SESSION_TEXT')
                raw=page if path==a.PAGE else b'const x = 1;'
                self.total+=len(raw)
                return raw,{'path':path,'status':200,'sha256':a.digest(raw),
                            'content_type':'text/html' if path==a.PAGE else 'application/javascript'}
        pins={a.PROXY:a.PROXY_SHA,a.BRIDGE:a.BRIDGE_SHA,a.WRAPPER:a.WRAPPER_SHA}
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.dict(a.os.environ,{'NOX_OWNER_REQUEST_ID':'123','NOX_OWNER_SOURCE_SHA':'a'*40}))
            for name,value in (
                ('AuditHTTP',FakeClient),('maintenance_lease',lambda _:contextlib.nullcontext()),
                ('stable_common_read',lambda path:(b'pass',{'sha256':pins[path]})),
                ('exact_common_import',lambda tree:False),('resolve_password_path',lambda *args,**kw:Path('/synthetic/password')),
                ('private_password',lambda path:'SYNTHETIC_ONLY'),('scoped_stop_supported',lambda source:True)):
                stack.enter_context(patch.object(a,name,value))
            report=a.audit(expected_source_sha='a'*40)
        self.assertEqual(report['status'],'HOLD_BOUNDED_AUDIT_FAILURE');self.assertTrue(report['partial'])
        self.assertEqual(report['html']['sha256'],a.digest(page));self.assertTrue(report['owner_flag_before_critical_scripts'])
        self.assertEqual(len(report['scripts']),1);self.assertEqual(report['model_requests'],0)
        self.assertNotIn('PRIVATE_SESSION_TEXT',json.dumps(report));self.assertEqual(clients[0].jar,[])
        sink=io.StringIO()
        with patch.object(a,'audit',return_value=report),contextlib.redirect_stdout(sink):
            self.assertEqual(a.main(),2)
        self.assertIn('NOX_MAINT_AUDIT_COMPLETE=false',sink.getvalue())

    def test_projection_drops_text_values_and_inline_state(self):
        page='<title>NOX HELION</title><script src="nox-chat.js"></script><script>window.NOX_NATIVE_OWNER=true; const user="PRIVATE_SESSION_TEXT";</script><textarea id="message">PRIVATE_SESSION_TEXT</textarea><input id="draft" value="PRIVATE_SESSION_TEXT">'
        parser=a.PageProjection();parser.feed(page);out=parser.summary();rendered=json.dumps(out)
        self.assertTrue(out['owner_flag_true_defined']);self.assertNotIn('PRIVATE_SESSION_TEXT',rendered)
        self.assertEqual(out['script_paths'],['/nox-web-v29/nox-chat.js']);self.assertFalse(out['source_text_exported'])

    def test_wiring_ignores_commented_or_stringified_owner_assignment(self):
        false=a.wiring('// window.NOX_NATIVE_OWNER=true;\n const x="window.NOX_NATIVE_OWNER=true";')
        self.assertFalse(false['owner_flag_true_defined'])
        live=a.wiring('window.NOX_NATIVE_OWNER=true; function sendNative(){return fetch("/api/nox/chat/stream");} const s="/api/nox/status";')
        self.assertTrue(live['owner_flag_true_defined']);self.assertTrue(live['sendNative_definition_present'])
        self.assertIn('/api/nox/status',live['literal_routes'])

    def test_status_projection_only_expected_bounded_fields(self):
        out=a.safe_status({'native_p02_bound':True,'backend':'EXISTING_NATIVE_ONEHOST',
                           'primary_model':'NOX-8B','password':'PRIVATE_SESSION_TEXT','sessions':['private']})
        self.assertEqual(set(out),{'schema_valid','native_p02_bound','backend','primary_model'})
        self.assertNotIn('PRIVATE_SESSION_TEXT',json.dumps(out))
        self.assertEqual(a.safe_status({'primary_model':'/root/private/model.gguf'})['primary_model'],'[WITHHELD_OR_UNAVAILABLE]')

    def test_redirect_is_not_followed_and_oversize_source_is_not_parsed(self):
        self.assertIsNone(a.AuditNoRedirect().redirect_request(None,None,302,'',{},'https://evil.invalid/'))
        client=a.AuditHTTP(time.monotonic()+30)
        with patch.object(client.opener,'open',return_value=FakeResponse(b'x'*(a.FILE_LIMIT+1),mime='text/html')):
            body,meta=client.read(a.PAGE)
        self.assertIsNone(body);self.assertTrue(meta['truncated']);self.assertEqual(meta['sha256_scope'],'bounded_prefix')

    def test_raw_exception_never_enters_operator_output(self):
        sink=io.StringIO()
        with patch.object(a,'audit',side_effect=RuntimeError('PRIVATE_SESSION_TEXT')),contextlib.redirect_stdout(sink):
            status=a.main()
        self.assertEqual(status,2);self.assertNotIn('PRIVATE_SESSION_TEXT',sink.getvalue())
        self.assertIn('NOX_MAINT_AUDIT_COMPLETE=false',sink.getvalue())


if __name__=='__main__':unittest.main()
