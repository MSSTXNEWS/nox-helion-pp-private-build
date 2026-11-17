import contextlib, hashlib, importlib.util, io, json, os, pathlib, sys, types, unittest, urllib.error
from unittest.mock import MagicMock, patch
HERE=pathlib.Path(__file__).parent
def load(name):
    spec=importlib.util.spec_from_file_location(name,HERE/(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
c=load('owner_cloudcopy_capability');o=load('owner_native_operator')
class Tests(unittest.TestCase):
    def response(self,data):
        r=MagicMock();r.__enter__.return_value.read.return_value=json.dumps(data).encode();return r
    def test_canonical_and_auth_only_expected_origin(self):
        opener=MagicMock();opener.open.return_value=self.response([])
        with patch.object(c.urllib.request,'build_opener',return_value=opener):self.assertEqual(c.probe('secret')['connections_count'],0)
        req=opener.open.call_args.args[0];self.assertTrue(req.full_url.endswith('/'));self.assertEqual(req.method,'GET');self.assertIsNone(req.data)
        for u in ['http://console.vast.ai/api/v0/users/cloud_integrations/','https://evil.invalid/x','https://console.vast.ai.evil.invalid/api/v0/users/cloud_integrations/','https://console.vast.ai/api/v0/users/cloud_integrations/?token=x','https://user@console.vast.ai/api/v0/users/cloud_integrations/']:
            self.assertFalse(c.allowed(u))
    def test_scoped_redirect_once(self):
        opener=MagicMock();opener.open.side_effect=[urllib.error.HTTPError(c.URL,301,'Moved',{'Location':'/api/v0/users/cloud_integrations'},None),self.response([{'id':9,'cloud_type':'drive','name':'PRIVATE'}])]
        with patch.object(c.urllib.request,'build_opener',return_value=opener):r=c.probe('secret')
        self.assertEqual(r['connections_count'],1);self.assertEqual(opener.open.call_count,2);self.assertNotIn('PRIVATE',json.dumps(r));self.assertNotIn('secret',json.dumps(r))
    def test_cross_origin_no_second_request(self):
        opener=MagicMock();opener.open.side_effect=urllib.error.HTTPError(c.URL,301,'Moved',{'Location':'https://evil.invalid/steal'},None)
        with patch.object(c.urllib.request,'build_opener',return_value=opener):r=c.probe('secret')
        self.assertEqual(r['state'],'HOLD_CLOUDCOPY_REDIRECT_SCOPE');self.assertEqual(opener.open.call_count,1)
    def test_provider_only_main_no_ssh_and_no_key_cleanup(self):
        backend=MagicMock();backend.api.return_value={'instances':[{'id':60509551,'actual_status':'running','num_gpus':2}]}
        backend.cleanup.side_effect=AssertionError('no SSH cleanup')
        modules={x:types.ModuleType(x) for x in ['nox_runpod','nox_runpod.teacher_mesh','nox_runpod.teacher_mesh.v51']}
        modules['nox_runpod.teacher_mesh.v51'].ephemeral_ssh_probe=backend
        modules['owner_cloudcopy_capability']=types.SimpleNamespace(probe=lambda key:{'state':'NO_EXISTING_CLOUDCOPY_CONNECTIONS','connections_count':0})
        o.PROVIDER_ONLY=False;o.MASTER=None;output=io.StringIO()
        with patch.dict(sys.modules,modules),patch.dict(os.environ,{'NOX2':'secret'}),patch.object(sys,'argv',['operator','deploy']),patch.object(o,'authorize_event',return_value=7),patch.object(o.subprocess,'run',side_effect=AssertionError('no SSH')),contextlib.redirect_stdout(output):
            self.assertEqual(o.main(),0)
        backend.api.assert_called_once_with('GET','/instances/','secret');backend.cleanup.assert_not_called()
        self.assertIn('NOX_MAINT_TRANSPORT=PROVIDER_ONLY_NO_SSH',output.getvalue());self.assertNotIn('secret',output.getvalue())
    def test_auth_failure_never_queries_provider(self):
        with patch.object(o,'authorize_event',side_effect=RuntimeError('HOLD_OWNER_COMMAND_IDENTITY')),patch.object(o,'run_native',side_effect=AssertionError('no provider')):
            o.PROVIDER_ONLY=True
            with patch.object(sys,'argv',['operator','deploy']),contextlib.redirect_stdout(io.StringIO()):self.assertEqual(o.main(),2)
    def test_auth_function_and_host_pin_unchanged(self):
        after=(HERE/'owner_native_operator.py').read_text()
        block=after.split('def authorize_event(action):')[1].split('def run_native')[0]
        self.assertEqual(hashlib.sha256(block.encode()).hexdigest(), 'cafd7703e54bdeef5cef5dfe4a6bbdd07832ce124b110cba5e0c0b0f2d8fc2d7')
        self.assertIn("PIN='SHA256:G4hmMllaT4uSfx+Gup9vjSySLXJT1cSc/9XePr7XmGc'",after)
if __name__=='__main__':unittest.main(verbosity=2)
