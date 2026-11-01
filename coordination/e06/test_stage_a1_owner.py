import importlib.util,hashlib,json,sys,tempfile,unittest
from pathlib import Path
P=Path(__file__).with_name('stage_a1_owner.py')
spec=importlib.util.spec_from_file_location('stage_a1_owner_candidate',P)
a=importlib.util.module_from_spec(spec);sys.modules[spec.name]=a;spec.loader.exec_module(a)

class A1StageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        base=Path(self.tmp.name);self.repo=base/'checkout';self.repo.mkdir()
        self.stage=self.repo/'work'/'original';self.stage.mkdir(parents=True)
        m={}
        for name in a.REQUIRED:
            original=self.repo/'src'/'nox_selfbuilder'/name
            original.parent.mkdir(parents=True,exist_ok=True)
            data=(f'# {name} candidate bytes\nFOUND=True\n').encode()
            original.write_bytes(data);m[name]=a.git_blob(data)
        self.lock=self.repo/'coordination'/'e06'/'A1_BUILD_SOURCES.lock.json'
        self.lock.parent.mkdir(parents=True)
        self.lock.write_text(json.dumps({'schema':'NOX-A1-ONEHOST-STAGE-LOCK-v1','sources':m}))
    def run_stage(self):return a.stage(self.stage,repo=self.repo,manifest_path=self.lock)
    def test_ten_source_files_physically_staged_and_sha_readback(self):
        v=self.run_stage()
        self.assertEqual(v['source_count'],10)
        self.assertEqual(len(v['runtime_data_files']),10)
        for q in v['runtime_data_files']:
            f=self.stage/q['runtime_path']
            self.assertEqual(hashlib.sha256(f.read_bytes()).hexdigest(),q['sha256'])
        self.assertFalse(v['installed_exe_accepted'])
    def test_corrupted_digest_fails_before_any_write(self):
        m=json.loads(self.lock.read_text());m['sources']['worm_autopilot.py']='a'*40
        self.lock.write_text(json.dumps(m))
        with self.assertRaisesRegex(ValueError,'SHA_HOLD'):
            self.run_stage()
        self.assertFalse((self.stage/'nox_selfbuilder').exists())
    def test_existing_source_prevents_overwrite(self):
        original=self.stage/'nox_selfbuilder'/'worms.py'
        original.parent.mkdir();original.write_text('USER FILE')
        with self.assertRaisesRegex(ValueError,'DUPLICATE'):
            self.run_stage()
        self.assertEqual(original.read_text(),'USER FILE')
    def test_sourceroot_cannot_be_itself_stage(self):
        with self.assertRaisesRegex(ValueError,'DISPOSABLE'):
            a.stage(self.repo,repo=self.repo,manifest_path=self.lock)
    def test_reparse_source_denied(self):
        target=self.repo/'src'/'nox_selfbuilder'/'worms.py';target.unlink()
        external=self.repo/'replacement';external.write_text('SAFE=False\n')
        try:target.symlink_to(external)
        except OSError:self.skipTest('symlinks unavailable')
        with self.assertRaisesRegex(ValueError,'REPARSE'):
            self.run_stage()
        self.assertFalse((self.stage/'nox_selfbuilder').exists())
    def test_rollback_only_written_files_on_failure(self):
        import builtins
        # Trigger a failure after the first new file, verify no orphaned files remain.
        old=a.Path.open
        calls=[0]
        def crash(path,*args,**kwargs):
            if str(path).endswith('worm_providers.py') and args and args[0]=='xb':
                raise OSError('forced staged failure')
            return old(path,*args,**kwargs)
        a.Path.open=crash
        try:
            with self.assertRaises(OSError):self.run_stage()
        finally:a.Path.open=old
        self.assertFalse((self.stage/'nox_selfbuilder'/'worms.py').exists())
    def test_unchanged_head_pin_accepts_source(self):
        v=self.run_stage();self.assertFalse(v['native_activation_verified'])
        self.assertFalse(v['model_weights_installed'])

if __name__=='__main__':unittest.main()
