#!/usr/bin/env python3
"""Admission, integrity, resume and GPU-lease tests; no network/CUDA operations."""
import hashlib
import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
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


if __name__=='__main__': unittest.main()
