#!/usr/bin/env python3
"""Admission, integrity, resume and GPU-lease tests; no network/CUDA operations."""
import hashlib
import importlib.util
import contextlib
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import threading
import time
import types
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location('owner_media_install',Path(__file__).with_name('owner_media_install.py'))
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class Reply(io.BytesIO):
    def __init__(self,data,status=200,headers=None):
        super().__init__(data)
        self.status = status
        self.headers = headers or {}


class MediaInstallTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.patch = mock.patch.multiple(m,ROOT=self.root,MEDIA=self.root/'media',
                                        SHM=self.root/'ram',STATE=self.root/'state/owner_media')
        self.patch.start(); self.addCleanup(self.patch.stop)

    def test_fresh_native_budget_admits_all_ram_with_real_reserves(self):
        rows = m.plan_assets({'disk_free':int(15.3*m.GIB),'shm_free':20749209600,
                              'memory_free':194065203200-50690568192})
        self.assertEqual({r['storage'] for r in rows},{'ram'})
        self.assertEqual(sum(r['bytes'] for r in rows),16766066457)
        self.assertGreaterEqual(20749209600-sum(r['bytes'] for r in rows),m.SHM_RESERVE)
        self.assertEqual({r['role'] for r in rows},{'checkpoint','unet','clip','vae'})

    def test_lower_shm_uses_only_text_encoder_on_disk(self):
        rows = m.plan_assets({'disk_free':int(15.3*m.GIB),'shm_free':int(16.8*m.GIB),'memory_free':100*m.GIB})
        self.assertEqual([r['role'] for r in rows if r['storage']=='disk'],['clip'])
        disk = sum(r['bytes'] for r in rows if r['storage']=='disk')
        self.assertGreaterEqual(int(15.3*m.GIB)-disk-m.SETUP_ALLOWANCE,m.DISK_RESERVE)

    def test_insufficient_resources_block_before_download(self):
        for budget,code in (({'disk_free':7*m.GIB,'shm_free':30*m.GIB,'memory_free':100*m.GIB},'DISK_SETUP'),
                            ({'disk_free':15*m.GIB,'shm_free':10*m.GIB,'memory_free':100*m.GIB},'MODEL_STORAGE'),
                            ({'disk_free':15*m.GIB,'shm_free':30*m.GIB,'memory_free':30*m.GIB},'CGROUP')):
            with self.subTest(code=code),self.assertRaisesRegex(RuntimeError,code):
                m.plan_assets(budget)

    def test_resumed_partial_is_not_double_counted_or_moved(self):
        first = m.ASSETS[0]
        progress = 6*m.GIB
        partials = {first['filename']:{'storage':'ram','bytes':progress}}
        total = sum(row['bytes'] for row in m.ASSETS)
        rows = m.plan_assets({'disk_free':9*m.GIB,'shm_free':total-progress+m.SHM_RESERVE,
                              'memory_free':100*m.GIB},partials=partials)
        self.assertEqual({r['storage'] for r in rows},{'ram'})

    def test_download_resumes_exact_range_and_hashes_entire_file(self):
        payload = b'complete binary content\x00\xff'
        target = self.root/'models/test.safetensors'; target.parent.mkdir()
        partial = target.with_name(target.name+'.partial'); partial.write_bytes(payload[:9])
        expected = {'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}
        def open_request(request,timeout):
            self.assertEqual(request.get_header('Range'),'bytes=9-')
            return Reply(payload[9:],206,{'Content-Range':'bytes 9-'+str(len(payload)-1)+'/'+str(len(payload))})
        with mock.patch.object(m.urllib.request,'urlopen',side_effect=open_request), \
             mock.patch.object(m,'check_write_space'),mock.patch.object(m,'emit'):
            checked = m.download('https://huggingface.co/owner/repo/resolve/pin/model',target,expected)
        self.assertTrue(checked['verified'])
        self.assertEqual(target.read_bytes(),payload)
        self.assertFalse(partial.exists())

    def test_download_mismatch_never_publishes_or_deletes_existing_data(self):
        unrelated = self.root/'important.gguf'; unrelated.write_bytes(b'keep')
        target = self.root/'bad.safetensors'
        expected = {'bytes':3,'sha256':hashlib.sha256(b'yes').hexdigest()}
        with mock.patch.object(m.urllib.request,'urlopen',return_value=Reply(b'bad')), \
             mock.patch.object(m,'check_write_space'),mock.patch.object(m,'emit'):
            with self.assertRaisesRegex(RuntimeError,'FILE_SHA'):
                m.download('https://huggingface.co/x/y/resolve/pin/model',target,expected)
        self.assertFalse(target.exists())
        self.assertEqual(target.with_name(target.name+'.partial').read_bytes(),b'bad')
        self.assertEqual(unrelated.read_bytes(),b'keep')

    def test_wrong_resume_range_does_not_append_to_partial(self):
        target = self.root/'bad.safetensors'
        partial = target.with_name(target.name+'.partial'); partial.write_bytes(b'a')
        expected = {'bytes':3,'sha256':hashlib.sha256(b'abc').hexdigest()}
        with mock.patch.object(m.urllib.request,'urlopen',return_value=Reply(b'bc',206,{'Content-Range':'bytes 0-1/3'})), \
             mock.patch.object(m,'check_write_space'):
            with self.assertRaisesRegex(RuntimeError,'RESUME_RANGE'):
                m.download('https://huggingface.co/x/y/resolve/pin/model',target,expected)
        self.assertEqual(partial.read_bytes(),b'a')

    def test_archive_traversal_and_symlinks_are_rejected(self):
        for kind in ('traversal','symlink'):
            archive = self.root/(kind+'.tar.gz')
            with tarfile.open(archive,'w:gz') as out:
                name = 'ComfyUI-'+m.COMFY_COMMIT+('/../../outside' if kind=='traversal' else '/escape')
                member = tarfile.TarInfo(name)
                if kind=='symlink': member.type=tarfile.SYMTYPE; member.linkname='/root/nox'
                out.addfile(member)
            with self.subTest(kind=kind),self.assertRaisesRegex(RuntimeError,'ARCHIVE'):
                m.extract_source(archive,self.root/(kind+'-engine'))
            self.assertFalse((self.root/(kind+'-engine')).exists())

    def test_shared_trainer_gpu_lease_is_exclusive_and_not_a_stale_flag(self):
        with m.gpu_lease():
            with self.assertRaisesRegex(RuntimeError,'GPU1_LEASE_BUSY'):
                with m.gpu_lease(): pass
        self.assertTrue((self.root/'state/forge_training.lock').exists())
        with m.gpu_lease(): pass

    def test_models_use_extra_paths_without_weight_copy(self):
        rows = m.plan_assets({'disk_free':20*m.GIB,'shm_free':24*m.GIB,'memory_free':100*m.GIB})
        config = m.model_paths_config(rows)['nox_media']
        self.assertEqual(config['base_path'],'/')
        for row in rows:
            self.assertIn(str(Path(row['path']).parent),config[row['subdir']].splitlines())

    def environment_fixture(self, legacy=True):
        environment = self.root/'media/venv'
        purelib = environment/'lib/python3.12/site-packages'
        purelib.mkdir(parents=True)
        base = {'purelib':'/root/venv_volta/lib/python3.12/site-packages',
                'torch':'2.6.0+cu124','torch_file':'/root/venv_volta/lib/python3.12/site-packages/torch/__init__.py',
                'python':'3.12.16','machine':'x86_64'}
        marker = environment/'nox-environment.json'
        marker.write_text(json.dumps(m.environment_spec(base,legacy=legacy)))
        (purelib/'nox_shared_torch.pth').write_text(base['purelib']+'\n')
        return purelib,base,marker

    def environment_runner(self, purelib, base, calls, failure=None):
        def run(args, *positional, **kwargs):
            args = list(map(str,args)); calls.append(args)
            if args[1:3]==['-m','pip']:
                return ''
            code = args[2]
            if 'sysconfig.get_path' in code:
                return str(purelib)
            if code == m.PIN_AUDIT_CODE:
                requested = json.loads(args[3])
                if requested == list(m.AIOHTTP_PINS) and not any(c[1:3]==['-m','pip'] for c in calls):
                    return json.dumps({'ok':False,'missing':['multidict'],'mismatched':[],
                                       'outside_isolated_environment':[]})
                return json.dumps({'ok':True,'missing':[],'mismatched':[],
                                   'outside_isolated_environment':[]})
            if code == m.DEPENDENCY_AUDIT_CODE:
                return json.dumps({'ok':True,'packages_checked':45,'issues':[]})
            if 'libvpx-vp9' in code:
                if failure: raise RuntimeError(failure)
                return json.dumps({'torch':base['torch'],'torch_file':base['torch_file'],
                                   'vp9_encoder':'libvpx-vp9','requests':'2.34.2',
                                   'aiohttp':'3.11.13','multidict':'6.9.1'})
            raise AssertionError('unexpected command')
        return run

    def test_exact_observed_environment_adds_complete_seven_wheel_closure(self):
        purelib,base,marker = self.environment_fixture()
        calls = []
        with mock.patch.object(m,'run',side_effect=self.environment_runner(purelib,base,calls)),mock.patch.object(m,'emit'):
            m.ensure_environment(base)
        pip = [row for row in calls if row[1:3]==['-m','pip']]
        self.assertEqual(len(pip),1)
        self.assertIn('--no-deps',pip[0])
        self.assertIn('--no-index',pip[0])
        wheels = [arg for arg in pip[0] if arg.startswith('https:')]
        self.assertEqual(len(wheels),7)
        self.assertTrue(all('files.pythonhosted.org/' in arg and '#sha256=' in arg for arg in wheels))
        self.assertNotIn('torchvision', ' '.join(pip[0]))
        self.assertNotIn('torchaudio', ' '.join(pip[0]))
        self.assertNotIn('/requests-', ' '.join(pip[0]))
        baseline=[json.loads(row[3]) for row in calls if row[1]=='-c' and row[2]==m.PIN_AUDIT_CODE][0]
        self.assertEqual(baseline,list(m.LEGACY_PYPI_PINS+m.REQUESTS_PINS+m.CUDA_PINS))
        self.assertEqual(json.loads(marker.read_text()),m.environment_spec(base))

    def test_unknown_or_altered_legacy_environment_is_not_rewritten(self):
        purelib,base,marker = self.environment_fixture()
        unknown = m.environment_spec(base,legacy=True)
        unknown['shared_torch']='unrecognized'
        marker.write_text(json.dumps(unknown))
        before = marker.read_bytes()
        with mock.patch.object(m,'run') as run:
            with self.assertRaisesRegex(RuntimeError,'EXISTING_ENVIRONMENT_SCOPE'):
                m.ensure_environment(base)
        run.assert_not_called()
        self.assertEqual(marker.read_bytes(),before)
        marker.write_text(json.dumps(m.environment_spec(base,legacy=True)))
        calls=[]
        runner=self.environment_runner(purelib,base,calls)
        def changed(args,*positional,**kwargs):
            if args[2] == m.PIN_AUDIT_CODE:
                return json.dumps({'ok':False,'missing':[], 'mismatched':['transformers'],
                                   'outside_isolated_environment':[]})
            return runner(args,*positional,**kwargs)
        with mock.patch.object(m,'run',side_effect=changed),mock.patch.object(m,'emit'):
            with self.assertRaisesRegex(RuntimeError,'LEGACY_PACKAGES_CHANGED'):
                m.ensure_environment(base)
        self.assertFalse(any(row[1:3]==['-m','pip'] for row in calls))
        self.assertEqual(json.loads(marker.read_text()),m.environment_spec(base,legacy=True))

    def test_failed_import_keeps_old_environment_marker_for_safe_retry(self):
        purelib,base,marker = self.environment_fixture()
        before = marker.read_bytes()
        calls=[]
        with mock.patch.object(m,'run',side_effect=self.environment_runner(purelib,base,calls,'HOLD_MEDIA_COMMAND_EXIT_1')),mock.patch.object(m,'emit'):
            with self.assertRaisesRegex(RuntimeError,'COMMAND_EXIT_1'):
                m.ensure_environment(base)
        self.assertEqual(marker.read_bytes(),before)

    def test_dependency_audit_ignores_unrequested_extras_and_shared_torch_installer_graph(self):
        rows={'core':('1',['requests>=2','optional;extra == "private"','torch==2.6.0']),
              'requests':('2.34.2',['idna>=2.5,<4']),'idna':('3.20',[]),
              'torch':('2.6.0+cu124',['do-not-install-driver'])}
        def distribution(name):
            version,requirements=rows[name]
            return types.SimpleNamespace(version=version,requires=requirements)
        output=io.StringIO()
        with mock.patch('importlib.metadata.distribution',side_effect=distribution), \
             mock.patch.object(sys,'argv',['audit','["core==1"]']),contextlib.redirect_stdout(output):
            exec(compile(m.DEPENDENCY_AUDIT_CODE,'<dependency-audit>','exec'),{})
        result=json.loads(output.getvalue())
        self.assertTrue(result['ok'])
        self.assertEqual(result['packages_checked'],4)

    def test_parallel_transfers_are_jointly_admitted_and_bounded_at_three(self):
        rows=m.plan_assets({'disk_free':20*m.GIB,'shm_free':24*m.GIB,'memory_free':100*m.GIB})
        active=0; maximum=0; guard=threading.Lock()
        def transfer(url,path,row,reserve):
            nonlocal active,maximum
            with guard:
                active+=1;maximum=max(maximum,active)
            time.sleep(0.04)
            with guard:active-=1
            return {'verified':True,'path':str(path),'stat_mtime_ns':1}
        with mock.patch.object(m,'resources',return_value={'disk_free':20*m.GIB,'shm_free':24*m.GIB,'memory_free':100*m.GIB}), \
             mock.patch.object(m,'download',side_effect=transfer) as download,mock.patch.object(m,'emit'):
            m.download_selected(rows)
        self.assertEqual(download.call_count,4)
        self.assertEqual(maximum,3)
        self.assertTrue(all(row['verified'] for row in rows))
        with mock.patch.object(m,'resources',return_value={'disk_free':20*m.GIB,'shm_free':m.SHM_RESERVE,'memory_free':100*m.GIB}), \
             mock.patch.object(m,'download') as download:
            with self.assertRaisesRegex(RuntimeError,'PARALLEL_SHM_ADMISSION'):
                m.download_selected(rows)
        download.assert_not_called()

    def test_environment_failure_does_not_cancel_admitted_downloads(self):
        complete=threading.Event()
        def downloads(rows,allowance):
            self.assertEqual(allowance,m.SETUP_ALLOWANCE)
            time.sleep(0.03);complete.set()
        with mock.patch.object(m,'admit_parallel_downloads') as admitted, \
             mock.patch.object(m,'ensure_environment',side_effect=RuntimeError('HOLD_MEDIA_DEPENDENCY_CLOSURE')), \
             mock.patch.object(m,'download_selected',side_effect=downloads),mock.patch.object(m,'emit'):
            with self.assertRaisesRegex(RuntimeError,'DEPENDENCY_CLOSURE'):
                m.prepare_assets_and_environment({},[])
        admitted.assert_called_once_with([],m.SETUP_ALLOWANCE)
        self.assertTrue(complete.is_set())

    def test_compiled_dependency_wheels_require_observed_platform(self):
        _,base,_=self.environment_fixture()
        with mock.patch.object(m,'run') as run:
            with self.assertRaisesRegex(RuntimeError,'DEPENDENCY_WHEEL_PLATFORM'):
                m.ensure_environment({**base,'python':'3.11.16'})
        run.assert_not_called()


    def test_v13_manual_stop_prevents_media_activation_before_lease(self):
        # Under V13, source/media preparation is allowed, but service activation
        # must never override a manual STOP or acquire GPU/engine leases.
        for name, symbolic in (
                ('STOP', False), ('state/MEDIA_STOP.flag', False),
                ('STOP.flag', True), ('program/STOP', False)):
            with self.subTest(marker=name):
                marker = self.root / name
                marker.parent.mkdir(parents=True, exist_ok=True)
                if symbolic:
                    marker.symlink_to(self.root / 'missing-marker-target')
                else:
                    marker.write_text('OWNER STOP')
                with mock.patch.object(m, 'lock') as engine_lock, \
                     mock.patch.object(m, 'gpu_lease') as lease, \
                     mock.patch.object(m, 'health_chat') as chat_health, \
                     mock.patch.object(m, 'service_status') as supervisor:
                    with self.assertRaisesRegex(RuntimeError, 'HOLD_MEDIA_OWNER_STOP_PRESENT'):
                        m.start_engine({'engine_root': str(self.root / 'media')})
                    engine_lock.assert_not_called()
                    lease.assert_not_called()
                    chat_health.assert_not_called()
                    supervisor.assert_not_called()
                marker.unlink()


    def test_v13_state_stop_flag_and_maintenance_marker_block_media(self):
        # These marker aliases existed in the owner/lifeline contract but
        # were missing from the direct media start admission path.
        for name, symlink in (('state/STOP.flag', False),
                              ('state/OWNER_MAINTENANCE.flag', False),
                              ('state/STOP.flag', True)):
            with self.subTest(marker=name, symlink=symlink):
                marker = self.root / name
                marker.parent.mkdir(parents=True, exist_ok=True)
                if symlink:
                    marker.symlink_to(self.root / 'absent-owner-target')
                else:
                    marker.write_text('OWNER')
                self.assertTrue(m.v13_owner_stop_present())
                with mock.patch.object(m, 'gpu_lease') as lease:
                    with self.assertRaisesRegex(RuntimeError, 'HOLD_MEDIA_OWNER_STOP_PRESENT'):
                        m.start_engine({'engine_root': str(self.root / 'media')})
                    lease.assert_not_called()
                marker.unlink()

    def test_v13_held_maintenance_lease_blocks_even_without_marker(self):
        import fcntl
        import os
        lease = self.root / 'state/owner_maintenance.lock'
        lease.parent.mkdir(parents=True, exist_ok=True)
        with open(lease, 'w') as held:
            fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertTrue(m.v13_owner_stop_present())
            with mock.patch.object(m, 'gpu_lease') as gpu:
                with self.assertRaisesRegex(RuntimeError, 'HOLD_MEDIA_OWNER_STOP_PRESENT'):
                    m.start_engine({'engine_root': str(self.root / 'media')})
                gpu.assert_not_called()
            fcntl.flock(held.fileno(), fcntl.LOCK_UN)

    def test_v13_late_owner_stop_after_locks_prevents_service_action(self):
        # A new STOP appearing while waiting on GPU1/engine locks must
        # prevent chat health probes and any Supervisor start attempt.
        with mock.patch.object(m, 'v13_owner_stop_present', side_effect=[False, True]) as stop, \
             mock.patch.object(m, 'lock', return_value=contextlib.nullcontext()) as engine_lock, \
             mock.patch.object(m, 'gpu_lease', return_value=contextlib.nullcontext()) as gpu, \
             mock.patch.object(m, 'health_chat') as chat_health, \
             mock.patch.object(m, 'service_status') as supervisor:
            with self.assertRaisesRegex(RuntimeError, 'HOLD_MEDIA_OWNER_STOP_PRESENT'):
                m.start_engine({'engine_root': str(self.root / 'media')})
            self.assertEqual(stop.call_count, 2)
            engine_lock.assert_called_once_with('media.lock')
            gpu.assert_called_once()
            chat_health.assert_not_called()
            supervisor.assert_not_called()


if __name__=='__main__': unittest.main()
