"""Only local fixture files; no server process or model is touched."""
from collections import Counter
import errno
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('builder_proc_probe', Path(__file__).with_name('owner_builder_proc_probe.py'))
M = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(M)


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(); self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.proc = self.root/'proc'; self.proc.mkdir()
        item = patch.object(M, 'PROC', self.proc); item.start(); self.addCleanup(item.stop)
        self.target = self.root/'builder'; self.target.write_bytes(b'fixture')
        self.target.chmod(0o640)
        info = self.target.stat(); self.key = (info.st_dev, info.st_ino)
        self.targets = {self.key: ['BUILDER_ARCHIVE']}
        self.pid = 123
        self.pid_path = self.proc/str(self.pid); self.pid_path.mkdir()
        self.fields = ['0']*20; self.fields[0]='S'; self.fields[1]='1'; self.fields[17]='1'; self.fields[19]='987'
        self.stat_value = (str(self.pid)+' (private process) '+' '.join(self.fields)+'\n').encode()
        (self.pid_path/'stat').write_bytes(self.stat_value)
        (self.pid_path/'status').write_bytes(b'Name:\tprivate name\nUid:\t0\t0\t0\t0\nGid:\t0\t0\t0\t0\nTgid:\t123\nNSpid:\t500\t123\nThreads:\t1\n')
        (self.pid_path/'cmdline').write_bytes(b'private command\x00secret=never-export\x00')
        (self.pid_path/'fd').mkdir(); (self.pid_path/'fdinfo').mkdir(); (self.pid_path/'ns').mkdir()
        self.self_ns = {}
        for name in M.NAMESPACES:
            path = self.pid_path/'ns'/name; path.write_bytes(b'namespace fixture')
            info = path.stat(); self.self_ns[name] = [info.st_dev, info.st_ino]
        (self.pid_path/'fd/4').symlink_to(self.target)
        (self.pid_path/'fdinfo/4').write_bytes(b'flags:\t0100000\nmnt_id:\t3\n')
        dev, inode = self.key
        self.maps = ('1000-2000 r--p 0000 %x:%x %d /private/path-never-export\n' %
                     (os.major(dev), os.minor(dev), inode)).encode()
        (self.pid_path/'maps').write_bytes(self.maps)

    def probe(self):
        return M.probe_process(self.pid, self.targets, self.self_ns, time.monotonic()+3, Counter(), {})

    def test_builder_explains_permission_predicate_without_reading_content(self):
        with patch.object(M, 'EXPECTED_BYTES', 7):
            value = M.builder_metadata('BUILDER_ARCHIVE', self.target, os.geteuid())
            self.assertTrue(value['identity_predicate_passes']); self.assertEqual(value['mode_octal'],'0640')
            self.target.chmod(0o666)
            value = M.builder_metadata('BUILDER_ARCHIVE', self.target, os.geteuid())
            self.assertFalse(value['identity_predicate_passes']); self.assertTrue(value['group_or_other_writable'])
            self.assertEqual(value['content_read_bytes'],0)
            self.assertFalse(M.builder_metadata('BUILDER_ARCHIVE', self.target, os.geteuid()+1)['uid_matches'])

    def test_symlink_is_metadata_only_not_followed_as_builder(self):
        link=self.root/'alias';link.symlink_to(self.target)
        value=M.builder_metadata('BUILDER_ARCHIVE',link,os.geteuid())
        self.assertTrue(value['symlink']);self.assertFalse(value['regular']);self.assertFalse(value['identity_predicate_passes'])

    def test_both_references_and_numeric_identity_are_retained_without_text(self):
        row=self.probe()
        self.assertTrue(row['candidate_fd_maps_complete'])
        self.assertEqual(row['stat_before']['starttime'],987)
        self.assertEqual(row['status']['uid'],[0,0,0,0])
        self.assertTrue(all(n['same_as_probe'] for n in row['namespaces'].values()))
        self.assertEqual([ref['kind'] for ref in row['references']],['FD','MMAP'])
        self.assertEqual(row['references'][0]['access'],'READ_ONLY')
        encoded=json.dumps(row)
        for value in ('private','secret','never-export',str(self.target)):
            self.assertNotIn(value,encoded)

    def test_cmdline_denial_never_skips_fd_or_maps(self):
        original=M.read_at
        def read(directory,name,maximum):
            if name=='cmdline':raise PermissionError(errno.EACCES,'private error details')
            return original(directory,name,maximum)
        with patch.object(M,'read_at',side_effect=read):row=self.probe()
        self.assertTrue(row['fd_complete']);self.assertTrue(row['maps_complete'])
        self.assertTrue(row['candidate_fd_maps_complete']);self.assertEqual(len(row['references']),2)
        self.assertIn({'stage':'cmdline','errno':errno.EACCES,'error':'EACCES'},row['errors'])
        self.assertNotIn('private',json.dumps(row))

    def test_fd_denial_still_inspects_maps_and_does_not_exclude_uid(self):
        original=M.os.open
        def opening(name,*args,**kwargs):
            if name=='fd':raise PermissionError(errno.EPERM,'hidden path')
            return original(name,*args,**kwargs)
        with patch.object(M.os,'open',side_effect=opening):row=self.probe()
        self.assertFalse(row['fd_complete']);self.assertTrue(row['maps_complete'])
        self.assertEqual(row['references'][0]['kind'],'MMAP')
        self.assertFalse(row['excluded_from_file_use_proof'])

    def test_maps_denial_keeps_fd_reference_and_marks_incomplete(self):
        original=M.read_at
        def read(directory,name,maximum):
            if name=='maps':raise PermissionError(errno.EACCES,'hidden')
            return original(directory,name,maximum)
        with patch.object(M,'read_at',side_effect=read):row=self.probe()
        self.assertTrue(row['fd_complete']);self.assertFalse(row['maps_complete'])
        self.assertFalse(row['candidate_fd_maps_complete']);self.assertEqual(row['references'][0]['kind'],'FD')

    def test_identity_change_is_not_claimed_stable(self):
        original=M.read_at;reads=0
        def read(directory,name,maximum):
            nonlocal reads
            if name=='stat':
                reads+=1
                if reads==2:return self.stat_value.replace(b'987',b'988')
            return original(directory,name,maximum)
        with patch.object(M,'read_at',side_effect=read):row=self.probe()
        self.assertFalse(row['identity_stable']);self.assertFalse(row['candidate_fd_maps_complete'])

    def test_writable_fd_and_shared_mapping_are_explicit(self):
        (self.pid_path/'fdinfo/4').write_bytes(b'flags:\t0100002\n')
        (self.pid_path/'maps').write_bytes(self.maps.replace(b'r--p',b'rw-s'))
        row=self.probe();self.assertEqual(row['references'][0]['access'],'READ_WRITE')
        self.assertTrue(row['references'][1]['shared_writable'])

    def test_budget_is_partial_without_permission_or_mutation_claim(self):
        before=self.target.read_bytes();row=M.run('123','a'*40,seconds=0)
        self.assertEqual(row['state'],'PARTIAL_BUDGET_REACHED');self.assertFalse(row['pid_snapshot_complete'])
        self.assertFalse(row['deletion_admission_evaluated']);self.assertEqual(row['files_deleted'],0)
        self.assertEqual(self.target.read_bytes(),before)


if __name__=='__main__':unittest.main()
