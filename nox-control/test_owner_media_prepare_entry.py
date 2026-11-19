"""Native job identity, inherited lease and readiness evidence; no GPU/network."""
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


entry = module('prepare_entry_test', HERE/'owner_media_prepare_entry.py')
installer = module('prepare_installer_test', HERE/'owner_media_install.py')


class PreparationTests(unittest.TestCase):
    def test_pid_boot_argv_starttime_must_all_match(self):
        record = {'pid':101,'start_ticks':'1000','boot_id':'boot-a','argv':['python','installer.py']}
        observed = dict(record, state='S')
        self.assertTrue(entry.same_job(record, observed))
        for field, value in [('pid',102),('start_ticks','1001'),('boot_id','boot-b'),
                             ('argv',['python','unrelated.py']),('state','Z')]:
            with self.subTest(field=field):
                self.assertFalse(entry.same_job(record, dict(observed, **{field:value})))

    def test_background_job_inherits_single_writer_lease_after_parent_releases(self):
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory)/'job.lock'
            fd = entry.acquire(lock)
            self.assertIsNotNone(fd)
            child = subprocess.Popen([sys.executable, '-c',
                'import os,sys,time;os.fstat(int(sys.argv[1]));print("ready",flush=True);time.sleep(0.4)', str(fd)],
                stdout=subprocess.PIPE, text=True, close_fds=True, pass_fds=(fd,))
            try:
                self.assertEqual(child.stdout.readline().strip(), 'ready')
                os.close(fd); fd = None
                self.assertIsNone(entry.acquire(lock))
                child.wait(timeout=3)
                released = entry.acquire(lock); self.assertIsNotNone(released); os.close(released)
            finally:
                if fd is not None: os.close(fd)
                if child.poll() is None: child.terminate(); child.wait(timeout=3)
                child.stdout.close()

    def fixture(self, root):
        payload = root/'model.safetensors'; payload.write_bytes(b'exact model fixture')
        asset = {'filename':'model.safetensors','role':'checkpoint','kind':'image',
                 'bytes':payload.stat().st_size,'sha256':hashlib.sha256(payload.read_bytes()).hexdigest()}
        engine = root/'engine'; engine.mkdir(); main = engine/'main.py'; main.write_text('print("fixture")')
        config = {'assets':[{**asset,'path':str(payload)}],'enabled':True,'engine_root':str(engine),
                  'engine_pid':123,'start_ticks':'500','engine_service':'nox-media-comfyui',
                  'engine_main_sha256':hashlib.sha256(main.read_bytes()).hexdigest()}
        cfg = root/'config.json'; cfg.write_text(json.dumps(config))
        fake = types.SimpleNamespace(ASSETS=(asset,), SERVICE='nox-media-comfyui', REQUIRED_NODES=('Node',),
            validate_file=installer.validate_file, sha256=installer.sha256,
            service_status=lambda:{'state':'RUNNING','pid':123},
            process_identity=lambda pid:{'cuda':'1','service':'nox-media-comfyui','argv':['python',str(main)],
                                         'pid':pid,'start_ticks':'500'},
            get_json=lambda *args,**kwargs:{'Node':{},'CheckpointLoaderSimple':{
                'input':{'required':{'ckpt_name':[['model.safetensors']]}}}}, health_chat=lambda:None)
        return payload, cfg, config, fake

    def test_only_full_assets_and_live_engine_are_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            payload, cfg, config, fake = self.fixture(Path(directory))
            with patch.object(entry, 'CONFIG', cfg):
                ready = entry.readiness(fake)
                self.assertEqual(ready['state'], 'ENGINE_AND_FILES_READY_GENERATION_ACCEPTANCE_PENDING')
                self.assertFalse(ready['generation_acceptance_verified'])
                self.assertTrue(ready['all_asset_sha256_verified'])
                nodes = fake.get_json
                fake.get_json = lambda *args,**kwargs:{'Node':{}}
                with self.assertRaisesRegex(RuntimeError, 'READY_MODEL_OPTION'):
                    entry.readiness(fake)
                fake.get_json = nodes
                fake.service_status = lambda:{'state':'STOPPED','pid':None}
                with self.assertRaisesRegex(RuntimeError, 'READY_SERVICE_NOT_RUNNING'):
                    entry.readiness(fake)

    def test_missing_ram_asset_never_claims_ready_and_can_rehydrate(self):
        with tempfile.TemporaryDirectory() as directory:
            payload, cfg, config, fake = self.fixture(Path(directory))
            payload.unlink()
            with patch.object(entry, 'CONFIG', cfg):
                result = entry.readiness(fake)
            self.assertEqual(result['state'], 'FILES_INCOMPLETE_REHYDRATION_REQUIRED')
            self.assertFalse(result['all_asset_sha256_verified'])

    def test_corrupt_asset_or_wrong_gpu_fails_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            payload, cfg, config, fake = self.fixture(Path(directory))
            with patch.object(entry, 'CONFIG', cfg):
                original = fake.process_identity
                fake.process_identity = lambda pid:dict(original(pid), cuda='0')
                with self.assertRaisesRegex(RuntimeError, 'READY_PROCESS_IDENTITY'):
                    entry.readiness(fake)
                fake.process_identity = original
                payload.write_bytes(b'bad')
                with self.assertRaisesRegex(RuntimeError, 'EXISTING_FILE_SIZE'):
                    entry.readiness(fake)

    def test_source_pins_and_generated_worker_compile(self):
        self.assertEqual(entry.digest(HERE/'owner_media_install.py'), entry.INSTALLER_SHA)
        self.assertEqual(entry.digest(HERE/'owner_media_runtime.py'), entry.RUNTIME_SHA)
        compile(entry.WORKER_SOURCE, '<finite-media-worker>', 'exec')
        legacy=entry.WORKER_SOURCE.replace(entry.INSTALLER_SHA,entry.LEGACY_INSTALLER_SHA)
        self.assertEqual(hashlib.sha256(legacy.encode()).hexdigest(),entry.LEGACY_WORKER_SHA)

    def migration_fixture(self, root):
        state=root/'state';state.mkdir()
        request='6903919663'
        old={'schema':'NOX_MEDIA_PREPARE_JOB_V1','request':request,'source_sha':entry.LEGACY_SOURCE_SHA,
             'installer_sha256':entry.LEGACY_INSTALLER_SHA,'runtime_sha256':entry.RUNTIME_SHA,
             'worker_sha256':entry.LEGACY_WORKER_SHA,'pid':101,'start_ticks':'1000',
             'boot_id':'boot-a','argv':['python','worker.py'],'state':'S'}
        archived=state/'prepare_jobs'/(request+'.json');archived.parent.mkdir()
        archived.write_text(json.dumps(old))
        result={'schema':'NOX_MEDIA_PREPARE_WORKER_V1','request':request,'source_sha':entry.LEGACY_SOURCE_SHA,
                'state':'HOLD_MEDIA_PREPARE','error':'HOLD_MEDIA_DEPENDENCY_CLOSURE',
                'started':1794788749.5905006,'finished':1794788752.6067092}
        result_path=state/('prepare_result_'+request+'.json')
        result_path.write_text(json.dumps(result))
        return state,old,result,result_path

    def test_migration_requires_exact_terminated_known_job_and_matching_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            state,old,result,result_path=self.migration_fixture(Path(directory))
            with patch.object(entry,'STATE',state),patch.object(entry,'identity',return_value=None), \
                 patch.object(entry,'original_hold') as hold:
                proof=entry.legacy_migration_proof(old)
                self.assertEqual(proof['request'],old['request'])
                hold.assert_called_once()
                result['source_sha']='b'*40
                result_path.write_text(json.dumps(result))
                with self.assertRaisesRegex(RuntimeError,'LEGACY_FAILURE_RECEIPT'):
                    entry.legacy_migration_proof(old)
            with patch.object(entry,'STATE',state),patch.object(entry,'identity',return_value=old), \
                 patch.object(entry,'original_hold') as hold:
                with self.assertRaisesRegex(RuntimeError,'LEGACY_JOB_IDENTITY'):
                    entry.legacy_migration_proof(old)
                hold.assert_not_called()
            with patch.object(entry,'STATE',state),patch.object(entry,'identity',return_value=None):
                with self.assertRaisesRegex(RuntimeError,'LEGACY_JOB_IDENTITY'):
                    entry.legacy_migration_proof({**old,'request':'123'})

    def test_source_migration_backs_up_only_exact_recognized_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);state=root/'state';source=root/'installer.py'
            old=b'old_pin = 1\n';new=b'new_pin = 2\n'
            source.write_bytes(old)
            old_sha=hashlib.sha256(old).hexdigest();new_sha=hashlib.sha256(new).hexdigest()
            with patch.object(entry,'STATE',state):
                with self.assertRaisesRegex(RuntimeError,'INSTALLED_COMPONENT_CHANGED'):
                    entry.install_component(source,new,new_sha,old_sha,None)
                self.assertEqual(source.read_bytes(),old)
                entry.install_component(source,new,new_sha,old_sha,{'request':'6903919663'})
                self.assertEqual(source.read_bytes(),new)
                backup=state/'source_backups'/('installer.py.'+old_sha)
                self.assertEqual(backup.read_bytes(),old)
                entry.install_component(source,new,new_sha,old_sha,None)
                source.write_bytes(b'unknown = 3\n')
                with self.assertRaisesRegex(RuntimeError,'INSTALLED_COMPONENT_CHANGED'):
                    entry.install_component(source,new,new_sha,old_sha,{'request':'6903919663'})


if __name__ == '__main__':
    unittest.main()
