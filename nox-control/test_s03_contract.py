import importlib.util,json,os,pathlib,tempfile,unittest,sys
from unittest.mock import patch
HERE=pathlib.Path(__file__).parent
spec=importlib.util.spec_from_file_location('s03_contract_probe',HERE/'owner_native_deploy.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
class Tests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.temp.name);p.DEADLINE=None
    def tearDown(self):self.temp.cleanup()
    def test_signatures_and_binder_without_literals(self):
        raw=b'''from library import AttachedNOX, HostBindings
class AttachedNOX:
 def remember(self, text="PRIVATE_TEXT", *, writer_lease="PRIVATE_KEY"):
  original_writer.append(text)
binding=HostBindings(s03_append=original_writer.append, revision=writer.revision, lease_epoch="PRIVATE_EPOCH", other=lambda: "PRIVATE_LAMBDA")
'''
        result=p.project(raw);text=json.dumps(result)
        for private in ['PRIVATE_TEXT','PRIVATE_KEY','PRIVATE_EPOCH','PRIVATE_LAMBDA']:self.assertNotIn(private,text)
        fn=result['functions'][0];self.assertEqual(fn['positional'],['self','text']);self.assertEqual(fn['keyword_only'],['writer_lease']);self.assertEqual(fn['default_count'],2)
        bind=result['constructor_bindings'][0]['keyword_symbols'];self.assertEqual(bind['s03_append'],'original_writer.append');self.assertIsNone(bind['lease_epoch']);self.assertIsNone(bind['other'])
    def test_pathfinder_resolves_without_execution(self):
        marker=self.root/'EXECUTED';source=self.root/'s03_memory.py';source.write_text('open('+repr(str(marker))+',"w").write("bad")\ndef remember(text): pass\n')
        old='s03_memory' in sys.modules
        with patch.object(p,'ROOT',self.root),patch.object(p,'SCRIPT_NAMES',()),patch.object(p,'MODULE_ROOTS',{'s03_memory':(self.root,)}),patch.object(p,'ALLOWED_PATHS',{source}):
            rows,resolution=p.sources()
        self.assertEqual(rows[0]['state'],'AST_CONTRACT_OBSERVED');self.assertEqual(resolution[0]['origins'],[str(source)])
        self.assertFalse(marker.exists());self.assertEqual('s03_memory' in sys.modules,old)
    def test_database_and_arbitrary_path_rejected(self):
        path=self.root/'knowledge.sqlite';path.write_bytes(b'private')
        with self.assertRaises(p.Hold):p.inspect_source(path)
        path2=self.root/'not_allowed.py';path2.write_text('def remember(x):pass')
        with self.assertRaises(p.Hold):p.inspect_source(path2)
    def test_symlinks_and_oversized_source_fail_closed(self):
        real=self.root/'real.py';real.write_text('def remember(x):pass');alias=self.root/'alias.py';alias.symlink_to(real)
        with patch.object(p,'ALLOWED_PATHS',{alias}):self.assertEqual(p.inspect_source(alias)['state'],'HOLD_SOURCE_UNREADABLE_OR_INVALID')
        big=self.root/'big.py';big.write_bytes(b' '*(p.MAX_FILE+1))
        with patch.object(p,'ALLOWED_PATHS',{big}):self.assertEqual(p.inspect_source(big)['state'],'HOLD_SOURCE_UNREADABLE_OR_INVALID')
    def test_static_projection_is_bounded(self):
        with self.assertRaises(p.Hold):p.project(b'x=1\n'*(p.MAX_FILE//4+1))
        source='\n'.join('def remember_'+str(i)+'(x):pass' for i in range(40))
        result=p.project(source.encode());self.assertEqual(len(result['functions']),32);self.assertTrue(result['truncated'])
    def test_held_main_has_no_mutations_and_no_database(self):
        state=self.root/'state';state.mkdir();lock=state/'owner_maintenance.lock';lock.write_bytes(b'');lock.chmod(0o600)
        before={x:x.read_bytes() for x in state.iterdir()}
        with patch.object(p,'STATE',state),patch.object(p,'flags',return_value=['a']*4),patch.object(p,'stopped',return_value=28),patch.object(p,'sources',return_value=([],[])),patch.dict(os.environ,{'NOX_OWNER_SOURCE_SHA':'a'*40,'NOX_OWNER_REQUEST_ID':'123'}):
            result=p.main()
        self.assertEqual(result['source_writes'],0);self.assertFalse(result['database_opened']);self.assertEqual(before,{x:x.read_bytes() for x in state.iterdir()})
    def test_stop_flag_change_is_hold(self):
        state=self.root/'state';state.mkdir();(state/'owner_maintenance.lock').write_bytes(b'')
        with patch.object(p,'STATE',state),patch.object(p,'flags',side_effect=[['a']*4,['b']*4]),patch.object(p,'stopped',return_value=28),patch.object(p,'sources',side_effect=AssertionError('must not inspect')),patch.dict(os.environ,{'NOX_OWNER_SOURCE_SHA':'a'*40,'NOX_OWNER_REQUEST_ID':'123'}),self.assertRaises(p.Hold):p.main()
    def test_sensitive_identifier_exclusion_and_expression_suppression(self):
        result=p.project(b'import secret_module\nx=HostBindings(s03_append=getattr(owner,"PRIVATE_NAME"), api_key=secret_token)\ndef remember(x:"PRIVATE_TYPE"="PRIVATE_DEFAULT"): pass')
        text=json.dumps(result);self.assertNotIn('PRIVATE',text);self.assertNotIn('secret_module',text);self.assertNotIn('secret_token',text)
        self.assertIsNone(result['constructor_bindings'][0]['keyword_symbols']['s03_append'])
if __name__=='__main__':unittest.main(verbosity=2)
