import importlib.util,json,os,pathlib,tempfile,unittest
from unittest.mock import patch
HERE=pathlib.Path(__file__).parent
spec=importlib.util.spec_from_file_location('stop_s03',HERE/'owner_native_deploy.py');p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.temp.name);self.state=self.root/'state';self.state.mkdir()
        self.paths=(self.root/'STOP',self.state/'OWNER_MAINTENANCE.flag',self.state/'TRAIN_HOLD.flag',self.state/'TRAIN_PAUSE_REQUEST.flag')
        (self.state/'owner_maintenance.lock').write_bytes(b'')
        self.patches=[patch.object(p,'FLAGS',self.paths),patch.object(p,'STATE',self.state),patch.object(p,'binary',return_value='/usr/bin/supervisorctl'),patch.dict(os.environ,{'NOX_OWNER_SOURCE_SHA':'a'*40,'NOX_OWNER_REQUEST_ID':'7'})]
        for x in self.patches:x.start()
        p.OBSERVATION.clear();p.AST_READ_STARTED=False;p.DEADLINE=None
    def tearDown(self):
        for x in reversed(self.patches):x.stop()
        self.temp.cleanup()
    def test_running_nontrainer_stopped_once_then_ast(self):
        calls=[];stopped=False
        def command(args,*a,**kw):
            nonlocal stopped
            calls.append(args)
            if args[1]=='stop':self.assertEqual(args[2:],['nox-proxy']);stopped=True;return 0,b''
            return 3,('nox-proxy '+('STOPPED' if stopped else 'RUNNING')+' pid 123 secret_argument\nnox-train-volta-t866u FATAL error_private\njupyter RUNNING pid 2\n').encode()
        def ast_sources():self.assertTrue(stopped);return [],[]
        with patch.object(p,'execute',side_effect=command),patch.object(p,'active_training',return_value=False),patch.object(p,'sources',side_effect=ast_sources):r=p.main()
        self.assertEqual(sum(a[1]=='stop' for a in calls),1);self.assertEqual(r['source_writes'],4);self.assertTrue(r['ast_read_started'])
        self.assertNotIn('secret_argument',json.dumps(r));self.assertNotIn('error_private',json.dumps(r));self.assertNotIn('jupyter',json.dumps(r))
        self.assertTrue(r['stop_observation']['all_noX_services_quiescent']);self.assertFalse(r['stop_observation']['all_states_literal_STOPPED'])
    def test_active_trainer_no_flag_or_stop_or_ast(self):
        def command(args,*a,**kw):self.assertEqual(args[1],'status');return 0,b'nox-train-volta-t866u RUNNING pid 9\n'
        with patch.object(p,'execute',side_effect=command),patch.object(p,'active_training',return_value=True),patch.object(p,'sources',side_effect=AssertionError('no AST')),self.assertRaises(p.Hold) as error:p.main()
        self.assertIn('ACTIVE_TRAINER',str(error.exception));self.assertFalse(any(x.exists() for x in self.paths));self.assertFalse(p.AST_READ_STARTED)
        self.assertEqual(p.failure_record(error.exception)['stop_observation']['supervisor_status'][0]['state'],'RUNNING')
    def test_existing_flags_preserved_exactly(self):
        for path in self.paths:path.write_bytes(b'original-private-stop-state')
        with patch.object(p,'execute',return_value=(3,b'nox-proxy STOPPED\n')),patch.object(p,'active_training',return_value=False),patch.object(p,'sources',return_value=([],[])):r=p.main()
        self.assertEqual(r['source_writes'],0);self.assertTrue(all(x.read_bytes()==b'original-private-stop-state' for x in self.paths))
    def test_unknown_nox_service_hold_before_mutation(self):
        with patch.object(p,'execute',return_value=(0,b'nox-unknown RUNNING pid 9\n')),patch.object(p,'active_training',return_value=False),patch.object(p,'sources',side_effect=AssertionError('no AST')),self.assertRaises(p.Hold):p.main()
        self.assertFalse(any(x.exists() for x in self.paths))
    def test_failed_stop_no_ast_and_status_exposed(self):
        def command(args,*a,**kw):return (1,b'') if args[1]=='stop' else (0,b'nox-proxy RUNNING pid 9 PRIVATE\n')
        with patch.object(p,'execute',side_effect=command),patch.object(p,'active_training',return_value=False),patch.object(p,'sources',side_effect=AssertionError('no AST')),self.assertRaises(p.Hold) as error:p.main()
        r=p.failure_record(error.exception);self.assertFalse(r['ast_read_started']);self.assertEqual(r['stop_observation']['supervisor_status'],[{'name':'nox-proxy','state':'RUNNING'}]);self.assertNotIn('PRIVATE',json.dumps(r))
    def test_trainer_service_detected_without_exporting_cmdline(self):
        with patch.object(p.os,'scandir',return_value=[]):self.assertTrue(p.active_training([{'name':'nox-train-volta-t866u','state':'RUNNING'}]))
        self.assertEqual(p.OBSERVATION['trainer_match_count'],0)
    def test_stop_flags_symlink_no_follow(self):
        outside=self.root/'outside';outside.write_bytes(b'original');self.paths[0].symlink_to(outside)
        with self.assertRaises(p.Hold):p.ensure_stop_flags()
        self.assertEqual(outside.read_bytes(),b'original')
    def test_ast_literals_still_suppressed(self):
        r=p.project(b'def remember(text="PRIVATE_VALUE"): return text\nb=HostBindings(s03_append=w.append,token="PRIVATE_TOKEN")')
        self.assertNotIn('PRIVATE_',json.dumps(r));self.assertEqual(r['constructor_bindings'][0]['keyword_symbols']['s03_append'],'w.append')
if __name__=='__main__':unittest.main(verbosity=2)
