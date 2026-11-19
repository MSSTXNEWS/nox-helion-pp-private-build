"""Safety tests for the native V125 installer; no remote connection."""
import ast
import pathlib
import unittest
from nox_runpod.teacher_mesh.v125 import install_owner_readonly as installer

class NativeSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script=installer.REMOTE_TEMPLATE.split("<<'PYREMOTE'\n",1)[1].rsplit('\nPYREMOTE',1)[0]
        cls.tree=ast.parse(cls.script)
    def test_embedded_owner_acceptance_compiles(self):
        compile(self.script,'<v125-native-script>','exec')
    def test_exact_live_preimage_and_stale_sha_fail_closed(self):
        self.assertEqual('d0590c2a582bd4ad0df5ff26a036284cf1426e31ca41b283cf1695c7726f7cd5',installer.BRIDGE_SHA)
        self.assertEqual('4d90215d7099344dd5aaed2412645b764baa0228acc0b0e153cfe425217591ad',installer.PROXY_SHA)
        for text in ('HOLD_NATIVE_SOURCE_SHA_DRIFT','HOLD_CONCURRENT_SOURCE_OR_CHAT',
                     'HOLD_BACKUP_VERIFY','HOLD_BUSY_OR_S03_HEALTH',
                     'HOLD_POST_RESTART_HEALTH','HOLD_POST_ROUTE_ACCEPTANCE',
                     'HOLD_ROLLED_BACK','HOLD_ROLLBACK_UNVERIFIED'):
            self.assertIn(text,self.script)
    def test_cookiejar_alias_not_function_shadowed(self):
        imports=[n for n in self.tree.body if isinstance(n,ast.Import)]
        self.assertTrue(any(any(i.name=='http.cookiejar' and i.asname=='cookiejar'
                                for i in node.names) for node in imports))
        self.assertIn('jar=cookiejar.CookieJar()',self.script)
        self.assertNotIn('jar=http.cookiejar.CookieJar()',self.script)
        self.assertTrue(any(isinstance(n,ast.FunctionDef) and n.name=='http'
                            for n in self.tree.body))
    def test_only_existing_proxy_restart_and_no_s03_writes(self):
        for banned in ('rm -rf','shutil.rmtree','torch.save(','optimizer.step(',
                       'supervisorctl stop','pip install','mode=rw','DROP TABLE',
                       'DELETE FROM s03_items'):
            self.assertNotIn(banned,self.script)
        self.assertIn("['supervisorctl','restart','nox-proxy']",self.script)
        self.assertIn('original_s03_quick_check',self.script)
        self.assertIn('anonymous_http401',self.script)
        self.assertIn('model_weights_unchanged',self.script)
    def test_install_does_not_create_second_backend(self):
        self.assertIn("SNIPPET=(\"    from nox_v125_live_readonly import register_nox_v125_live_readonly",self.script)
        self.assertIn('register_nox_v125_live_readonly(app,trusted)',self.script)
        self.assertIn("if stopped():raise RuntimeError('HOLD_STOP')",self.script)
        self.assertIn("if count!=5 or stopped():raise RuntimeError('HOLD_POST_ROUTE_ACCEPTANCE')",self.script)


    def test_owner_cookie_auth_middleware_exact_path_allowlist(self):
        source=self.script
        self.assertIn("PROXY_OLD_GUARD=",source)
        self.assertIn("PROXY_NEW_GUARD=",source)
        self.assertIn("pxsource.count(PROXY_OLD_GUARD)!=1",source)
        self.assertIn("compile(pxchanged,str(PX),'exec')",source)
        self.assertIn("new_proxy_sha256=file_sha(PX)",source)
        self.assertIn("'/api/nox/system/processes'",source)
        self.assertIn("'/api/nox/premium/capabilities'",source)
        self.assertIn("_session_ok(request):",source)
        self.assertIn("atomic(PX,pxchanged,pxmeta,'.nox-v125-proxy.tmp')",source)
        self.assertIn("atomic(PX,pxbefore,pxmeta,'.nox-v125-proxy-rollback.tmp')",source)
        self.assertIn("file_sha(PX)==PX_EXPECTED",source)

if __name__=='__main__':
    unittest.main()
