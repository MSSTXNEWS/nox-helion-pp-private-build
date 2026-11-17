import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import time
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('ro_diag', HERE/'owner_runtime_stage_readonly_diagnostic.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
BASE = HERE.parent


def fixture(root):
    active = root/'state/priority/CHAT_ACTIVE'
    active.parent.mkdir(parents=True)
    active.write_bytes(b'0\n')
    active.chmod(0o600)
    dest = root/'extensions'/m.DEST_NAME
    for name in m.EXPECTED:
        src = BASE/('integrations_bridge' if '/nox_integrations/' in name else 'warm_weights_controller')/Path(name).relative_to('runtime')
        target = dest/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(src.read_bytes())
        target.chmod(0o600)
    return dest


def snapshot(root):
    return {str(p.relative_to(root)):(p.lstat().st_ino,p.lstat().st_mode,p.lstat().st_mtime_ns,
            hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() and not p.is_symlink() else None)
            for p in root.rglob('*')}


class ReadOnlyDiagnosticTests(unittest.TestCase):
    def test_twelve_exact_files_and_no_mutations(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);fixture(root);before=snapshot(root)
            with mock.patch.object(m,'ROOT',root):r=m.collect()
            self.assertEqual(r['matching_source_count'],12)
            self.assertEqual(r['source_bytes_read'],98385)
            self.assertEqual(r['chat_active_before']['value'],0)
            self.assertEqual(r['observed_original_directory_guard_failure_candidates'],[])
            self.assertEqual(snapshot(root),before)
            self.assertFalse(r['native_staging_accepted'])

    def test_final_directory_mode_is_not_ancestor_mode(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);fixture(root);root.chmod(0o775)
            with mock.patch.object(m,'ROOT',root):r=m.collect()
            self.assertEqual(r['observed_original_directory_guard_failure_candidates'],[])
            priority=root/'state/priority';priority.chmod(0o775)
            with mock.patch.object(m,'ROOT',root):r=m.collect()
            self.assertEqual(r['observed_original_directory_guard_failure_candidates'],[str(priority)])
            self.assertEqual(stat.S_IMODE(priority.stat().st_mode),0o775)
            self.assertEqual(r['matching_source_count'],12)

    def test_no_follow_leaf_and_ancestor_symlinks(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'host';dest=fixture(root)
            name=sorted(m.EXPECTED)[0];target=dest/name
            outside=Path(td)/'unrelated';outside.write_bytes(b'MUST_NOT_READ_TARGET')
            target.unlink();target.symlink_to(outside)
            row=m.inspect(target,expected=m.EXPECTED[name])
            self.assertEqual(row['status'],'NOT_REGULAR_NO_READ')
            self.assertEqual(row['bytes_read'],0)
            self.assertEqual(row['metadata']['type'],'symlink')
            self.assertNotIn('MUST_NOT_READ_TARGET',json.dumps(row))
            package=dest/'runtime/nox_warm';old=dest/'runtime/saved_warm';package.rename(old);package.symlink_to(old)
            row=m.inspect(package/'__init__.py',expected=m.EXPECTED['runtime/nox_warm/__init__.py'])
            self.assertEqual(row['status'],'SYMLINK_ANCESTOR')
            self.assertEqual(row['bytes_read'],0)

    def test_partial_mismatch_and_unknown_flag_are_reported_without_contents(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);dest=fixture(root)
            a,b,c=sorted(m.EXPECTED)[:3]
            (dest/a).unlink()
            (dest/b).write_bytes(b'x'*m.EXPECTED[b][0])
            (dest/c).write_bytes(b'x'*(m.EXPECTED[c][0]+1))
            (root/'state/priority/CHAT_ACTIVE').write_bytes(b'NOT_A_FLAG')
            with mock.patch.object(m,'ROOT',root):r=m.collect()
            self.assertEqual(r['matching_source_count'],9)
            self.assertEqual(r['present_file_count'],11)
            rows={Path(x['path']).name:x for x in r['files']}
            self.assertEqual(r['chat_active_before']['status'],'FLAG_UNKNOWN_CONTENT_WITHHELD')
            self.assertIsNone(r['chat_active_before']['value'])
            self.assertNotIn('NOT_A_FLAG',json.dumps(r))
            self.assertEqual(next(x for x in r['files'] if x['path']==str(dest/c))['bytes_read'],0)
            self.assertFalse(r['all_expected_source_files_match'])

    def test_pins_match_manifest_and_context_rejects_before_reads(self):
        path=BASE/'runtime_stage_only/STAGING_MANIFEST.json'
        raw=path.read_bytes();j=json.loads(raw)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),m.STAGING_MANIFEST_SHA256)
        self.assertEqual({r['path']:(r['bytes'],r['sha256']) for r in j['file_pins']},m.EXPECTED)
        self.assertEqual(j['bundle_sha256'],m.BUNDLE_SHA256)
        with mock.patch.dict(os.environ,{},clear=True),mock.patch.object(m,'collect') as collect:
            with self.assertRaisesRegex(RuntimeError,'HOLD_OWNER_REQUEST_CONTEXT'):m.run()
            collect.assert_not_called()

    def make_lock_fixture(self, root, proc):
        fixture(root)
        lock=root/'state/owner_maintenance.lock';lock.touch(mode=0o600)
        proc.mkdir()
        s=lock.stat()
        address=f'{os.major(s.st_dev):02x}:{os.minor(s.st_dev):02x}:{s.st_ino}'
        return address

    def make_holder(self,proc,pid):
        d=proc/str(pid);d.mkdir()
        tail=' '.join(['S']+['0']*18+['123456']+['0']*5)
        (d/'stat').write_text(f'{pid} (worker (one)) {tail}\n')
        (d/'status').write_text('Name:\towner-worker\nUid:\t0 0 0 0\nGid:\t0 0 0 0\n')

    def test_lock_holder_waiter_and_empty_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'host';proc=Path(td)/'proc';address=self.make_lock_fixture(root,proc)
            self.make_holder(proc,123)
            (proc/'locks').write_text(f'1: FLOCK ADVISORY WRITE 123 {address} 0 EOF\n1: -> FLOCK ADVISORY WRITE 999 {address} 0 EOF\n')
            with mock.patch.multiple(m,ROOT=root,PROC=proc):r=m.maintenance_snapshot(time.monotonic()+10)
            self.assertEqual(r['state'],'HELD_OBSERVED')
            self.assertEqual([x['pid'] for x in r['holders']],[123])
            self.assertEqual(r['holders'][0]['start_ticks'],123456)
            self.assertTrue(r['matching_locks'][1]['waiter'])
            self.assertFalse((proc/'999').exists())
            (proc/'locks').write_bytes(b'')
            with mock.patch.multiple(m,ROOT=root,PROC=proc):r=m.maintenance_snapshot(time.monotonic()+10)
            self.assertEqual(r['state'],'NO_MATCH_OBSERVED')
            self.assertFalse(r['free_lock_proven']);self.assertFalse(r['retry_authorized'])

    def test_ofd_and_truncated_proc_are_unknown(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'host';proc=Path(td)/'proc';address=self.make_lock_fixture(root,proc)
            (proc/'locks').write_text(f'1: OFDLCK ADVISORY WRITE -1 {address} 0 EOF\n')
            with mock.patch.multiple(m,ROOT=root,PROC=proc):r=m.maintenance_snapshot(time.monotonic()+10)
            self.assertEqual(r['state'],'UNKNOWN')
            self.assertEqual(r['reason'],'OFD_OR_UNRESOLVED_HOLDER_PID')
            self.assertEqual(r['holders'],[])
            (proc/'locks').write_bytes(b'x'*(m.MAX_PROC_LOCKS_BYTES+1))
            with mock.patch.multiple(m,ROOT=root,PROC=proc):r=m.maintenance_snapshot(time.monotonic()+10)
            self.assertEqual(r['state'],'UNKNOWN')
            self.assertTrue(r['proc_truncated'])

    def test_reused_holder_pid_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'host';proc=Path(td)/'proc';address=self.make_lock_fixture(root,proc)
            self.make_holder(proc,123)
            (proc/'locks').write_text(f'1: FLOCK ADVISORY WRITE 123 {address} 0 EOF\n')
            with mock.patch.multiple(m,ROOT=root,PROC=proc),mock.patch.object(m,'proc_start_ticks',side_effect=[123456,123457]):
                r=m.maintenance_snapshot(time.monotonic()+10)
            self.assertEqual(r['state'],'UNKNOWN')
            self.assertEqual(r['reason'],'PROC_PID_REUSED_OR_CHANGED')
            self.assertFalse(r['free_lock_proven']);self.assertFalse(r['retry_authorized'])


if __name__=='__main__':unittest.main()
