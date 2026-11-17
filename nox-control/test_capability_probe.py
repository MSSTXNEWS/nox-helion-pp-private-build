import ast, importlib.util, json, os, pathlib, tempfile, time, unittest
from unittest.mock import patch, MagicMock

HERE=pathlib.Path(__file__).parent
def load(name):
    spec=importlib.util.spec_from_file_location(name,HERE/(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
p=load('owner_native_deploy');c=load('owner_cloudcopy_capability')

class CapabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name)
        p.DEADLINE=None
    def tearDown(self):self.tmp.cleanup()
    def private(self,name,text):
        path=self.root/name;path.write_text(text);path.chmod(0o600);return path
    def test_missing_profile_no_mutation_or_command(self):
        before=list(self.root.iterdir())
        with patch.object(p,'execute',side_effect=AssertionError('no command')):
            row=p.probe_profile('test',self.root/'missing',{},None)
        self.assertFalse(row['present']);self.assertEqual(before,list(self.root.iterdir()))
    def test_private_mode_and_symlink_fail_closed(self):
        path=self.private('profile','[nox_drive]\ntype=drive\ntoken=PRIVATE_TOKEN\n')
        path.chmod(0o644)
        with patch.object(p,'execute',side_effect=AssertionError('no command')):
            self.assertEqual(p.probe_profile('test',path,{},None)['state'],'HOLD_PROFILE_PROBE')
            alias=self.root/'link';alias.symlink_to(path)
            self.assertEqual(p.probe_profile('test',alias,{},None)['state'],'HOLD_PROFILE_PROBE')
    def test_oauth_profile_runs_from_memfd_and_does_not_leak(self):
        path=self.private('profile','[nox_drive]\ntype=drive\ntoken=PRIVATE_TOKEN\n')
        before=path.read_bytes();stamp=path.stat().st_mtime_ns
        def command(args,seconds,pass_fds):
            self.assertIn('/proc/self/fd/'+str(pass_fds[0]),args)
            self.assertNotIn(str(path),args)
            self.assertEqual(args[-4:],['nox_drive:NOX_PRIVATE_BACKUPS','--max-depth','1','--dirs-only'])
            self.assertIn(b'PRIVATE_TOKEN',os.pread(pass_fds[0],500,0))
            return 0,b''
        with patch.object(p,'binary',return_value='/usr/bin/rclone'),patch.object(p,'execute',side_effect=command):
            row=p.probe_profile('current_NOX_RCLONE_CONFIG',path,{},None)
        self.assertTrue(row['drive_authenticated_read']);self.assertTrue(row['source_unchanged'])
        self.assertEqual(before,path.read_bytes());self.assertEqual(stamp,path.stat().st_mtime_ns)
        self.assertNotIn('PRIVATE_TOKEN',json.dumps(row));self.assertNotIn(str(path),json.dumps(row))
    def test_pc_freshness_identity_without_personal_export(self):
        data={'schema':'NOX_PC_LINK_V1','instance_id':60509551,'reverse_host':'127.0.0.1','reverse_port':46051,'connected':True,'last_verified_utc':'2026-11-17T00:00:00+00:00','backup_root':'D:\\Personal_Name\\NOX','pc_user':'PRIVATE_USER'}
        path=self.private('connection',json.dumps(data));now=1794873630
        import datetime
        now=datetime.datetime.fromisoformat(data['last_verified_utc']).timestamp()+30
        with patch.object(p.socket,'create_connection',return_value=MagicMock()):
            row,target=p.pc_metadata(path,now)
        self.assertTrue(row['fresh']);self.assertTrue(row['loopback_open']);self.assertEqual(target,'nox_pc:/D:/Personal_Name/NOX')
        self.assertNotIn('PRIVATE_USER',json.dumps(row));self.assertNotIn('Personal_Name',json.dumps(row))
        with patch.object(p.socket,'create_connection',return_value=MagicMock()):
            row,_=p.pc_metadata(path,now+200)
        self.assertFalse(row['fresh']);self.assertTrue(row['loopback_open'])
        data['instance_id']=1;path.write_text(json.dumps(data))
        with patch.object(p.socket,'create_connection',side_effect=AssertionError('wrong instance')):
            row,target=p.pc_metadata(path,now)
        self.assertFalse(row['identity_valid']);self.assertIsNone(target)
    def test_cloud_metadata_redacts_names_ids_unknown_types(self):
        row=c.summarize([{'id':42,'cloud_type':'drive','name':'PRIVATE_NAME','token':'SECRET'}, {'id':43,'cloud_type':'SECRET_PROVIDER'}])
        self.assertEqual(row['connections_count'],2);self.assertEqual(row['provider_counts'],{'drive':1,'other':1})
        text=json.dumps(row);self.assertNotIn('SECRET',text);self.assertNotIn('PRIVATE_NAME',text);self.assertNotIn('42',text)
        self.assertFalse(row['destination_access_verified'])
    def test_cloud_bad_schema_never_means_no_connections(self):
        self.assertEqual(c.summarize({'error':'secret'})['state'],'HOLD_CLOUDCOPY_RESPONSE_SCHEMA')
        self.assertEqual(c.summarize([])['state'],'NO_EXISTING_CLOUDCOPY_CONNECTIONS')
    def test_provider_query_fixed_get_and_no_redirect(self):
        response=MagicMock();response.__enter__.return_value.read.return_value=b'[]'
        opener=MagicMock();opener.open.return_value=response
        with patch.object(c.urllib.request,'build_opener',return_value=opener):
            result=c.probe('SECRET_KEY')
        request=opener.open.call_args.args[0]
        self.assertEqual(request.full_url,c.URL);self.assertEqual(request.method,'GET');self.assertIsNone(request.data)
        self.assertNotIn('SECRET_KEY',json.dumps(result));self.assertIsNone(c.NoRedirect().redirect_request(None,None,None,None,None,None))
    def test_bounded_pipe_and_timeout(self):
        import sys
        rc,out=p.execute([sys.executable,'-c','import sys;print("ok");sys.stderr.write("PRIVATE")'],2,collect=True)
        self.assertEqual((rc,out),(0,b'ok\n'))
        with self.assertRaises(p.Hold):p.execute([sys.executable,'-c','import time;time.sleep(3)'],.1)
        with self.assertRaises(p.Hold):p.execute([sys.executable,'-c','print("x"*200000)'],2,collect=True)
    def test_missing_stop_flags_fails_before_probe(self):
        with patch.object(p,'FLAGS',(self.root/'missing',)*4),self.assertRaises(p.Hold):p.flags()
    def test_no_write_apis_or_shell(self):
        tree=ast.parse((HERE/'owner_native_deploy.py').read_text())
        forbidden={'mkdir','unlink','write_text','write_bytes','remove','rename','copy','copyfile','rmtree'}
        for node in ast.walk(tree):
            if isinstance(node,ast.Call):
                if isinstance(node.func,ast.Attribute):self.assertNotIn(node.func.attr,forbidden)
                self.assertFalse(any(k.arg=='shell' and isinstance(k.value,ast.Constant) and k.value.value for k in node.keywords))
        self.assertNotIn('os.O_CREAT',(HERE/'owner_native_deploy.py').read_text())

if __name__=='__main__':unittest.main(verbosity=2)
